"""
Shareable OSOCC briefing package.

Renders a self-contained HTML document structured so an operator (or anyone they
forward it to) can answer three questions in under 30 seconds:
  1. WHAT HAPPENED         — summary + grounded key figures
  2. WHO OWNS WHAT NEXT     — 3W cluster tasking + logistics options (with ack)
  3. WHAT IS STILL UNCERTAIN — confidence, reasons, and the open-questions list

Plus an evidence appendix, operating context, and the decision log. Printable to
PDF straight from the browser.
"""
from __future__ import annotations
import html
from .models import Incident

_CSS = """
:root{--ink:#0e1726;--mut:#5f7197;--line:#d8e0ec;--crit:#d11d2a;--high:#d97206;--mod:#b8901a;--low:#1f9d57;--acc:#1d7fb0}
*{box-sizing:border-box}body{font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);max-width:900px;margin:24px auto;padding:0 22px}
h1{font-size:23px;margin:0 0 4px}h2{font-size:15px;text-transform:uppercase;letter-spacing:.5px;color:var(--acc);border-bottom:2px solid var(--line);padding-bottom:5px;margin:26px 0 12px}
.sub{color:var(--mut);font-size:12.5px}.badges{margin:12px 0}
.badge{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:4px 11px;border-radius:5px;color:#fff;margin-right:7px}
.sev-Critical{background:var(--crit)}.sev-High{background:var(--high)}.sev-Moderate{background:var(--mod)}.sev-Low{background:var(--low)}
.conf-Confirmed{background:var(--low)}.conf-Probable{background:var(--high)}.conf-Unverified{background:#6b7280}
.metrics{display:flex;gap:26px;margin:14px 0;flex-wrap:wrap}.metrics div{font-size:12px;color:var(--mut)}.metrics b{display:block;font-size:19px;color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:8px 0}th{text-align:left;background:#f1f5fa;padding:7px 8px;border:1px solid var(--line);font-size:11px;text-transform:uppercase;color:var(--mut)}
td{padding:7px 8px;border:1px solid var(--line);vertical-align:top}
.kfig{display:flex;gap:22px;flex-wrap:wrap;margin:6px 0}.kfig div{min-width:130px}.kfig b{display:block;font-size:18px}.kfig span{font-size:11px;color:var(--mut)}
ul{margin:6px 0;padding-left:20px}li{margin:3px 0}.unk{color:var(--mut);font-style:italic}
.q{background:#fbf7ec;border-left:3px solid var(--mod);padding:8px 11px;margin:7px 0;border-radius:0 5px 5px 0}
.q b{display:block}.q span{font-size:11.5px;color:var(--mut)}
.ev{font-size:12px;border-left:2px solid var(--line);padding:4px 0 4px 10px;margin:5px 0}.ev .s{color:var(--acc);font-weight:600}
.ack-Accepted{color:var(--low);font-weight:700}.ack-Rejected{color:var(--crit);font-weight:700}.ack-Amended{color:var(--high);font-weight:700}.ack-Proposed{color:var(--mut)}
.foot{margin-top:30px;font-size:11px;color:var(--mut);border-top:1px solid var(--line);padding-top:10px}
.caveat{background:#fdeced;border:1px solid #f3c0c4;border-radius:6px;padding:10px 13px;margin:10px 0;font-size:12.5px}
@media print{body{margin:0}h2{break-after:avoid}table,.q{break-inside:avoid}}
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _fig(val, label):
    if val is None:
        return f'<div><b class="unk">not estimated</b><span>{_e(label) or "—"}</span></div>'
    return f'<div><b>{val:,}</b><span>{_e(label) or ""}</span></div>'


def render_briefing(inc: Incident) -> str:
    di = inc.incident
    a = inc.assessment
    co = inc.coordination
    lo = inc.logistics
    cf = inc.confidence
    ctx = inc.context or {}
    m = inc.metrics or {}

    sev = a.severity_score if a else "—"
    conf = cf.level if cf else "Unverified"

    # header
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
             f"<title>ORBIT Briefing — {_e(di.disaster_type)} · {_e(di.location)}</title>",
             f"<style>{_CSS}</style></head><body>"]
    parts.append(f"<h1>{_e(di.disaster_type)} — {_e(di.location)}</h1>")
    parts.append(f"<div class='sub'>ORBIT OSOCC Briefing · incident {_e(inc.id)} · "
                 f"generated {_e(inc.updated_at)}</div>")
    parts.append("<div class='badges'>"
                 f"<span class='badge sev-{_e(sev)}'>Severity: {_e(sev)}</span>"
                 f"<span class='badge conf-{_e(conf)}'>Confidence: {_e(conf)}"
                 f"{f' ({cf.score}/100)' if cf else ''}</span></div>")
    parts.append("<div class='metrics'>"
                 f"<div><b>{_e(m.get('time_to_brief_seconds','—'))}s</b>time to briefing</div>"
                 f"<div><b>{_e(m.get('open_questions','—'))}</b>open questions</div>"
                 f"<div><b>{_e(m.get('evidence_count','—'))}</b>evidence items</div>"
                 f"<div><b>{_e(len(co.three_w) if co else 0)}</b>cluster taskings</div></div>")

    if cf and cf.level == "Unverified":
        parts.append("<div class='caveat'><b>⚠ Low confidence.</b> This picture is not yet "
                     "corroborated by independent sources — treat figures as provisional and "
                     "prioritise verification before committing major resources.</div>")

    # §1 WHAT HAPPENED
    parts.append("<h2>1 · What happened</h2>")
    if a:
        parts.append(f"<p>{_e(a.severity_basis)}.</p>")
        parts.append("<div class='kfig'>"
                     + _fig(a.affected_population, a.affected_label or "people affected")
                     + _fig(a.displaced_estimate, a.displaced_label or "displaced")
                     + (f"<div><b>{a.fatalities_label or a.fatalities_estimate}</b><span>casualties</span></div>"
                        if (a.fatalities_estimate is not None or a.fatalities_label)
                        else '<div><b class="unk">not estimated</b><span>casualties</span></div>')
                     + f"<div><b>{_e(a.golden_hours)}h</b><span>life-saving window</span></div>"
                     + "</div>")
        if ctx.get("weather"):
            w = ctx["weather"]
            parts.append(f"<p class='sub'>Operating conditions: {_e(w['conditions'])}, "
                         f"{_e(w['temperature_c'])}°C, wind {_e(w['wind_kmh'])} km/h, "
                         f"precipitation {_e(w['precipitation_mm'])} mm.</p>")
        sat = ctx.get("satellite")
        if sat:
            parts.append(f"<a href='{_e(sat.get('worldview'))}'><img src='{_e(sat['url'])}' "
                         f"style='width:100%;max-width:520px;border-radius:8px;border:1px solid var(--line)'/></a>"
                         f"<p class='sub'>Near-real-time {_e(sat['layer'])} satellite imagery "
                         f"({_e(sat['date'])}) · NASA GIBS.</p>")
        sm = ctx.get("shakemap")
        if sm:
            parts.append(f"<a href='{_e(sm['url'])}'><img src='{_e(sm['url'])}' "
                         f"style='width:100%;max-width:420px;border-radius:8px;border:1px solid var(--line)'/></a>"
                         f"<p class='sub'>USGS ShakeMap — modelled ground shaking intensity.</p>")
        fires = ctx.get("fires")
        if fires and fires.get("count"):
            parts.append(f"<p class='sub'><b>Active fires:</b> {_e(fires['count'])} FIRMS detections "
                         f"within ~150 km (nearest {_e(fires.get('nearest_km'))} km, max FRP "
                         f"{_e(fires.get('max_frp'))} MW).</p>")
        aq = ctx.get("air_quality")
        if aq and aq.get("pm25") is not None:
            parts.append(f"<p class='sub'><b>Air quality:</b> PM2.5 {_e(aq['pm25'])} µg/m³ "
                         f"({_e(aq['band'])}) — OpenAQ.</p>")
        at = ctx.get("air_traffic")
        if at and at.get("count"):
            parts.append(f"<p class='sub'>Airspace: {_e(at['count'])} aircraft tracked within "
                         f"~150 km ({_e(at['airborne'])} airborne) — OpenSky.</p>")

    # §2 WHO OWNS WHAT NEXT
    parts.append("<h2>2 · Who owns what next</h2>")
    if co:
        parts.append("<table><tr><th>Sector</th><th>Lead</th><th>Activity</th>"
                     "<th>Status</th><th>Why (evidence)</th></tr>")
        for e in co.three_w:
            ack = e.ack.status if e.ack else "Proposed"
            badge = f"<span class='ack-{_e(ack)}'>{_e(ack)}</span>"
            parts.append(f"<tr><td>{_e(e.sector)}</td><td>{_e(e.who)}</td><td>{_e(e.what)}</td>"
                         f"<td>{badge}{f'<br><span class=sub>{_e(e.ack.note)}</span>' if e.ack and e.ack.note else ''}</td>"
                         f"<td class='sub'>{_e(e.rationale)}</td></tr>")
        parts.append("</table>")

    # logistics options
    if lo:
        parts.append("<p><b>Logistics:</b> " + _e(lo.summary) + "</p>")
        airports = ctx.get("airports", [])
        if airports:
            opts = "; ".join(f"{_e(ap['name'])} ({_e(ap['distance_km'])} km"
                             + (f", {_e(ap['iata'])}" if ap.get('iata') else "") + ")"
                             for ap in airports[:3])
            parts.append(f"<p class='sub'><b>Relief access (nearest aerodromes):</b> {opts}</p>")
        ports = ctx.get("ports", [])
        if ports:
            popts = "; ".join(f"{_e(p['name'])} ({_e(p['distance_km'])} km)" for p in ports[:3])
            parts.append(f"<p class='sub'><b>Relief access (nearest seaports):</b> {popts}</p>")
        ves = ctx.get("vessels")
        if ves and ves.get("count"):
            parts.append(f"<p class='sub'><b>Maritime:</b> {_e(ves['count'])} vessels within ~80 km "
                         f"({_e(ves['moving'])} under way) — potential SAR/relief assets (VesselAPI).</p>")
        conf = ctx.get("conflict")
        if conf and conf.get("available") and conf.get("events"):
            parts.append(f"<div class='caveat'><b>⚠ Security context:</b> {_e(len(conf['events']))} recent "
                         f"conflict/unrest events within ~300 km (ACLED) — factor into access &amp; staff safety.</div>")

    # §3 WHAT IS STILL UNCERTAIN
    parts.append("<h2>3 · What is still uncertain</h2>")
    if cf:
        parts.append("<p><b>Confidence basis:</b></p><ul>"
                     + "".join(f"<li>{_e(r)}</li>" for r in cf.reasons) + "</ul>")
    if inc.open_questions:
        parts.append("<p><b>Unanswered questions (resolve to reduce uncertainty):</b></p>")
        for q in inc.open_questions:
            if q.status == "Answered":
                parts.append(f"<div class='q' style='border-color:var(--low)'><b>✓ {_e(q.question)}</b>"
                             f"<span>{_e(q.answer)}</span></div>")
            else:
                parts.append(f"<div class='q'><b>{_e(q.question)}</b><span>{_e(q.why)}</span></div>")

    # context: medical capacity
    hosp = ctx.get("hospitals", [])
    if hosp:
        parts.append("<h2>Operating context · medical</h2>")
        parts.append(f"<p class='sub'>{len(hosp)} hospital(s) within 60 km (OpenStreetMap):</p><ul>"
                     + "".join(f"<li>{_e(h['name'])} — {_e(h['distance_km'])} km</li>" for h in hosp[:6])
                     + "</ul>")

    # evidence appendix
    if inc.evidence:
        parts.append("<h2>Evidence appendix</h2>")
        for ev in inc.evidence:
            link = f" <a href='{_e(ev.url)}'>↗</a>" if ev.url else ""
            parts.append(f"<div class='ev'><span class='s'>{_e(ev.source)}</span> "
                         f"[{_e(ev.kind)}]: {_e(ev.statement)}{link}</div>")

    # decision log
    if inc.decisions or inc.comments:
        parts.append("<h2>Decision log &amp; notes</h2>")
        for d in inc.decisions:
            parts.append(f"<p><b>{_e(d.decision)}</b> — {_e(d.rationale)} "
                         f"<span class='sub'>({_e(d.author)}, {_e(d.at)})</span></p>")
        for c in inc.comments:
            parts.append(f"<p class='sub'>💬 {_e(c.author)}: {_e(c.text)} ({_e(c.at)})</p>")

    parts.append("<div class='foot'>Generated by ORBIT — Operational Response, Briefing &amp; "
                 "Incident Triage. Decision-support only; figures are sourced or marked "
                 "“not estimated”. Verify against ground truth before operational action.</div>")
    parts.append("</body></html>")
    return "".join(parts)


def clean_html_for_pdf(html_str: str) -> str:
    """Preprocess HTML/CSS for xhtml2pdf compatibility (resolves CSS variables)."""
    replacements = {
        "var(--ink)": "#0e1726",
        "var(--mut)": "#5f7197",
        "var(--line)": "#d8e0ec",
        "var(--crit)": "#d11d2a",
        "var(--high)": "#d97206",
        "var(--mod)": "#b8901a",
        "var(--low)": "#1f9d57",
        "var(--acc)": "#1d7fb0"
    }
    for var_name, hex_color in replacements.items():
        html_str = html_str.replace(var_name, hex_color)
    return html_str


def render_briefing_pdf(inc: Incident) -> bytes:
    """Renders the briefing HTML, cleans it, and generates a PDF binary payload."""
    import io
    from xhtml2pdf import pisa
    
    html_content = render_briefing(inc)
    cleaned_html = clean_html_for_pdf(html_content)
    
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(cleaned_html, dest=pdf_buffer)
    if pisa_status.err:
        raise RuntimeError(f"PDF generation failed: {pisa_status.err}")
        
    return pdf_buffer.getvalue()
