"""
Pluggable LLM layer.

Design goal: the platform must run "for everyone" with NO API key — every agent
has a deterministic heuristic path. When an Anthropic API key is present
(ANTHROPIC_API_KEY), agents can optionally call Claude for richer reasoning
(structured extraction, narrative SitReps). The rest of the system never depends
on it.
"""
from __future__ import annotations
import os
import json
from typing import Optional, Dict, Any

# Latest Claude model — fast + capable for structured humanitarian reasoning.
DEFAULT_MODEL = os.environ.get("CRISIS_LLM_MODEL", "claude-sonnet-4-6")


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _client():
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


def complete(system: str, user: str, max_tokens: int = 1024,
             model: Optional[str] = None) -> Optional[str]:
    """Return text completion, or None if no LLM is configured/available."""
    if not llm_available():
        return None
    client = _client()
    if client is None:
        return None
    try:
        msg = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")
    except Exception:
        return None


def complete_json(system: str, user: str, max_tokens: int = 1024) -> Optional[Dict[str, Any]]:
    """Ask the model for JSON and parse it; None on any failure."""
    text = complete(
        system + " Respond ONLY with a single valid JSON object, no prose, no code fences.",
        user, max_tokens=max_tokens,
    )
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def status() -> Dict[str, Any]:
    return {
        "llm_enabled": llm_available(),
        "model": DEFAULT_MODEL if llm_available() else None,
        "mode": "claude" if llm_available() else "heuristic",
    }
