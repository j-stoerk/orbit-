/* ===================================================================
   UNDAC Crisis Coordinator — frontend controller
   =================================================================== */
const API = "";
let currentIncident = null;   // last pipeline result (full Incident)
let liveEvents = [];
let filteredEvents = [];      // events currently shown (after layer/search/sev filters)
let evSearch = "";
let evSevFilter = "all";
let selectedEventId = null;
let activeLiveEvent = null;    // live event the report was generated from (exact coords)
const SEV_RANK = { Critical: 4, High: 3, Moderate: 2, Low: 1 };

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());

const SAMPLES = [
  { l: "Istanbul EQ", t: "Magnitude 7.1 earthquake struck near Istanbul. Many buildings collapsed, roughly 20,000 people affected, 400 injured. Need medics, water and rescue teams urgently." },
  { l: "Manila flood", t: "Severe flooding in Manila after typhoon rains. Whole districts submerged, 50,000 people affected, families stranded on rooftops. Need rescue boats, clean water and food." },
  { l: "Mozambique cyclone", t: "Tropical cyclone made landfall near Beira, Mozambique. Widespread wind and storm-surge damage, 80,000 affected, power and communications down. Shelter and food needed." },
  { l: "DRC volcano", t: "Volcanic eruption near Goma. Lava flows approaching the city, ashfall heavy, 30,000 people evacuating. Need masks, water and buses for evacuation." },
];

/* --------------------------------------------------------------- boot */
window.addEventListener("DOMContentLoaded", () => {
  CrisisGlobe.init($("#globe"));
  CrisisGlobe.setOnClick(onEventClick);
  startClock();
  wireUI();
  renderSamples();
  loadHealth();
  refreshFeeds();
  loadResources();
  loadHazards();
  refreshAlertBadge();
  setInterval(refreshFeeds, 120000);       // auto-refresh live feeds every 2 min
  setInterval(refreshAlertBadge, 60000);   // refresh alert badge every minute
});

/* ------------------------------------------------------------ UI wiring */
function wireUI() {
  // collapsible panels
  $$(".panel-head[data-collapse]").forEach((h) =>
    h.addEventListener("click", () => h.parentElement.classList.toggle("collapsed")));

  // top nav views
  $$(".nav-btn").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));

  // brief tabs
  $$(".brief-tabs .tab").forEach((t) => t.addEventListener("click", () => {
    $$(".brief-tabs .tab").forEach((x) => x.classList.remove("active"));
    $$(".tab-pane").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#tab-" + t.dataset.tab).classList.add("active");
  }));

  $("#runBtn").addEventListener("click", runPipeline);
  // editing the report manually detaches it from the live event's exact coords
  $("#reportInput").addEventListener("input", () => { activeLiveEvent = null; $("#runBtn").classList.remove("armed"); });
  $("#refreshBtn").addEventListener("click", refreshFeeds);
  $("#briefClose").addEventListener("click", closeBrief);
  $("#magRange").addEventListener("input", (e) => { $("#magVal").textContent = e.target.value; });
  $("#magRange").addEventListener("change", refreshFeeds);
  ["layerEq", "layerGdacs", "layerRw"].forEach((id) =>
    $("#" + id).addEventListener("change", () => renderEvents()));

  // live-events search + severity filter
  $("#evSearch").addEventListener("input", (e) => { evSearch = e.target.value.toLowerCase(); renderEventList(); });
  $$("#evSevFilter button").forEach((b) => b.addEventListener("click", () => {
    $$("#evSevFilter button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    evSevFilter = b.dataset.sev;
    renderEventList();
  }));
}

function switchView(v) {
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((x) => x.classList.remove("active"));
  $("#" + v + "View").classList.add("active");
  if (v === "incidents") loadIncidents();
  if (v === "resources") loadResources();
  if (v === "monitor") loadMonitor();
}

function renderSamples() {
  $("#sampleRow").innerHTML = SAMPLES.map((s, i) =>
    `<span class="chip" data-i="${i}">${esc(s.l)}</span>`).join("");
  $$("#sampleRow .chip").forEach((c) =>
    c.addEventListener("click", () => { $("#reportInput").value = SAMPLES[c.dataset.i].t; }));
}

/* ------------------------------------------------------------- health */
async function loadHealth() {
  try {
    const h = await (await fetch(API + "/api/health")).json();
    const el = $("#llmStatus");
    if (h.llm && h.llm.llm_enabled) {
      el.textContent = "●  Claude " + (h.llm.model || "");
      el.style.color = "var(--low)";
    } else {
      el.textContent = "●  heuristic engine";
      el.style.color = "var(--mod)";
      el.title = "Set ANTHROPIC_API_KEY to enable Claude reasoning";
    }
  } catch (e) { /* ignore */ }
}

/* -------------------------------------------------------- live feeds */
async function refreshFeeds() {
  const mag = $("#magRange").value;
  $("#feedMeta").textContent = "loading feeds…";
  try {
    const r = await (await fetch(`${API}/api/events?min_magnitude=${mag}`)).json();
    liveEvents = r.events || [];
    renderEvents();
    $("#feedMeta").textContent = `${liveEvents.length} events · updated ${new Date().toLocaleTimeString()}`;
    $("#eventCount").textContent = `${liveEvents.length} live events`;
  } catch (e) {
    $("#feedMeta").textContent = "feed error: " + e.message;
  }
}

function renderEvents() {
  const showEq = $("#layerEq").checked, showG = $("#layerGdacs").checked, showR = $("#layerRw").checked;
  filteredEvents = liveEvents.filter((e) =>
    (e.source === "USGS" && showEq) ||
    (e.source === "GDACS" && showG) ||
    (e.source === "ReliefWeb" && showR));
  CrisisGlobe.setEvents(filteredEvents);
  // pulse rings on Critical + High events
  CrisisGlobe.setActiveRings(filteredEvents.filter((e) => SEV_RANK[e.severity] >= 3));
  renderEventList();
}

// Ranked, searchable triage list of live events in the sidebar.
function renderEventList() {
  let list = filteredEvents.slice();
  if (evSevFilter !== "all") list = list.filter((e) => e.severity === evSevFilter);
  if (evSearch) list = list.filter((e) =>
    `${e.title} ${e.type} ${e.source} ${e.country || ""}`.toLowerCase().includes(evSearch));
  // sort by severity then magnitude/recency
  list.sort((a, b) => (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0)
    || (Number(b.magnitude) || 0) - (Number(a.magnitude) || 0));

  $("#evCount").textContent = list.length;
  const el = $("#evList");
  if (!list.length) { el.innerHTML = `<div class="ev-empty">No matching live events.</div>`; return; }
  el.innerHTML = list.map((e, i) => {
    const mag = (e.source === "USGS" && e.magnitude) ? "M" + e.magnitude : (e.severity || "").slice(0, 4);
    return `<div class="ev-item ${e.id === selectedEventId ? "selected" : ""}" data-id="${esc(e.id)}">
      <span class="ev-sev" style="background:${CrisisGlobe.severityColor(e.severity)}"></span>
      <div class="ev-main">
        <div class="ev-title">${esc((e.title || e.type || "Event").slice(0, 60))}</div>
        <div class="ev-meta">${esc(e.type)} · ${esc(e.source)}${e.country ? " · " + esc(e.country) : ""}</div>
      </div>
      <span class="ev-mag">${esc(mag)}</span>
      <button class="ev-run" title="Run agent team on this event">▶</button>
    </div>`;
  }).join("");
  // wire rows
  $$("#evList .ev-item").forEach((row) => {
    const ev = list.find((x) => x.id === row.dataset.id);
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("ev-run")) return;
      onEventClick(ev);
    });
    row.querySelector(".ev-run").addEventListener("click", (e) => {
      e.stopPropagation();
      onEventClick(ev);
      runPipeline();
    });
  });
}

/* ---------------------------------------------- clicking a live event */
function onEventClick(d) {
  selectedEventId = d.id;
  activeLiveEvent = d;            // remember exact coords for the pipeline run
  $("#runBtn").classList.add("armed");   // nudge the single run button
  CrisisGlobe.select(d.id);
  CrisisGlobe.focus(d.lat, d.lon, 0.7);
  renderEventList();
  // Prefill intake with an auto-generated report so the operator can run the
  // agent team on a real, live event in one click.
  $("#reportInput").value = buildReportFromEvent(d);
  showLiveEventBrief(d);
}

function buildReportFromEvent(d) {
  const mag = d.magnitude ? `Magnitude ${d.magnitude} ` : "";
  const loc = d.title || d.country || "the affected area";
  const place = d.country ? ` near ${d.country}` : "";
  return `${mag}${d.type || "disaster"} reported: ${loc}${place}. ` +
    `Source ${d.source}, severity ${d.severity}. Assess needs and coordinate response.`;
}

function showLiveEventBrief(d) {
  $("#briefEmpty").hidden = true;
  $("#briefContent").hidden = false;
  $("#briefSev").className = "sev-badge sev-" + (d.severity || "Moderate");
  $("#briefSev").textContent = d.severity || "—";
  $("#briefConf").style.display = "none";
  $("#briefExport").onclick = null;
  $("#briefTitle").textContent = d.title || d.type;
  $("#briefSub").textContent = `${d.type || ""} · ${d.source} ${d.magnitude ? "· M" + d.magnitude : ""} ${d.country ? "· " + d.country : ""}`;
  $("#tab-overview").innerHTML = `
    <div class="kv"><span>Type</span><b>${esc(d.type)}</b></div>
    <div class="kv"><span>Severity</span><b>${esc(d.severity)}</b></div>
    ${d.magnitude ? `<div class="kv"><span>Magnitude</span><b>${esc(d.magnitude)}</b></div>` : ""}
    ${d.depth_km != null ? `<div class="kv"><span>Depth</span><b>${esc(d.depth_km)} km</b></div>` : ""}
    <div class="kv"><span>Coordinates</span><b>${d.lat?.toFixed(2)}, ${d.lon?.toFixed(2)}</b></div>
    ${d.time ? `<div class="kv"><span>Time</span><b>${esc(d.time)}</b></div>` : ""}
    <div class="kv"><span>Source</span><b>${esc(d.source)}</b></div>
    ${d.url ? `<div style="margin-top:12px"><a href="${esc(d.url)}" target="_blank" style="color:var(--accent)">Open source report →</a></div>` : ""}
    <div class="run-hint">↻ Report pre-filled from this event — press <b>Activate Agent Team</b> (left panel) to run.</div>`;
  ["sitrep", "3w", "logistics", "alerts", "log"].forEach((t) =>
    $("#tab-" + t).innerHTML = `<div class="empty-state">Run the agent team to generate this product.</div>`);
  // live news & social for the clicked event — no pipeline run needed
  loadMedia(d.country || d.title, d.type);
  // live vessel routes near the clicked event (cleared if none / inland)
  if (d.lat != null) loadVesselTracks(d.lat, d.lon); else CrisisGlobe.setVesselTracks([]);
}

/* =================================================================
   PIPELINE — live WebSocket streaming of the agent team
   ================================================================= */
let _msgQueue = [], _playing = false, _missionCoords = null, _missionSeverity = "High";

function runPipeline() {
  const report = $("#reportInput").value.trim();
  if (!report) { $("#reportInput").focus(); return; }
  const btn = $("#runBtn");
  btn.disabled = true;
  btn.classList.remove("armed");
  btn.innerHTML = '<span class="spinner"></span>Agents working…';
  clearConsole();
  CrisisGlobe.clearMission();
  _msgQueue = []; _playing = false; _missionCoords = null; _missionSeverity = "High";
  showBriefWorking();
  logLine("Orchestrator", "Connecting to OSOCC agent team…");

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/run`);
  const autoApprove = !$("#hitlToggle").checked;
  const finish = () => { btn.disabled = false; btn.innerHTML = "▶  Activate Agent Team"; };

  // if the report came from a live event, send its exact coordinates (precise
  // fly-to) and an exposure reference so the backend grounds the assessment in
  // real USGS PAGER / GDACS data instead of estimating
  const payload = { report, auto_approve: autoApprove, commit_inventory: true };
  if (activeLiveEvent && activeLiveEvent.lat != null) {
    const e = activeLiveEvent;
    payload.lat = e.lat;
    payload.lon = e.lon;
    payload.location = e.country || e.title || null;
    if (e.source === "USGS" && e.detail) {
      payload.exposure_ref = { source: "USGS", detail: e.detail };
    } else if (e.source === "GDACS" && e.gdacs_eventtype) {
      payload.exposure_ref = { source: "GDACS", gdacs_eventtype: e.gdacs_eventtype, gdacs_eventid: e.gdacs_eventid };
    }
  }
  ws.onopen = () => ws.send(JSON.stringify(payload));
  // Queue messages and play them out at a watchable pace so the mission
  // visibly unfolds on the globe instead of completing in a single frame.
  ws.onmessage = (ev) => { _msgQueue.push(JSON.parse(ev.data)); playNext(finish); };
  ws.onerror = () => { logLine("Error", "WebSocket error — is the server running?"); finish(); };
}

// milestone steps carry structured payloads and drive globe visuals → slower
function isMilestone(m) {
  const d = m.data || {};
  return d.incident || d.assessment || d.coordination || d.logistics || d.notifications
    || m.agent === "Done" || m.agent === "HITL" || m.agent === "Alerts";
}

function playNext(finish) {
  if (_playing) return;
  const m = _msgQueue.shift();
  if (!m) return;
  _playing = true;
  // never let a render error stall the queue — log it and keep going
  try { processMsg(m, finish); }
  catch (err) { console.error("processMsg error:", err); logLine("Error", "UI: " + err.message); }
  const delay = isMilestone(m) ? 950 : 110;
  setTimeout(() => { _playing = false; playNext(finish); }, delay);
}

function processMsg(m, finish) {
  if (m.agent === "Done") {
    currentIncident = m.data.incident;
    renderBrief(currentIncident);
    loadResources();
    logLine("Orchestrator", "✓ Operational brief ready (right panel).");
    finish();
    return;
  }
  if (m.agent === "Error") { logLine("Error", m.message); briefError(m.message); finish(); return; }
  logLine(m.agent, m.message);
  // keep the working brief informed of progress
  const sub = $("#briefSub");
  if (sub && $("#briefContent") && !$("#briefContent").hidden) sub.textContent = `${m.agent}: ${m.message}`.slice(0, 90);
  driveGlobe(m);
}

// immediate brief shell shown while the agents work (so the panel is never blank)
function showBriefWorking() {
  $("#briefEmpty").hidden = true;
  $("#briefContent").hidden = false;
  $("#briefSev").className = "sev-badge";
  $("#briefSev").textContent = "···";
  $("#briefTitle").textContent = "Agent team activated";
  $("#briefSub").textContent = "Working…";
  $("#briefConf").style.display = "none";
  $("#tab-overview").innerHTML = `
    <div class="working"><span class="spinner"></span> Agent team working — the operational brief will fill in below.</div>
    <div class="brief-stream" id="briefStream"></div>`;
  ["sitrep", "3w", "logistics", "alerts", "media", "log"].forEach((t) => {
    const el = $("#tab-" + t); if (el) el.innerHTML = `<div class="working"><span class="spinner"></span> Working…</div>`;
  });
  $$(".brief-tabs .tab").forEach((x) => x.classList.remove("active"));
  $$(".tab-pane").forEach((x) => x.classList.remove("active"));
  $(".brief-tabs .tab").classList.add("active");
  $("#tab-overview").classList.add("active");
}

function briefError(msg) {
  $("#tab-overview").innerHTML = `<div class="working" style="color:var(--crit)">Pipeline error: ${esc(msg)}</div>`;
}

// translate an agent milestone into a globe animation
function driveGlobe(m) {
  const d = m.data || {};
  if (d.incident && d.incident.coordinates && d.incident.coordinates.lat != null) {
    const c = d.incident.coordinates;
    _missionCoords = c;
    CrisisGlobe.missionStart(c.lat, c.lon, _missionSeverity, d.incident.location || d.incident.disaster_type);
  }
  if (d.assessment) {
    _missionSeverity = d.assessment.severity_score || _missionSeverity;
    CrisisGlobe.scan(_missionSeverity);
  }
  if (d.coordination) {
    CrisisGlobe.coordination(d.coordination.lead_clusters || []);
  }
  if (d.logistics) {
    CrisisGlobe.logistics();
  }
  if (d.notifications) {
    CrisisGlobe.broadcast(_missionSeverity);
  }
}

/* ----------- live agent stream (rendered inside the brief) ----------- */
function clearConsole() { const s = $("#briefStream"); if (s) s.innerHTML = ""; }
function logLine(who, msg) {
  const c = $("#briefStream");
  if (!c) return;                 // no-op when no run is streaming
  const row = document.createElement("div");
  row.className = "log agent-" + who;
  row.innerHTML = `<span class="who">${esc(who)}</span><span class="msg">${esc(msg)}</span>`;
  c.appendChild(row);
  c.scrollTop = c.scrollHeight;
}

/* =================================================================
   OPERATIONAL BRIEF rendering
   ================================================================= */
const OPERATOR = "operator";
function renderBrief(inc) {
  currentIncident = inc;
  const di = inc.incident, a = inc.assessment, co = inc.coordination, lo = inc.logistics;
  const cf = inc.confidence, ctx = inc.context || {}, m = inc.metrics || {};
  $("#briefEmpty").hidden = true;
  $("#briefContent").hidden = false;

  $("#briefSev").className = "sev-badge sev-" + (a ? a.severity_score : "Moderate");
  $("#briefSev").textContent = a ? a.severity_score : "—";
  const cb = $("#briefConf");
  if (cf) { cb.style.display = ""; cb.className = "conf-badge conf-" + cf.level; cb.textContent = `${cf.level} ${cf.score}`; }
  else cb.style.display = "none";
  $("#briefTitle").textContent = `${di.disaster_type} · ${di.location}`;
  $("#briefSub").textContent = inc.sitrep ? inc.sitrep.headline : `Incident ${inc.id}`;
  $("#briefExport").onclick = () => window.open(`${API}/api/incidents/${inc.id}/briefing`, "_blank");

  if (di.coordinates && di.coordinates.lat != null) CrisisGlobe.focus(di.coordinates.lat, di.coordinates.lon, 1.0);

  const figure = (val, label) => val == null
    ? `<b class="unk">not estimated</b>${label ? `<span class="prov">${esc(label)}</span>` : ""}`
    : `<b>${fmt(val)}</b>${label ? `<span class="prov">${esc(label)}</span>` : ""}`;

  /* ---------- BRIEFING: what happened + what's uncertain (the 30-second view) ---------- */
  const approveBar = (inc.approved === null)
    ? `<div class="approve-bar"><span>⚠ Resources awaiting human approval (HITL)</span>
        <button onclick="approveIncident('${inc.id}')">Approve & Commit</button></div>` : "";
  const wx = ctx.weather;
  const openQs = (inc.open_questions || []).filter((q) => q.status === "Open");
  const ansQs = (inc.open_questions || []).filter((q) => q.status === "Answered");
  $("#tab-overview").innerHTML = approveBar + `
    <div class="metric-strip">
      <div><b>${m.time_to_brief_seconds != null ? m.time_to_brief_seconds + "s" : "—"}</b><span>to brief</span></div>
      <div><b>${cf ? cf.score : "—"}</b><span>confidence</span></div>
      <div><b>${openQs.length}</b><span>open Qs</span></div>
      <div><b>${(inc.evidence || []).length}</b><span>evidence</span></div>
    </div>

    <div class="brief-sec-h">① What happened</div>
    <div class="kfig">
      ${figure(a && a.affected_population, (a && a.affected_label) || "affected")}
      ${figure(a && a.displaced_estimate, (a && a.displaced_label) || "displaced")}
      ${a && a.fatalities_estimate != null ? figure(a.fatalities_estimate, a.fatalities_label || "casualties")
        : `<b class="unk">${esc((a && a.fatalities_label) || "not estimated")}</b><span class="prov">casualties</span>`}
    </div>
    <p class="basis">${esc(a && a.severity_basis)}.</p>
    ${a && a.data_sources && a.data_sources.length ? `<div class="src-row">${a.data_sources.map((s) =>
        s.url ? `<a class="src" href="${esc(s.url)}" target="_blank">${esc(s.name)} ↗</a>` : `<span class="src">${esc(s.name)}</span>`).join("")}</div>` : ""}
    ${wx ? `<div class="ctx-line">🌤 ${esc(wx.conditions)}, ${esc(wx.temperature_c)}°C · wind ${esc(wx.wind_kmh)} km/h · precip ${esc(wx.precipitation_mm)} mm <span class="prov">Open-Meteo</span></div>` : ""}
    <div class="img-grid">
      ${ctx.satellite ? `<a class="sat-img" href="${esc(ctx.satellite.worldview)}" target="_blank" title="Open in NASA Worldview">
        <img src="${esc(ctx.satellite.url)}" loading="lazy" onerror="this.parentElement.style.display='none'"/>
        <span class="sat-cap">🛰 ${esc(ctx.satellite.date)} <span class="prov">NASA</span></span></a>` : ""}
      ${ctx.shakemap ? `<a class="sat-img" href="${esc(ctx.shakemap.url)}" target="_blank" title="USGS ShakeMap">
        <img src="${esc(ctx.shakemap.url)}" loading="lazy" onerror="this.parentElement.style.display='none'"/>
        <span class="sat-cap">📈 ShakeMap <span class="prov">USGS</span></span></a>` : ""}
      ${ctx.radar ? `<a class="sat-img radar" href="https://www.rainviewer.com" target="_blank" title="Live precipitation radar">
        <img src="${esc(ctx.radar.base_url)}" loading="lazy"/>
        <img class="radar-ov" src="${esc(ctx.radar.radar_url)}" loading="lazy" onerror="this.style.display='none'"/>
        <span class="sat-cap">🌧 Radar <span class="prov">RainViewer</span></span></a>` : ""}
    </div>
    ${ctx.fires && ctx.fires.count ? `<div class="ctx-line ctx-fire">🔥 ${esc(ctx.fires.count)} active fire detections within ~150 km · nearest ${esc(ctx.fires.nearest_km)} km · max FRP ${esc(ctx.fires.max_frp)} MW <span class="prov">NASA FIRMS</span></div>` : ""}
    ${ctx.air_quality && ctx.air_quality.pm25 != null ? `<div class="ctx-line">💨 Air quality PM2.5 ${esc(ctx.air_quality.pm25)} µg/m³ · <b>${esc(ctx.air_quality.band)}</b> <span class="prov">OpenAQ · ${esc(ctx.air_quality.location || "")}</span></div>` : ""}
    ${ctx.air_traffic && ctx.air_traffic.count ? `<div class="ctx-line">✈ ${esc(ctx.air_traffic.count)} aircraft tracked within ~150 km (${esc(ctx.air_traffic.airborne)} airborne) — airspace active <span class="prov">OpenSky</span></div>` : ""}
    ${ctx.vessels && ctx.vessels.count ? `<div class="ctx-line">🚢 ${esc(ctx.vessels.count)} vessels within ~80 km (${esc(ctx.vessels.moving)} under way) · nearest ${esc(ctx.vessels.nearest.name)} ${esc(ctx.vessels.nearest.dist_km)} km — potential maritime assets <span class="prov">VesselAPI</span></div>` : ""}
    ${ctx.conflict && ctx.conflict.available && ctx.conflict.events && ctx.conflict.events.length ? `<div class="ctx-line ctx-fire">⚠ ${esc(ctx.conflict.events.length)} recent conflict/unrest events within ~300 km <span class="prov">ACLED</span></div>` : ""}

    <div class="brief-sec-h">② Who owns what next
      <button class="conf-mini" style="background:var(--accent2);border:none;cursor:pointer" onclick="gotoTab('3w')">manage →</button></div>
    <div class="own-list">
      ${co ? co.three_w.map((e) => `<div class="own-row">
        <span class="own-sector">${esc(e.sector)}</span>
        <span class="own-lead">${esc(e.who)}</span>
        <span class="ack-tag ack-${e.ack ? e.ack.status : "Proposed"}">${e.ack ? e.ack.status : "Proposed"}</span>
      </div>`).join("") : `<div class="ev-empty">No tasking yet.</div>`}
    </div>

    <div class="brief-sec-h">③ What is still uncertain
      <span class="conf-mini conf-${cf ? cf.level : "Unverified"}">${cf ? cf.level : "—"}</span></div>
    ${cf && cf.reasons.length ? `<ul class="reasons">${cf.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
    <div class="q-list">
      ${openQs.length ? openQs.map((q) => `
        <div class="q-card cat-${esc(q.category)}">
          <div class="q-row"><b>${esc(q.question)}</b>
            <button class="q-ans" onclick="answerQuestion('${inc.id}','${q.id}')">Answer</button></div>
          <span>${esc(q.why)}</span>
        </div>`).join("") : `<div class="ev-empty">No open questions.</div>`}
      ${ansQs.map((q) => `<div class="q-card answered"><div class="q-row"><b>✓ ${esc(q.question)}</b></div><span>${esc(q.answer)}</span></div>`).join("")}
    </div>`;

  /* ---------- WHO & TASKING: 3W with accept/reject/amend ---------- */
  $("#tab-3w").innerHTML = co ? `
    <div class="brief-sec-h">② Who owns what next</div>
    <p class="hint">Machine proposals — accept, reject or amend each. Status feeds the briefing package.</p>
    ${co.three_w.map((e) => `
      <div class="task-card ack-${e.ack ? e.ack.status : "Proposed"}">
        <div class="task-top">
          <div><b>${esc(e.sector)}</b> <span class="task-lead">${esc(e.who)}</span></div>
          <span class="ack-tag ack-${e.ack ? e.ack.status : "Proposed"}">${e.ack ? e.ack.status : "Proposed"}</span>
        </div>
        <div class="task-act">${esc(e.what)}</div>
        <div class="task-why">${esc(e.rationale || "")}</div>
        ${e.ack && e.ack.note ? `<div class="task-note">“${esc(e.ack.note)}”${e.ack.by ? " — " + esc(e.ack.by) : ""}</div>` : ""}
        <div class="ack-btns">
          <button class="ack-a" onclick="ackCluster('${inc.id}','${e.id}','Accepted')">Accept</button>
          <button class="ack-r" onclick="ackCluster('${inc.id}','${e.id}','Rejected')">Reject</button>
          <button class="ack-m" onclick="amendCluster('${inc.id}','${e.id}')">Amend</button>
        </div>
      </div>`).join("")}
    <div class="section-title">Coordination gaps</div>
    <ul class="action-list">${co.coordination_gaps.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>
    <div class="section-title">OSOCC tasking</div>
    <ul class="action-list">${co.tasking.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`
    : `<div class="empty-state">No coordination plan.</div>`;

  /* ---------- LOGISTICS ---------- */
  const cell = (v) => v == null ? "—" : fmt(v);
  const air = ctx.airports || [], hosp = ctx.hospitals || [];
  $("#tab-logistics").innerHTML = lo ? `
    <p style="font-size:12px;color:var(--txt-dim)">${esc(lo.summary)}</p>
    <table class="grid"><tr><th>Resource</th><th>Available</th><th>Location</th><th>Req</th><th>Gap</th><th>Status</th></tr>
      ${lo.lines.map((l) => `<tr><td>${esc(l.label || l.item)}</td>
        <td>${fmt(l.available)} ${esc(l.unit || "")}</td>
        <td style="font-size:10px;color:var(--txt-faint)">${l.locations && l.locations.length ? esc(l.locations.join(", ")) : "—"}</td>
        <td>${cell(l.requested)}</td><td>${cell(l.gap)}</td>
        <td class="st-${l.status.replace(/\s/g, "")}">${esc(l.status)}</td></tr>`).join("")}</table>
    ${air.length ? `<div class="section-title">Relief access · nearest aerodromes <span class="sub">OSM</span></div>
      <ul class="action-list">${air.slice(0, 4).map((p) => `<li>${esc(p.name)} — ${esc(p.distance_km)} km${p.iata ? " · " + esc(p.iata) : ""}</li>`).join("")}</ul>` : ""}
    ${(ctx.ports || []).length ? `<div class="section-title">Relief access · nearest seaports <span class="sub">VesselAPI</span></div>
      <ul class="action-list">${ctx.ports.slice(0, 4).map((p) => `<li>${esc(p.name)} — ${esc(p.distance_km)} km${p.unlocode ? " · " + esc(p.unlocode) : ""}${p.country ? " · " + esc(p.country) : ""}</li>`).join("")}</ul>` : ""}
    ${hosp.length ? `<div class="section-title">Medical capacity · nearest hospitals <span class="sub">OSM</span></div>
      <ul class="action-list">${hosp.slice(0, 4).map((h) => `<li>${esc(h.name)} — ${esc(h.distance_km)} km</li>`).join("")}</ul>` : ""}
    <div class="section-title">Procurement recommendations</div>
    <ul class="action-list">${lo.procurement_recommendations.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
    : `<div class="empty-state">No logistics plan.</div>`;

  /* ---------- ALERTS with ack ---------- */
  $("#tab-alerts").innerHTML = (inc.notifications && inc.notifications.length) ?
    inc.notifications.map((n) => `
      <div class="notif sev-${n.severity}">
        <h4>${esc(n.headline)}</h4>
        <p>${esc(n.body)}</p>
        <div style="font-size:10.5px;color:var(--txt-faint);margin-bottom:6px">Audience: ${n.audience.join(", ")}
          ${n.requires_ack ? " · <b style='color:var(--mod)'>ACK required</b>" : ""}</div>
        <div class="chs">${n.channel.map((c) => `<span class="ch">${esc(c)}</span>`).join("")}</div>
        <div class="ack-btns">
          <span class="ack-tag ack-${n.ack ? n.ack.status : "Proposed"}">${n.ack ? n.ack.status : "Proposed"}</span>
          <button class="ack-a" onclick="ackNotif('${inc.id}','${n.id}','Accepted')">Acknowledge</button>
          <button class="ack-r" onclick="ackNotif('${inc.id}','${n.id}','Rejected')">Reject</button>
        </div>
      </div>`).join("")
    : `<div class="empty-state">No notifications.</div>`;

  /* ---------- SITREP ---------- */
  $("#tab-sitrep").innerHTML = inc.sitrep
    ? `<div class="sitrep-actions">
         <button class="btn-ghost sm" onclick="window.open('${API}/api/incidents/${inc.id}/briefing','_blank')">⤓ Briefing package</button>
         <button class="btn-ghost sm" onclick="downloadSitRep('${inc.id}')">⭳ .md</button>
         <button class="btn-ghost sm" onclick="copySitRep('${inc.id}')">⧉ Copy</button>
       </div><div class="sitrep-md">${mdToHtml(inc.sitrep.body_markdown)}</div>`
    : `<div class="empty-state">No SitRep.</div>`;

  /* ---------- LOG: evidence + decisions + comments + timeline ---------- */
  renderLogTab(inc);

  // NEWS & MEDIA (async)
  loadMedia(di.location, di.disaster_type);
  // live vessel routes on the globe (coastal incidents)
  if (ctx.vessels && ctx.vessels.count && di.coordinates && di.coordinates.lat != null) {
    loadVesselTracks(di.coordinates.lat, di.coordinates.lon);
  } else CrisisGlobe.setVesselTracks([]);

  // reset to Briefing tab
  $$(".brief-tabs .tab").forEach((x) => x.classList.remove("active"));
  $$(".tab-pane").forEach((x) => x.classList.remove("active"));
  $(".brief-tabs .tab").classList.add("active");
  $("#tab-overview").classList.add("active");
}

function renderLogTab(inc) {
  const ev = inc.evidence || [], dec = inc.decisions || [], com = inc.comments || [];
  $("#tab-log").innerHTML = `
    <div class="section-title">Evidence ledger <span class="sub">why we believe this</span></div>
    ${ev.length ? ev.map((e) => `<div class="ev-item2 kind-${esc(e.kind)}">
        <span class="ev-src">${esc(e.source)}</span>
        <span class="ev-stmt">${esc(e.statement)}${e.url ? ` <a href="${esc(e.url)}" target="_blank">↗</a>` : ""}</span>
      </div>`).join("") : `<div class="ev-empty">No evidence captured.</div>`}

    <div class="section-title">Decision log</div>
    <div class="add-dec">
      <input id="decInput" class="search" placeholder="Record a decision…" />
      <button class="btn-ghost sm" onclick="addDecision('${inc.id}')">Log decision</button>
    </div>
    ${dec.length ? dec.map((d) => `<div class="log-item"><b>${esc(d.decision)}</b>
       <span class="log-meta">${esc(d.author)} · ${esc((d.at || "").slice(0, 16).replace("T", " "))}</span></div>`).join("") : ""}

    <div class="section-title">Notes</div>
    <div class="add-dec">
      <input id="comInput" class="search" placeholder="Add a note / comment…" />
      <button class="btn-ghost sm" onclick="addComment('${inc.id}')">Add</button>
    </div>
    ${com.length ? com.map((c) => `<div class="log-item">💬 ${esc(c.text)}
       <span class="log-meta">${esc(c.author)} · ${esc((c.at || "").slice(0, 16).replace("T", " "))}</span></div>`).join("") : ""}

    <div class="section-title">Agent timeline</div>
    <div class="tl">${(inc.timeline || []).map((t) => `<div class="tl-row"><span class="tl-agent">${esc(t.agent)}</span> ${esc(t.message)}</div>`).join("")}</div>`;
}

function gotoTab(t) {
  $$(".brief-tabs .tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === t));
  $$(".tab-pane").forEach((x) => x.classList.toggle("active", x.id === "tab-" + t));
}

/* ---------- acknowledgement + collaboration actions ---------- */
async function refreshIncident(id) {
  const inc = await (await fetch(`${API}/api/incidents/${id}`)).json();
  renderBrief(inc);
}
async function postAck(incId, target, status, extra) {
  await fetch(`${API}/api/incidents/${incId}/ack`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, status, by: OPERATOR, ...(extra || {}) }),
  });
  refreshIncident(incId);
}
function ackCluster(incId, id, status) { postAck(incId, `cluster:${id}`, status); }
function amendCluster(incId, id) {
  const v = prompt("Amend the activity / tasking:");
  if (v) postAck(incId, `cluster:${id}`, "Amended", { answer: v });
}
function ackNotif(incId, id, status) { postAck(incId, `notification:${id}`, status); }
function answerQuestion(incId, id) {
  const v = prompt("Answer / resolve this question:");
  if (v) postAck(incId, `question:${id}`, "Answered", { answer: v });
}
async function addDecision(incId) {
  const el = $("#decInput"); const v = el.value.trim(); if (!v) return;
  await fetch(`${API}/api/incidents/${incId}/decisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ author: OPERATOR, decision: v }) });
  refreshIncident(incId);
}
async function addComment(incId) {
  const el = $("#comInput"); const v = el.value.trim(); if (!v) return;
  await fetch(`${API}/api/incidents/${incId}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ author: OPERATOR, text: v }) });
  refreshIncident(incId);
}

async function loadVesselTracks(lat, lon) {
  try {
    const r = await (await fetch(`${API}/api/vessels?lat=${lat}&lon=${lon}`)).json();
    CrisisGlobe.setVesselTracks(r.tracks || []);
  } catch (e) { /* ignore */ }
}

async function loadMedia(location, type) {
  const pane = $("#tab-media");
  pane.innerHTML = `<div class="working"><span class="spinner"></span> Fetching live news & social posts…</div>`;
  try {
    const m = await (await fetch(`${API}/api/media?location=${encodeURIComponent(location || "")}&type=${encodeURIComponent(type || "")}`)).json();
    const news = m.news || [], social = m.social || [];
    pane.innerHTML = `
      <div class="section-title">Live news <span class="sub">· GDELT</span></div>
      ${news.length ? news.map(newsCard).join("") : `<div class="ev-empty">No recent news found for “${esc(m.query)}”.</div>`}
      <div class="section-title">Social media <span class="sub">· Mastodon</span></div>
      ${social.length ? social.map(socialCard).join("") : `<div class="ev-empty">No recent public posts found.</div>`}`;
  } catch (e) {
    pane.innerHTML = `<div class="ev-empty">News & social unavailable: ${esc(e.message)}</div>`;
  }
}

function newsCard(a) {
  const when = (a.time || "").replace(/T/, " ").slice(0, 13);
  return `<a class="news-card" href="${esc(a.url)}" target="_blank" rel="noopener">
    ${a.image ? `<img src="${esc(a.image)}" loading="lazy" onerror="this.style.display='none'"/>` : ""}
    <div class="news-body"><div class="news-title">${esc(a.title || "(untitled)")}</div>
      <div class="news-meta">${esc(a.domain || "")}${a.country ? " · " + esc(a.country) : ""}${when ? " · " + esc(when) : ""}</div></div>
  </a>`;
}

function socialCard(p) {
  return `<div class="social-card">
    <div class="social-head">${p.avatar ? `<img src="${esc(p.avatar)}" loading="lazy" onerror="this.style.display='none'"/>` : ""}
      <a href="${esc(p.url)}" target="_blank" rel="noopener">@${esc(p.author || "user")}</a></div>
    <div class="social-text">${esc(p.text || "")}</div>
  </div>`;
}

function closeBrief() { $("#briefContent").hidden = true; $("#briefEmpty").hidden = false; CrisisGlobe.setVesselTracks([]); }

async function approveIncident(id) {
  const r = await (await fetch(`${API}/api/incidents/${id}/approve`, { method: "POST" })).json();
  if (r.incident) { currentIncident = r.incident; renderBrief(currentIncident); loadResources(); logLine("HITL", "Dispatch approved — inventory committed."); }
}

function _sitrepOf(id) {
  const inc = (currentIncident && currentIncident.id === id) ? currentIncident : null;
  return inc && inc.sitrep ? inc.sitrep.body_markdown : "";
}
function downloadSitRep(id) {
  const md = _sitrepOf(id); if (!md) return;
  const blob = new Blob([md], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `SitRep_${id}.md`;
  a.click(); URL.revokeObjectURL(a.href);
}
function copySitRep(id) {
  const md = _sitrepOf(id); if (!md) return;
  navigator.clipboard.writeText(md).then(() => logLine("InfoManagement", "SitRep copied to clipboard."));
}

/* ============================================================= incidents */
async function loadIncidents() {
  const r = await (await fetch(API + "/api/incidents")).json();
  const list = r.incidents || [];
  $("#incidentsList").innerHTML = list.length ? list.map((i) => `
    <div class="inc-card" onclick='openIncident("${i.id}")'>
      <div>
        <h3>${esc(i.incident.disaster_type)} · ${esc(i.incident.location)}</h3>
        <div class="meta">${esc(i.id)} · ${esc(i.created_at).slice(0, 19).replace("T", " ")} UTC</div>
      </div>
      <div class="right">
        <span class="sev-badge sev-${i.assessment ? i.assessment.severity_score : "Moderate"}">${i.assessment ? i.assessment.severity_score : "—"}</span>
        <div style="margin-top:6px">${esc(i.status)}</div>
      </div>
    </div>`).join("")
    : `<div class="empty-state">No incidents yet. Run the agent team from the left panel.</div>`;
}

async function openIncident(id) {
  const inc = await (await fetch(`${API}/api/incidents/${id}`)).json();
  currentIncident = inc;
  switchView("globe");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === "globe"));
  renderBrief(inc);
}

/* ============================================================= resources */
const RES_TYPES = ["medics", "water", "food_rations", "tents", "rescue_boats", "rescue_teams",
  "ambulances", "helicopters", "generators", "masks", "tarpaulins", "water_purification",
  "buses", "body_bags", "cash_transfers"];
let resourceCache = [];

async function loadResources() {
  const d = await (await fetch(API + "/api/resources")).json();
  resourceCache = d.resources || [];
  CrisisGlobe.setResources && CrisisGlobe.setResources(resourceCache);
  // only render the full editor when the Resources view is active
  if ($("#resourcesView").classList.contains("active")) renderResources();
}

function renderResources() {
  const rows = resourceCache.map((r) => `
    <tr data-id="${esc(r.id)}">
      <td><input class="cell" data-f="label" value="${esc(r.label)}" /></td>
      <td><select class="cell sel" data-f="type">${RES_TYPES.map((t) =>
        `<option ${t === r.type ? "selected" : ""}>${t}</option>`).join("")}</select></td>
      <td><input class="cell num" data-f="quantity" type="number" value="${r.quantity}" /></td>
      <td><input class="cell" data-f="unit" value="${esc(r.unit)}" style="width:70px" /></td>
      <td><input class="cell" data-f="location" value="${esc(r.location)}" /></td>
      <td><input class="cell num" data-f="lat" type="number" step="0.0001" value="${r.lat ?? ""}" style="width:78px" /></td>
      <td><input class="cell num" data-f="lon" type="number" step="0.0001" value="${r.lon ?? ""}" style="width:78px" /></td>
      <td><input class="cell" data-f="owner" value="${esc(r.owner)}" style="width:90px" /></td>
      <td class="prov-cell">${esc(r.source)}</td>
      <td class="row-actions">
        <button class="mini save" title="Save">✓</button>
        <button class="mini del" title="Delete">✕</button>
      </td>
    </tr>`).join("");

  const totals = {};
  resourceCache.forEach((r) => { totals[r.type] = (totals[r.type] || 0) + r.quantity; });

  $("#resourcesPanel").innerHTML = `
    <div class="mon-head">
      <div><h2>Resource Registry</h2>
        <p class="sub">Real, located, editable stock. Every record has a location and owner; the Logistics agent allocates from here and deducts on dispatch approval. Nothing is fabricated — edit or delete the seed entries and add your own.</p></div>
      <div class="mon-stat"><div><b>${resourceCache.length}</b><span>records</span></div>
        <div><b>${Object.keys(totals).length}</b><span>types</span></div></div>
    </div>
    <div class="res-table-wrap">
      <table class="res-table">
        <thead><tr><th>Label</th><th>Type</th><th>Qty</th><th>Unit</th><th>Location</th><th>Lat</th><th>Lon</th><th>Owner</th><th>Src</th><th></th></tr></thead>
        <tbody id="resBody">${rows}</tbody>
      </table>
    </div>
    <div class="res-add">
      <h3>+ Add resource</h3>
      <div class="add-row">
        <input id="naLabel" class="search" placeholder="Label (e.g. Water purification unit)" />
        <select id="naType" class="sel">${RES_TYPES.map((t) => `<option>${t}</option>`).join("")}</select>
        <input id="naQty" class="search" type="number" placeholder="Qty" style="width:80px" />
        <input id="naUnit" class="search" placeholder="unit" style="width:90px" />
        <input id="naLoc" class="search" placeholder="Location name" />
        <input id="naLat" class="search" type="number" step="0.0001" placeholder="lat" style="width:90px" />
        <input id="naLon" class="search" type="number" step="0.0001" placeholder="lon" style="width:90px" />
        <input id="naOwner" class="search" placeholder="Owner" style="width:110px" />
        <button class="btn-primary sm" id="addRes">Add</button>
      </div>
      <p class="sub" id="resMsg"></p>
    </div>`;

  // wire row save/delete
  $$("#resBody tr").forEach((tr) => {
    const id = tr.dataset.id;
    tr.querySelector(".save").addEventListener("click", async () => {
      const patch = {};
      tr.querySelectorAll(".cell").forEach((c) => {
        let v = c.value;
        if (c.dataset.f === "quantity") v = parseInt(v) || 0;
        if (c.dataset.f === "lat" || c.dataset.f === "lon") v = v === "" ? null : parseFloat(v);
        patch[c.dataset.f] = v;
      });
      await fetch(`${API}/api/resources/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      resMsg("✓ Saved."); loadResources();
    });
    tr.querySelector(".del").addEventListener("click", async () => {
      await fetch(`${API}/api/resources/${id}`, { method: "DELETE" });
      loadResources();
    });
  });

  // wire add
  $("#addRes").addEventListener("click", async () => {
    const body = {
      label: $("#naLabel").value.trim() || $("#naType").value, type: $("#naType").value,
      quantity: parseInt($("#naQty").value) || 0, unit: $("#naUnit").value.trim() || "units",
      location: $("#naLoc").value.trim(),
      lat: $("#naLat").value === "" ? null : parseFloat($("#naLat").value),
      lon: $("#naLon").value === "" ? null : parseFloat($("#naLon").value),
      owner: $("#naOwner").value.trim(), source: "user",
    };
    await fetch(API + "/api/resources", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    resMsg("✓ Added."); loadResources();
  });
}

function resMsg(t) { const e = $("#resMsg"); if (e) { e.textContent = t; e.style.color = "var(--low)"; } }

/* ============================================================= monitoring */
const HAZARD_TYPES = ["Earthquake", "Tropical Cyclone", "Flood", "Volcano", "Wildfire", "Tsunami", "Drought", "Landslide"];

async function loadMonitor() {
  const [status, rules, channels, alerts] = await Promise.all([
    fetch(API + "/api/monitor/status").then((r) => r.json()),
    fetch(API + "/api/monitor/rules").then((r) => r.json()),
    fetch(API + "/api/monitor/channels").then((r) => r.json()),
    fetch(API + "/api/monitor/alerts").then((r) => r.json()),
  ]);
  renderMonitor(status, rules.rules, channels, alerts.alerts);
}

function renderMonitor(status, rules, channels, alerts) {
  const ch = status.channels;
  $("#monitorPanel").innerHTML = `
    <div class="mon-head">
      <div><h2>Monitoring &amp; Alerts</h2>
        <p class="sub">Continuously watches the live feeds and notifies you when new events match your rules.</p></div>
      <div class="mon-stat">
        <div><b>${status.watching}</b><span>active rules</span></div>
        <div><b>${status.alerts}</b><span>alerts</span></div>
        <div><b class="${ch.webhook || ch.email ? "on" : "off"}">${ch.webhook || ch.email ? "ON" : "IN-APP"}</b><span>delivery</span></div>
        <div><b>${status.last_poll ? status.last_poll.slice(11, 19) : "—"}</b><span>last poll (UTC)</span></div>
      </div>
    </div>

    <div class="mon-grid">
      <section class="mon-card">
        <h3>Notification channel</h3>
        <p class="sub">Paste a Slack / Discord / Teams or generic incoming-webhook URL to get alerts pushed there. Leave blank to log them in-app only.</p>
        <label class="fl">Webhook URL</label>
        <input id="monWebhook" class="search" placeholder="https://hooks.slack.com/services/…" value="${esc(channels.webhook_url || "")}" />
        <label class="fl">Email (needs server SMTP_* env)</label>
        <input id="monEmail" class="search" placeholder="ops@example.org" value="${esc(channels.email_to || "")}" />
        <div class="btn-row">
          <button class="btn-primary sm" id="saveCh">Save channel</button>
          <button class="btn-ghost sm" id="testCh">Send test alert</button>
        </div>
        <div class="mon-msg" id="chMsg"></div>
      </section>

      <section class="mon-card">
        <h3>Watch rules</h3>
        <p class="sub">Alert me when a new event is at least this severe, of these types, in this region.</p>
        <div class="rule-form">
          <input id="rName" class="search" placeholder="Rule name (e.g. Pacific quakes)" />
          <div class="rule-row">
            <select id="rSev" class="sel">
              <option>Critical</option><option selected>High</option><option>Moderate</option><option>Low</option>
            </select>
            <input id="rRegion" class="search" placeholder="Region filter (country/place, blank = global)" />
          </div>
          <div class="type-chips" id="rTypes">
            ${HAZARD_TYPES.map((t) => `<span class="tchip" data-t="${t}">${t}</span>`).join("")}
          </div>
          <button class="btn-primary sm" id="addRule">+ Add rule</button>
        </div>
        <div class="rule-list" id="ruleList">
          ${rules.map(ruleRow).join("") || `<div class="ev-empty">No rules.</div>`}
        </div>
      </section>
    </div>

    <section class="mon-card">
      <h3>Triggered alerts <span class="sub">(most recent first)</span></h3>
      <div class="alert-list" id="alertList">
        ${alerts.length ? alerts.map(alertRow).join("") : `<div class="ev-empty">No alerts yet. They appear here when a new matching event is detected, or when you send a test.</div>`}
      </div>
    </section>`;

  // wire channel
  $("#saveCh").addEventListener("click", async () => {
    await fetch(API + "/api/monitor/channels", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_url: $("#monWebhook").value.trim(), email_to: $("#monEmail").value.trim() }) });
    monMsg("chMsg", "✓ Channel saved.");
    loadMonitor();
  });
  $("#testCh").addEventListener("click", async () => {
    monMsg("chMsg", "Sending…");
    const a = await (await fetch(API + "/api/monitor/test", { method: "POST" })).json();
    monMsg("chMsg", a.delivered.length ? `✓ Delivered via ${a.delivered.join(", ")}.` : `✗ ${a.errors.join("; ") || "not delivered"}`,
      !a.delivered.length);
    loadMonitor();
  });

  // wire type chips
  $$("#rTypes .tchip").forEach((c) => c.addEventListener("click", () => c.classList.toggle("on")));

  // add rule
  $("#addRule").addEventListener("click", async () => {
    const types = Array.from($$("#rTypes .tchip.on")).map((c) => c.dataset.t);
    const rule = { name: $("#rName").value.trim() || "New watch", min_severity: $("#rSev").value,
      region: $("#rRegion").value.trim(), types };
    await fetch(API + "/api/monitor/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rule) });
    loadMonitor();
  });

  // delete rules
  $$("#ruleList .rule-del").forEach((b) => b.addEventListener("click", async () => {
    await fetch(`${API}/api/monitor/rules/${b.dataset.id}`, { method: "DELETE" });
    loadMonitor();
  }));
}

function ruleRow(r) {
  return `<div class="rule-item">
    <span class="ev-sev" style="background:${CrisisGlobe.severityColor(r.min_severity)}"></span>
    <div class="ev-main">
      <div class="ev-title">${esc(r.name)}</div>
      <div class="ev-meta">≥ ${esc(r.min_severity)} · ${r.types.length ? esc(r.types.join(", ")) : "any type"} · ${r.region ? esc(r.region) : "global"}</div>
    </div>
    <button class="rule-del" data-id="${esc(r.id)}" title="Delete rule">✕</button>
  </div>`;
}

function alertRow(a) {
  const e = a.event || {};
  const ok = a.delivered.length && !a.delivered.includes("in-app");
  return `<div class="alert-item">
    <span class="ev-sev" style="background:${CrisisGlobe.severityColor(e.severity)}"></span>
    <div class="ev-main">
      <div class="ev-title">${esc(e.title || e.type || "Event")}</div>
      <div class="ev-meta">${esc(e.type || "")} · ${esc(e.source || "")}${e.country ? " · " + esc(e.country) : ""} · rule “${esc(a.rule_name)}”</div>
    </div>
    <span class="al-chan ${ok ? "ok" : a.errors.length ? "err" : "log"}">${a.delivered.join(",") || "failed"}</span>
    <span class="al-time">${esc((a.at || "").slice(11, 19))}</span>
  </div>`;
}

function monMsg(id, text, isErr) {
  const el = $("#" + id); if (!el) return;
  el.textContent = text; el.className = "mon-msg " + (isErr ? "err" : "ok");
}

// poll the alert count for the nav badge
async function refreshAlertBadge() {
  try {
    const s = await (await fetch(API + "/api/monitor/status")).json();
    const badge = $("#alertBadge");
    if (s.alerts > 0) { badge.textContent = s.alerts; badge.hidden = false; }
    else badge.hidden = true;
  } catch (e) { /* ignore */ }
}

/* ============================================================= hazards KB */
async function loadHazards() {
  try {
    const r = await (await fetch(API + "/api/hazards")).json();
    const p = r.profiles || {};
    $("#handbookPanel").innerHTML = `
      <h2 style="margin-bottom:6px">Hazard Impact Knowledge Base</h2>
      <p style="color:var(--txt-faint);font-size:12px;margin-bottom:16px">Grounded in the UNDAC Handbook (8th ed., 2024) Section K. Drives the Assessment agent's hazard-aware reasoning.</p>
      ${Object.entries(p).map(([name, h]) => `
        <div class="haz-card">
          <h3>${esc(name)} <span class="haz-ref">UNDAC ${esc(h.handbook_ref)}</span>
            <span style="font-size:11px;color:var(--txt-faint);font-weight:400">· life-saving window ${h.golden_hours || "—"}h</span></h3>
          <div class="haz-cols">
            <div><h4>Priority sectors</h4><div class="pill-list">${h.priority_sectors.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>
              <h4 style="margin-top:12px">Secondary hazards</h4><div class="pill-list">${h.secondary_hazards.map((s) => `<span class="tag crit">${esc(s)}</span>`).join("")}</div></div>
            <div><h4>Priority actions</h4><ul>${h.priority_actions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>
          </div>
        </div>`).join("")}`;
  } catch (e) { /* ignore */ }
}

/* ============================================================= helpers */
function startClock() {
  setInterval(() => {
    $("#clock").textContent = new Date().toISOString().slice(11, 19) + " UTC";
  }, 1000);
}

// minimal markdown → HTML for SitReps (headings, tables, lists, bold/italic)
function mdToHtml(md) {
  const lines = (md || "").split("\n");
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
  const isSep = (l) => /^\|[\s|:-]+\|?$/.test(l) && l.includes("-");
  const cellsOf = (l) => l.split("|").slice(1, -1).map((c) => c.trim());

  let html = "", inList = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();

    // table: a "|...|" row whose following line is a "---" separator starts a table
    if (line.startsWith("|") && i + 1 < lines.length && isSep(lines[i + 1].trim())) {
      if (inList) { html += "</ul>"; inList = false; }
      html += "<table><tr>" + cellsOf(line).map((c) => `<th>${inline(c)}</th>`).join("") + "</tr>";
      i++; // skip separator
      while (i + 1 < lines.length && lines[i + 1].trim().startsWith("|")) {
        html += "<tr>" + cellsOf(lines[++i].trim()).map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
      }
      html += "</table>";
      continue;
    }

    if (line.startsWith("### ")) { if (inList) { html += "</ul>"; inList = false; } html += `<h3>${inline(line.slice(4))}</h3>`; }
    else if (line.startsWith("## ")) { if (inList) { html += "</ul>"; inList = false; } html += `<h2>${inline(line.slice(3))}</h2>`; }
    else if (line.startsWith("- ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(line.slice(2))}</li>`;
    } else if (line === "") { if (inList) { html += "</ul>"; inList = false; } }
    else { if (inList) { html += "</ul>"; inList = false; } html += `<p>${inline(line)}</p>`; }
  }
  if (inList) html += "</ul>";
  return html;
}
