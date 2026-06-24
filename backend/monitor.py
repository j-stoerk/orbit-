"""
Monitoring & Alerting engine — the core of a situational-awareness tool.

Continuously polls the live feeds, detects *genuinely new* events (deduplicated
against what was already seen), matches them against user-defined **watch rules**,
and dispatches real notifications over configured channels:

  * **Webhook** (keyless) — works with Slack / Discord / Teams / any generic
    incoming webhook. This is the "for everyone" alert channel.
  * **Email** (optional) — SMTP, enabled only when SMTP_* env vars are set.

On startup the engine seeds its "seen" set with the current event backlog, so it
only alerts on events that appear *after* monitoring begins (no backlog spam).
"""
from __future__ import annotations
import os
import json
import time
import smtplib
import threading
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Any

import requests
from pydantic import BaseModel, Field

from .data import live_feeds

_SEV_RANK = {"Low": 1, "Moderate": 2, "High": 3, "Critical": 4}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class WatchRule(BaseModel):
    id: str = Field(default_factory=lambda: os.urandom(4).hex())
    name: str = "New watch"
    enabled: bool = True
    min_severity: str = "High"           # Low | Moderate | High | Critical
    types: List[str] = Field(default_factory=list)   # empty = any hazard type
    region: str = ""                     # substring match on title/country; empty = global


class Channels(BaseModel):
    webhook_url: str = ""
    email_to: str = ""


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: os.urandom(4).hex())
    at: str = Field(default_factory=_now)
    rule_name: str = ""
    event: Dict[str, Any] = Field(default_factory=dict)
    delivered: List[str] = Field(default_factory=list)   # channels that succeeded
    errors: List[str] = Field(default_factory=list)


class AlertEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.rules: List[WatchRule] = [
            WatchRule(name="Global critical events", min_severity="Critical"),
        ]
        self.channels = Channels(webhook_url=os.environ.get("ALERT_WEBHOOK_URL", ""),
                                  email_to=os.environ.get("ALERT_EMAIL_TO", ""))
        self.alerts: List[Alert] = []     # most-recent-first, capped
        self.seen: set[str] = set()
        self.seeded = False
        self.last_poll: Optional[str] = None
        self.poll_count = 0

    # ---- rule / channel management ----
    def list_rules(self) -> List[WatchRule]:
        return self.rules

    def add_rule(self, rule: WatchRule) -> WatchRule:
        with self._lock:
            self.rules.append(rule)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self.rules)
            self.rules = [r for r in self.rules if r.id != rule_id]
            return len(self.rules) < before

    def set_channels(self, ch: Channels):
        self.channels = ch

    # ---- matching ----
    def _matches(self, ev: Dict[str, Any], rule: WatchRule) -> bool:
        if not rule.enabled:
            return False
        if _SEV_RANK.get(ev.get("severity"), 0) < _SEV_RANK.get(rule.min_severity, 0):
            return False
        if rule.types and ev.get("type") not in rule.types:
            return False
        if rule.region:
            hay = f"{ev.get('title','')} {ev.get('country','')}".lower()
            if rule.region.lower() not in hay:
                return False
        return True

    # ---- dispatch ----
    def _format(self, ev: Dict[str, Any], rule: WatchRule) -> str:
        mag = f" M{ev['magnitude']}" if (ev.get("source") == "USGS" and ev.get("magnitude")) else ""
        loc = ev.get("country") or ev.get("title") or "unknown location"
        return (f"🚨 [{ev.get('severity','').upper()}] {ev.get('type','Event')}{mag} — {loc}\n"
                f"{ev.get('title','')}\n"
                f"Source: {ev.get('source','')} · matched rule “{rule.name}”"
                + (f"\n{ev.get('url')}" if ev.get("url") else ""))

    def _send_webhook(self, text: str, ev: Dict[str, Any]) -> None:
        url = self.channels.webhook_url
        if not url:
            raise RuntimeError("no webhook configured")
        # keys cover Slack ("text"), Discord ("content") and generic consumers
        payload = {"text": text, "content": text, "event": ev}
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()

    def _send_email(self, text: str, subject: str) -> None:
        to = self.channels.email_to
        host = os.environ.get("SMTP_HOST")
        if not (to and host):
            raise RuntimeError("email not configured")
        msg = MIMEText(text)
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "alerts@crisis-coordinator"))
        msg["To"] = to
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)

    def dispatch(self, ev: Dict[str, Any], rule: WatchRule) -> Alert:
        text = self._format(ev, rule)
        alert = Alert(rule_name=rule.name, event=ev)
        if self.channels.webhook_url:
            try:
                self._send_webhook(text, ev)
                alert.delivered.append("webhook")
            except Exception as e:
                alert.errors.append(f"webhook: {e}")
        if self.channels.email_to and os.environ.get("SMTP_HOST"):
            try:
                self._send_email(text, f"[{ev.get('severity')}] {ev.get('type')} — {ev.get('country') or ev.get('title')}")
                alert.delivered.append("email")
            except Exception as e:
                alert.errors.append(f"email: {e}")
        if not self.channels.webhook_url and not (self.channels.email_to and os.environ.get("SMTP_HOST")):
            alert.delivered.append("in-app")   # always at least logged in the UI
        with self._lock:
            self.alerts.insert(0, alert)
            self.alerts = self.alerts[:100]
        return alert

    # ---- the poll cycle ----
    def poll(self) -> int:
        events = live_feeds.get_all_events(min_magnitude=2.5)
        ids = {e.get("id") for e in events if e.get("id")}
        fired = 0
        if not self.seeded:
            # first run: remember the backlog, don't alert on it
            self.seen = ids
            self.seeded = True
        else:
            new_events = [e for e in events if e.get("id") and e["id"] not in self.seen]
            for ev in new_events:
                for rule in list(self.rules):
                    if self._matches(ev, rule):
                        self.dispatch(ev, rule)
                        fired += 1
                        break   # one alert per event
            self.seen |= ids
            # keep the seen-set bounded
            if len(self.seen) > 5000:
                self.seen = ids
        self.last_poll = _now()
        self.poll_count += 1
        return fired

    def status(self) -> Dict[str, Any]:
        return {
            "seeded": self.seeded,
            "last_poll": self.last_poll,
            "poll_count": self.poll_count,
            "watching": len([r for r in self.rules if r.enabled]),
            "rules": len(self.rules),
            "alerts": len(self.alerts),
            "channels": {
                "webhook": bool(self.channels.webhook_url),
                "email": bool(self.channels.email_to and os.environ.get("SMTP_HOST")),
            },
        }


ENGINE = AlertEngine()
