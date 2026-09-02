const COLORS = {};
const state = {
  window: "24h",
  category: "",
  district: "",
  hideRoutine: true,
  heatmap: true,
  pins: true,
  incidents: [],
  stats: null,
};

const map = L.map("map", { zoomControl: true }).setView([37.7749, -122.4194], 13);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap &copy; CARTO",
  maxZoom: 19,
}).addTo(map);

const pinLayer = L.layerGroup().addTo(map);
let heatLayer = null;

function qs() {
  const p = new URLSearchParams({
    window: state.window,
    hide_routine: state.hideRoutine ? "1" : "0",
  });
  if (state.category) p.set("category", state.category);
  if (state.district) p.set("district", state.district);
  return p.toString();
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function relTime(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function colorFor(cat) {
  return COLORS[cat] || "#64748b";
}

function renderCats(stats) {
  const host = document.getElementById("cats");
  const cats = stats.categories || [];
  cats.forEach((c) => { COLORS[c.id] = c.color; });
  const counts = Object.fromEntries((stats.by_category || []).map((r) => [r.category, r.n]));
  host.innerHTML = "";
  const all = document.createElement("button");
  all.className = `chip ${state.category ? "" : "on"}`;
  all.textContent = `All · ${stats.total}`;
  all.onclick = () => { state.category = ""; reload(); };
  host.appendChild(all);
  for (const c of cats) {
    const n = counts[c.id] || 0;
    if (!n && c.id === "other") continue;
    const btn = document.createElement("button");
    btn.className = `chip ${state.category === c.id ? "on" : ""}`;
    btn.style.setProperty("--chip", c.color);
    btn.innerHTML = `<span class="dot"></span>${c.label} · ${n}`;
    btn.onclick = () => {
      state.category = state.category === c.id ? "" : c.id;
      reload();
    };
    host.appendChild(btn);
  }
}

function renderStats(s) {
  document.getElementById("stats").innerHTML = `
    <div class="stat"><b>${s.total}</b><span>incidents</span></div>
    <div class="stat"><b>${s.open}</b><span>open</span></div>
    <div class="stat"><b>${s.mapped}</b><span>mapped</span></div>
  `;
  const maxHour = Math.max(1, ...(s.by_hour || []).map((h) => h.n));
  document.getElementById("hours").innerHTML = `
    <h2>By hour</h2>
    ${(s.by_hour || []).map((h) => `
      <div class="hour-row">
        <span>${String(h.hour).padStart(2, "0")}</span>
        <div class="bar"><i style="width:${Math.round((h.n / maxHour) * 100)}%"></i></div>
        <span>${h.n}</span>
      </div>`).join("")}
  `;
  document.getElementById("hotspots").innerHTML = `
    <h2>Hotspots</h2>
    ${(s.hotspots || []).map((h) => `
      <div class="hot" data-lat="${h.lat || ""}" data-lon="${h.lon || ""}">
        <span>${(h.intersection || "Unknown").replace(" \\ ", " / ")}
          <em> · ${h.neighborhood || h.district || ""}</em></span>
        <b>${h.n}</b>
      </div>`).join("") || "<p class='sub'>No clustered intersections yet.</p>"}
  `;
  document.querySelectorAll(".hot").forEach((el) => {
    el.onclick = () => {
      const lat = parseFloat(el.dataset.lat);
      const lon = parseFloat(el.dataset.lon);
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) map.setView([lat, lon], 16);
    };
  });

  const dist = document.getElementById("district");
  const current = state.district;
  dist.innerHTML = `<option value="">All districts</option>` +
    (s.districts || []).map((d) => `<option ${d === current ? "selected" : ""}>${d}</option>`).join("");

  const latest = s.latest_incident ? relTime(s.latest_incident) : "n/a";
  document.getElementById("statusLine").textContent =
    `${s.total} in window · newest ${latest} · traffic stops count toward heat`;
}

function renderFeed(items) {
  document.getElementById("feedCount").textContent = `${items.length} shown`;
  document.getElementById("feed").innerHTML = items.map((it) => `
    <article class="card" data-cad="${it.cad_number}" style="--cat:${colorFor(it.category)}">
      <div class="kicker">
        <span>${it.district || "SF"} · ${relTime(it.received_datetime)}</span>
        <span class="badge ${it.status}">${it.status}</span>
      </div>
      <h3>${it.call_type_final_desc || "Unknown call"}</h3>
      <p>${it.intersection ? it.intersection.replace(" \\ ", " / ") : "Location withheld"}
         ${it.neighborhood ? " · " + it.neighborhood : ""}</p>
    </article>
  `).join("") || `<p class="sub">No incidents in this window.</p>`;
  document.querySelectorAll(".card").forEach((el) => {
    el.onclick = () => focusCad(el.dataset.cad);
  });
}

function popupHtml(it) {
  return `<div class="incident-popup">
    <h3>${it.call_type_final_desc || "CAD"}</h3>
    <p>${it.intersection ? it.intersection.replace(" \\ ", " / ") : "Location withheld"}<br>
    ${it.neighborhood || ""} · ${it.district || ""} · ${relTime(it.received_datetime)}</p>
  </div>`;
}

function renderPins(items) {
  pinLayer.clearLayers();
  if (!state.pins) return;
  for (const it of items) {
    if (it.lat == null || it.lon == null) continue;
    const marker = L.circleMarker([it.lat, it.lon], {
      radius: it.status === "open" ? 7 : 5,
      color: colorFor(it.category),
      weight: it.status === "open" ? 2 : 1,
      fillOpacity: it.status === "open" ? 0.9 : 0.55,
    });
    marker.bindPopup(popupHtml(it));
    marker.cad = it.cad_number;
    pinLayer.addLayer(marker);
  }
}

function renderHeat(points) {
  if (heatLayer) {
    map.removeLayer(heatLayer);
    heatLayer = null;
  }
  if (!state.heatmap || !points.length) return;
  heatLayer = L.heatLayer(points, {
    radius: 22,
    blur: 18,
    maxZoom: 17,
    minOpacity: 0.25,
    gradient: {
      0.2: "#1d4ed8",
      0.4: "#22c55e",
      0.65: "#f59e0b",
      0.85: "#f97316",
      1.0: "#ef4444",
    },
  }).addTo(map);
}

function focusCad(cad) {
  const it = state.incidents.find((x) => x.cad_number === cad);
  document.querySelectorAll(".card").forEach((el) => {
    el.classList.toggle("active", el.dataset.cad === cad);
  });
  if (!it || it.lat == null) return;
  map.setView([it.lat, it.lon], 16);
  pinLayer.eachLayer((layer) => {
    if (layer.cad === cad) layer.openPopup();
  });
}

async function reload() {
  document.getElementById("pulse").classList.remove("idle");
  try {
    const [incidents, heat, stats] = await Promise.all([
      getJSON(`/api/incidents?${qs()}&limit=250`),
      getJSON(`/api/heatmap?${qs()}`),
      getJSON(`/api/stats?${qs()}`),
    ]);
    state.incidents = incidents;
    state.stats = stats;
    renderCats(stats);
    renderStats(stats);
    renderFeed(incidents);
    renderPins(incidents);
    renderHeat(heat.points || []);
  } catch (err) {
    document.getElementById("statusLine").textContent = `error: ${err.message}`;
    document.getElementById("pulse").classList.add("idle");
  }
}

document.getElementById("window").onchange = (e) => {
  state.window = e.target.value;
  reload();
};
document.getElementById("district").onchange = (e) => {
  state.district = e.target.value;
  reload();
};
document.getElementById("heatmap").onchange = (e) => {
  state.heatmap = e.target.checked;
  reload();
};
document.getElementById("pins").onchange = (e) => {
  state.pins = e.target.checked;
  renderPins(state.incidents);
};
document.getElementById("hideRoutine").onchange = (e) => {
  state.hideRoutine = e.target.checked;
  reload();
};
document.getElementById("refresh").onclick = async () => {
  document.getElementById("statusLine").textContent = "refreshing CAD…";
  await fetch("/api/refresh", { method: "POST" });
  reload();
};
document.getElementById("feedToggle").onclick = () => {
  document.getElementById("panel").classList.toggle("open");
};

reload();
setInterval(reload, 60000);
