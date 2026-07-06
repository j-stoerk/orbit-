/* ===================================================================
   3D interactive world — built on globe.gl (three.js).
   Plots live events AND animates the OSOCC agent pipeline as a
   "mission" playing out on the globe (fly-to, scan, coordination arcs,
   inbound supply arcs, alert broadcast).
   Exposes window.CrisisGlobe.
   =================================================================== */
(function () {
  const SEV_COLOR = { Critical: "#ff3b46", High: "#ff8c2e", Moderate: "#ffd23f", Low: "#37d67a" };
  const SEV_RGBA = {
    Critical: "rgba(255,59,70,", High: "rgba(255,140,46,",
    Moderate: "rgba(255,210,63,", Low: "rgba(55,214,122,",
  };
  // UN cluster-lead HQ cities used to visualise coordination reach
  const CLUSTER_HQ = {
    "Health": { city: "WHO Geneva", lat: 46.2317, lon: 6.0566 },
    "WASH": { city: "UNICEF New York", lat: 40.7489, lon: -73.968 },
    "Shelter/NFI": { city: "IFRC/UNHCR Geneva", lat: 46.227, lon: 6.137 },
    "Food Security": { city: "WFP/FAO Rome", lat: 41.8881, lon: 12.4894 },
    "Protection": { city: "UNHCR Geneva", lat: 46.227, lon: 6.137 },
    "Logistics": { city: "WFP Rome", lat: 41.8881, lon: 12.4894 },
    "Emergency Telecommunications": { city: "WFP ETC Rome", lat: 41.8881, lon: 12.4894 },
    "Education": { city: "UNICEF New York", lat: 40.7489, lon: -73.968 },
    "Early Recovery": { city: "UNDP New York", lat: 40.7493, lon: -73.968 },
    "Camp Coordination": { city: "IOM Geneva", lat: 46.224, lon: 6.1432 },
    "Nutrition": { city: "UNICEF New York", lat: 40.7489, lon: -73.968 },
  };

  // UN Humanitarian Response Depots (UNHRD) — supply origins
  const DEPOTS = [
    { city: "Brindisi (IT)", lat: 40.6453, lon: 17.9461 },
    { city: "Dubai (AE)", lat: 25.2048, lon: 55.2708 },
    { city: "Accra (GH)", lat: 5.6037, lon: -0.187 },
    { city: "Panama City", lat: 8.9824, lon: -79.5199 },
    { city: "Subang (MY)", lat: 3.0738, lon: 101.5183 },
    { city: "Las Palmas (ES)", lat: 28.0997, lon: -15.4134 },
  ];

  let world = null, onClick = null;
  let points = [], selectedId = null;
  let liveRings = [], missionRings = [];

  function severityColor(s) { return SEV_COLOR[s] || "#2ea7e0"; }
  function rgbaPrefix(s) { return SEV_RGBA[s] || "rgba(46,167,224,"; }

  const SEV_ALT = { Critical: 0.085, High: 0.06, Moderate: 0.04, Low: 0.025 };
  const SEV_RAD = { Critical: 0.42, High: 0.34, Moderate: 0.27, Low: 0.22 };
  const pointAltitude = (d) => (d.id === selectedId ? 0.12 : 0) + (SEV_ALT[d.severity] || 0.03);
  const pointRadius = (d) => (d.id === selectedId ? 0.18 : 0) + (SEV_RAD[d.severity] || 0.25);

  function haversine(a, b) {
    const R = 6371, toR = Math.PI / 180;
    const dLat = (b.lat - a.lat) * toR, dLon = (b.lon - a.lon) * toR;
    const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toR) * Math.cos(b.lat * toR) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  function init(el) {
    world = Globe()(el)
      .globeImageUrl("https://unpkg.com/three-globe@2.31.0/example/img/earth-night.jpg")
      .bumpImageUrl("https://unpkg.com/three-globe@2.31.0/example/img/earth-topology.png")
      .backgroundImageUrl("https://unpkg.com/three-globe@2.31.0/example/img/night-sky.png")
      .atmosphereColor("#2ea7e0").atmosphereAltitude(0.18)
      // live + incident points
      .pointsData([]).pointLat("lat").pointLng("lon")
      .pointColor((d) => {
        if (d.id === selectedId) return "#ffffff";
        if (d.is_victim) {
          return d.status === "Dispatched" ? "#37d67a" : "#ffff00";
        }
        return severityColor(d.severity);
      })
      .pointAltitude(pointAltitude).pointRadius(pointRadius).pointResolution(6)
      .pointLabel(labelHtml)
      .onPointClick((d) => onClick && onClick(d))
      // expanding rings (live pulses + mission scan/broadcast)
      .ringsData([]).ringLat("lat").ringLng("lon")
      .ringColor((d) => (t) => `${d._rgba || "rgba(255,59,70,"}${(1 - t) * (d._maxOpacity || 1)})`)
      .ringMaxRadius((d) => d._maxR || 4)
      .ringPropagationSpeed((d) => d._speed || 2.2)
      .ringRepeatPeriod((d) => d._period || 900)
      // arcs (coordination + supply) — thin, flat, calm
      .arcsData([]).arcStartLat("startLat").arcStartLng("startLng")
      .arcEndLat("endLat").arcEndLng("endLng")
      .arcColor("color").arcStroke((d) => d.stroke || 0.18)
      .arcAltitudeAutoScale(0.4)
      .arcDashLength(0.5).arcDashGap(0.45)
      .arcDashAnimateTime((d) => d.speed || 2800)
      .arcLabel((d) => d.label)
      // beacon label at the active incident — small + restrained
      .labelsData([]).labelLat("lat").labelLng("lon")
      .labelText("text").labelColor((d) => d.color || "#cdd9ec")
      .labelSize(0.52).labelDotRadius(0.2).labelResolution(2)
      .labelAltitude(0.008)
      // resource depots — small static markers
      .htmlElementsData([]).htmlLat("lat").htmlLng("lon")
      .htmlElement(htmlMarker)
      // live vessel tracks (routes) — animated dash flowing to current position
      .pathsData([])
      .pathPoints("path").pathPointLat((p) => p[0]).pathPointLng((p) => p[1])
      .pathColor(() => ["rgba(70,200,210,0.12)", "rgba(120,230,240,0.95)"])
      .pathStroke(1.4).pathPointAlt(0.004)
      .pathLabel((d) => `🚢 ${d.name}${d.sog != null ? " · " + d.sog + " kn" : ""}`)
      .pathDashLength(0.5).pathDashGap(0.18).pathDashAnimateTime(2600)
      // static 3D impact range zones
      .customLayerData([])
      .customThreeObject((d) => {
        const THREE = window.THREE;
        if (!THREE) return null;
        const group = new THREE.Group();

        // 1. Filled circle (semi-transparent)
        const circleGeo = new THREE.CircleGeometry(d.radius, 32);
        const circleMat = new THREE.MeshBasicMaterial({
          color: d.color || "#ff3b46",
          transparent: true,
          opacity: d.isSelected ? 0.28 : 0.14,
          side: THREE.DoubleSide,
          depthWrite: false
        });
        const circle = new THREE.Mesh(circleGeo, circleMat);
        group.add(circle);

        // 2. Ring border
        const ringGeo = new THREE.RingGeometry(d.radius * (d.isSelected ? 0.94 : 0.96), d.radius, 32);
        const ringMat = new THREE.MeshBasicMaterial({
          color: d.isSelected ? "#ffffff" : d.color,
          transparent: true,
          opacity: d.isSelected ? 0.95 : 0.52,
          side: THREE.DoubleSide,
          depthWrite: false
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        group.add(ring);

        return group;
      })
      .customThreeObjectUpdate((obj, d) => {
        const THREE = window.THREE;
        if (!THREE) return;
        // Position slightly above the surface (altitude 0.006) to avoid z-fighting
        Object.assign(obj.position, world.getCoords(d.lat, d.lon, 0.006));
        // Align its local Z-normal to point outward from the Earth center (normal vector)
        const normal = obj.position.clone().normalize();
        obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
      });

    const controls = world.controls();
    controls.autoRotate = true; controls.autoRotateSpeed = 0.35;
    el.addEventListener("pointerdown", () => (controls.autoRotate = false), { once: true });
    const resize = () => world.width(el.clientWidth).height(el.clientHeight);
    new ResizeObserver(resize).observe(el);
    resize();
    world.pointOfView({ lat: 20, lng: 10, altitude: 2.4 }, 0);
    return world;
  }

  function labelHtml(d) {
    const mag = (d.source === "USGS" && d.magnitude) ? `M${d.magnitude} · ` : "";
    return `<div style="font:12px/1.4 'Segoe UI';background:#0a1120ee;border:1px solid #2a3a5c;
        border-radius:7px;padding:8px 11px;color:#dfe7f3;max-width:240px">
        <b style="color:${severityColor(d.severity)}">${d.severity || "Event"}</b>&nbsp;·&nbsp;${d.type || ""}<br>
        <span style="color:#fff">${(d.title || "").slice(0, 70)}</span><br>
        <span style="color:#8da0c0;font-size:11px">${mag}${d.source || ""}${d.country ? " · " + d.country : ""}</span><br>
        <span style="color:#5f7197;font-size:10px">click to brief &rarr;</span></div>`;
  }

  /* ----------------------------- live data ----------------------------- */
  function refresh() { world && world.pointsData(points); }
  function setEvents(evts) { points = (evts || []).filter((e) => e.lat != null && e.lon != null); refresh(); }
  function applyRings() { world && world.ringsData([...liveRings, ...missionRings]); }

  function setActiveRings(items) {
    liveRings = (items || []).filter((e) => e.lat != null && e.lon != null).map((e) => {
      let rgba = rgbaPrefix(e.severity);
      let maxOpacity = 0.3;
      let maxR = e.severity === "Critical" ? 2.6 : 2;
      let speed = 1.3;
      if (e.is_victim) {
        rgba = "rgba(255,255,0,";
        maxOpacity = 0.8;
        maxR = 3.0;
        speed = 1.5;
      }
      return {
        lat: e.lat, lon: e.lon, _rgba: rgba,
        _maxR: maxR, _speed: speed, _period: 2200, _maxOpacity: maxOpacity,
      };
    });
    applyRings();
  }

  function focus(lat, lon, altitude = 1.1) {
    if (world && lat != null && lon != null) {
      world.controls().autoRotate = false;
      world.pointOfView({ lat, lng: lon, altitude }, 1200);
    }
  }
  function select(id) {
    selectedId = id;
    refresh();
    setImpactCircles(points);
  }
  function setOnClick(fn) { onClick = fn; }

  // combined HTML-marker layer: resource depots (green diamond) + vessels (teal dot)
  let depotMarkers = [], vesselMarkers = [];
  function applyHtml() { world && world.htmlElementsData([...depotMarkers, ...vesselMarkers]); }

  function htmlMarker(d) {
    const el = document.createElement("div");
    if (d.kind === "vessel") {
      el.style.cssText = "width:7px;height:7px;background:#5ce6f0;border:1px solid #0a1120;"
        + "border-radius:50%;box-shadow:0 0 7px #5ce6f0;cursor:help";
      el.title = `🚢 ${d.name}${d.sog != null ? " · " + d.sog + " kn" : ""}`;
    } else {
      el.style.cssText = "width:9px;height:9px;background:#37d67a;border:1px solid #0a1120;"
        + "transform:rotate(45deg);box-shadow:0 0 6px #37d67a88;cursor:help";
      el.title = `${d.location}: ${(d.items || []).join(", ")}`;
    }
    return el;
  }

  // live vessel routes (paths) + current-position markers
  function setVesselTracks(tracks) {
    tracks = tracks || [];
    world && world.pathsData(tracks.filter((t) => t.path && t.path.length >= 2));
    vesselMarkers = tracks.filter((t) => t.current)
      .map((t) => ({ kind: "vessel", lat: t.current[0], lon: t.current[1], name: t.name, sog: t.sog }));
    applyHtml();
  }

  function setResources(resources) {
    const byLoc = {};
    (resources || []).forEach((r) => {
      if (r.lat == null || r.lon == null) return;
      const k = `${r.lat},${r.lon}`;
      (byLoc[k] = byLoc[k] || { kind: "depot", lat: r.lat, lon: r.lon, location: r.location, items: [] })
        .items.push(`${r.quantity} ${r.label}`);
    });
    depotMarkers = Object.values(byLoc);
    applyHtml();
  }

  let impactCircles = [];

  function setImpactCircles(items) {
    if (!world) return;
    impactCircles = (items || []).filter((e) => e.lat != null && e.lon != null).map((e) => {
      // 1 unit = 63.71 km
      let radiusKm = 100;
      if (e.source === "USGS" && e.magnitude) {
        // scale with magnitude (M5 -> 100km, M7 -> 300km, etc)
        radiusKm = Math.max(30, Math.pow(1.8, e.magnitude) * 12);
      } else {
        if (e.severity === "Critical") radiusKm = 250;
        else if (e.severity === "High") radiusKm = 150;
        else if (e.severity === "Moderate") radiusKm = 90;
        else if (e.severity === "Low") radiusKm = 50;
      }
      return {
        id: e.id,
        lat: e.lat,
        lon: e.lon,
        radius: radiusKm / 63.71,
        color: severityColor(e.severity),
        isSelected: e.id === selectedId
      };
    });
    world.customLayerData(impactCircles);
  }

  /* =============================== MISSION =============================== */
  let mission = null; // {lat, lon, severity, title}

  // one-shot expanding ring burst that auto-clears
  function burst(lat, lon, rgba, { maxR = 5, speed = 3, period = 700, ttl = 3200, maxOpacity = 1 } = {}) {
    const ring = { lat, lon, _rgba: rgba, _maxR: maxR, _speed: speed, _period: period, _maxOpacity: maxOpacity };
    missionRings.push(ring); applyRings();
    setTimeout(() => { missionRings = missionRings.filter((r) => r !== ring); applyRings(); }, ttl);
  }

  // muted, neutral arc palettes (kept independent of severity for a calm look)
  const COORD_ARC = ["rgba(140,180,215,0)", "rgba(140,180,215,0.4)"];
  const SUPPLY_ARC = ["rgba(120,196,160,0)", "rgba(120,196,160,0.45)"];

  // 1) begin the mission: fly tightly to the spot, drop a small beacon, one soft pulse
  function missionStart(lat, lon, severity, title) {
    if (lat == null || lon == null) return;
    mission = { lat, lon, severity: severity || "High", title: title || "Incident" };
    world.controls().autoRotate = false;
    world.arcsData([]);
    world.labelsData([{ lat, lon, text: shortLabel(title), color: severityColor(mission.severity) }]);
    world.pointOfView({ lat, lng: lon, altitude: 0.62 }, 1500);
    burst(lat, lon, rgbaPrefix(mission.severity), { maxR: 1.8, speed: 2.4, period: 900, ttl: 1700, maxOpacity: 0.4 });
  }

  // 2) assessment scan — a single soft severity-coloured sweep
  function scan(severity) {
    if (!mission) return;
    mission.severity = severity || mission.severity;
    world.labelsData([{ lat: mission.lat, lon: mission.lon, text: shortLabel(mission.title), color: severityColor(mission.severity) }]);
    burst(mission.lat, mission.lon, rgbaPrefix(mission.severity), { maxR: 3.2, speed: 1.6, period: 1500, ttl: 3000, maxOpacity: 0.4 });
  }

  // 3) coordination — thin arcs from incident out to engaged UN cluster HQs
  function coordination(sectors) {
    if (!mission) return;
    const seen = new Set(), arcs = [];
    (sectors || []).forEach((s) => {
      const hq = CLUSTER_HQ[s]; if (!hq || seen.has(hq.city)) return; seen.add(hq.city);
      arcs.push({
        startLat: mission.lat, startLng: mission.lon, endLat: hq.lat, endLng: hq.lon,
        color: COORD_ARC, label: `Coordinating · ${hq.city}`, stroke: 0.18, speed: 2800, _kind: "coord",
      });
    });
    world.arcsData(arcs);
  }

  // 4) logistics — thin inbound supply arcs from the nearest UN depots
  function logistics() {
    if (!mission) return;
    const nearest = DEPOTS.map((d) => ({ ...d, dist: haversine(mission, d) }))
      .sort((a, b) => a.dist - b.dist).slice(0, 3);
    const existing = world.arcsData() || [];
    const supply = nearest.map((d) => ({
      startLat: d.lat, startLng: d.lon, endLat: mission.lat, endLng: mission.lon,
      color: SUPPLY_ARC, label: `Supply · ${d.city} (${Math.round(d.dist).toLocaleString()} km)`,
      stroke: 0.22, speed: 2200, _kind: "supply",
    }));
    world.arcsData([...existing, ...supply]);
  }

  // 5) alerts — one restrained broadcast ripple (mass notification)
  function broadcast(severity) {
    if (!mission) return;
    const sev = severity || mission.severity;
    burst(mission.lat, mission.lon, rgbaPrefix(sev), { maxR: 7, speed: 3, period: 1100, ttl: 3400, maxOpacity: 0.32 });
  }

  function shortLabel(t) { t = (t || "Incident").trim(); return t.length > 26 ? t.slice(0, 24) + "…" : t; }

  function clearMission() {
    mission = null; missionRings = []; vesselMarkers = [];
    if (world) { world.arcsData([]); world.labelsData([]); world.pathsData([]); }
    applyHtml();
    applyRings();
  }

  window.CrisisGlobe = {
    init, setEvents, setActiveRings, setResources, setVesselTracks, focus, select, setOnClick, severityColor,
    missionStart, scan, coordination, logistics, broadcast, clearMission, setImpactCircles
  };
})();
