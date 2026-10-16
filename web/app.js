const COLORS = {};
const FEED_PAGE = 100;
const state = {
  window: "24h",
  category: "",
  district: "",
  hideRoutine: true,
  heatmap: true,
  pins: true,
  openOnly: false,
  q: "",
  basemap: "",
  selected: null,
  incidents: [],
  heat: [],
  feedShown: FEED_PAGE,
  stats: null,
};

const map = L.map("map", { zoomControl: false, attributionControl: true })
  .setView([37.7749, -122.4194], 13);
L.control.zoom({ position: "bottomleft" }).addTo(map);

const pinLayer = L.layerGroup().addTo(map);
let heatLayer = null;
let basemapLayer = null;
let basemaps = [];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function street(name) {
  return (name || "Location withheld").replaceAll(" \\ ", " / ");
}

function qs() {
  const searching = state.q.trim().length > 0;
  const p = new URLSearchParams({
    window: state.window,
    hide_routine: state.hideRoutine ? "1" : "0",
    // Search covers the whole store, so allow deeper results while typing.
    limit: searching ? "500" : "250",
  });
  if (state.category) p.set("category", state.category);
  if (state.district) p.set("district", state.district);
  if (state.openOnly) p.set("status", "open");
  if (searching) p.set("q", state.q.trim());
  return p.toString();
}

function readUrl() {
  const u = new URL(location.href);
  state.window = u.searchParams.get("window") || state.window;
  state.category = u.searchParams.get("category") || "";
  state.district = u.searchParams.get("district") || "";
  state.q = u.searchParams.get("q") || "";
  state.basemap = u.searchParams.get("basemap") || "";
  if (u.searchParams.get("open") === "1") state.openOnly = true;
  if (u.searchParams.get("noise") === "1") state.hideRoutine = false;
}

function writeUrl() {
  const u = new URL(location.href);
  const set = (k, v) => { if (v) u.searchParams.set(k, v); else u.searchParams.delete(k); };
  set("window", state.window === "24h" ? "" : state.window);
  set("category", state.category);
  set("district", state.district);
  set("q", state.q);
  set("basemap", state.basemap);
  set("open", state.openOnly ? "1" : "");
  set("noise", state.hideRoutine ? "" : "1");
  history.replaceState(null, "", u);
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

function applyBasemap(id) {
  state.basemap = id;
  const sel = document.getElementById("basemap");
  if (sel) sel.value = id;
  const def = basemaps.find((b) => b.id === id) || basemaps[0];
  if (basemapLayer) {
    map.removeLayer(basemapLayer);
    basemapLayer = null;
  }
  // "none" means no external tile requests at all: pins and heat still work.
  if (!def || !def.url) return;
  basemapLayer = L.tileLayer(def.url, {
    attribution: def.attribution,
    subdomains: def.subdomains || "abc",
    // Providers stop serving real tiles past their own ceiling (Esri's SF
    // cache ends at z16); upscale the last real zoom instead of requesting
    // tiles that come back as placeholder images.
    maxNativeZoom: def.max_native_zoom || 19,
    maxZoom: 19,
  }).addTo(map);
}

async function initBasemap() {
  const meta = await getJSON("/api/meta");
  basemaps = meta.basemaps || [];
  const sel = document.getElementById("basemap");
  sel.innerHTML = basemaps
    .map((b) => `<option value="${escapeHtml(b.id)}">${escapeHtml(b.label)}</option>`)
    .join("");
  sel.onchange = () => {
    applyBasemap(sel.value);
    writeUrl();
  };
  // The server's default (SFALERT_BASEMAP) applies unless the URL says otherwise.
  const wanted = state.basemap || meta.basemap?.id || "";
  applyBasemap(basemaps.some((b) => b.id === wanted) ? wanted : (meta.basemap?.id || basemaps[0]?.id));
}

function setPressed(id, on) {
  const el = document.getElementById(id);
  el.classList.toggle("on", on);
  el.setAttribute("aria-pressed", on ? "true" : "false");
}

function renderWindows() {
  document.querySelectorAll("#windows [data-window]").forEach((btn) => {
    const on = btn.dataset.window === state.window;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function renderCats(stats) {
  const host = document.getElementById("cats");
  const cats = stats.categories || [];
  cats.forEach((c) => { COLORS[c.id] = c.color; });
  const counts = Object.fromEntries((stats.by_category || []).map((r) => [r.category, r.n]));
  host.innerHTML = "";
  const all = document.createElement("button");
  all.className = `chip ${state.category ? "" : "on"}`;
  all.setAttribute("aria-pressed", state.category ? "false" : "true");
  all.textContent = `All · ${stats.total}`;
  all.onclick = () => { state.category = ""; reload(); };
  host.appendChild(all);
  for (const c of cats) {
    const n = counts[c.id] || 0;
    if (!n && c.id === "other") continue;
    const on = state.category === c.id;
    const btn = document.createElement("button");
    btn.className = `chip ${on ? "on" : ""}`;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.style.setProperty("--chip", c.color);
    btn.innerHTML = `<span class="dot" aria-hidden="true"></span>${escapeHtml(c.label)} · ${n}`;
    btn.onclick = () => {
      state.category = state.category === c.id ? "" : c.id;
      reload();
    };
    host.appendChild(btn);
  }
}

function renderStats(s) {
  document.getElementById("stats").innerHTML = `
    <div class="stat"><b>${s.total}</b><span>calls</span></div>
    <div class="stat"><b>${s.open}</b><span>open</span></div>
    <div class="stat"><b>${s.mapped}</b><span>mapped</span></div>
  `;
  const byHour = new Map((s.by_hour || []).map((h) => [Number(h.hour), h.n]));
  const maxHour = Math.max(1, ...byHour.values());
  document.getElementById("hours").innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const n = byHour.get(hour) || 0;
    const pct = Math.max(8, Math.round((n / maxHour) * 100));
    const label = `${String(hour).padStart(2, "0")}:00 · ${n} calls`;
    return `<button type="button" style="--h:${pct}%" title="${label}" aria-label="${label}"></button>`;
  }).join("");

  document.getElementById("hotspots").innerHTML = `
    <h2>Hotspots</h2>
    ${(s.hotspots || []).map((h, i) => `
      <div class="hot" data-lat="${h.lat || ""}" data-lon="${h.lon || ""}">
        <span class="idx">${String(i + 1).padStart(2, "0")}</span>
        <span>${escapeHtml(street(h.intersection))}
          <em> · ${escapeHtml(h.neighborhood || h.district || "")}</em></span>
        <b>${h.n}</b>
      </div>`).join("") || "<p class='sub'>No clustered intersections yet.</p>"}
  `;
  document.querySelectorAll(".hot").forEach((el) => {
    el.onclick = () => {
      const lat = parseFloat(el.dataset.lat);
      const lon = parseFloat(el.dataset.lon);
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) map.flyTo([lat, lon], 16);
    };
  });

  const dist = document.getElementById("district");
  const current = state.district;
  const wanted = ["", ...((s.districts || []).map(String))];
  const existing = Array.from(dist.options || []).map((o) => o.value);
  // Rebuilding the <select> on every poll closes an open dropdown and
  // drops focus. Only touch the DOM when the district list changed.
  if (JSON.stringify(existing) !== JSON.stringify(wanted)) {
    const focused = document.activeElement === dist;
    dist.innerHTML = `<option value="">All districts</option>` +
      (s.districts || []).map((d) =>
        `<option ${d === current ? "selected" : ""}>${escapeHtml(d)}</option>`
      ).join("");
    if (focused) dist.focus();
  } else if (dist.value !== current) {
    dist.value = current;
  }

  const latest = s.latest_incident ? relTime(s.latest_incident) : "n/a";
  document.getElementById("statusLine").textContent =
    `${s.total} in window · ${s.open} open · newest ${latest}`;

  document.getElementById("legend").innerHTML =
    `<b>Heat includes traffic stops.</b> Passing calls stay off unless you turn off Skip noise.`;
}

function renderFeed(items, total) {
  const count = total ?? state.stats?.total ?? items.length;
  // The feed is capped (250 newest, 500 while searching) so "N shown"
  // alone hides how much is hidden. Show "N of M" when truncated.
  // Rendering is paged (FEED_PAGE at a time) so a 500-row search does
  // not build 500 cards at once on a phone.
  const shown = items.slice(0, state.feedShown);
  document.getElementById("feedCount").textContent =
    count > shown.length ? `${shown.length} of ${count} shown` : `${shown.length} shown`;
  if (!items.length) {
    document.getElementById("feed").innerHTML = `
      <div class="empty"><div class="rings"></div>No matching calls in this window.</div>`;
    return;
  }
  const more = items.length - shown.length;
  document.getElementById("feed").innerHTML = shown.map((it) => `
    <article class="card" data-cad="${escapeHtml(it.cad_number)}" style="--cat:${colorFor(it.category)}">
      <div class="kicker">
        <span>${escapeHtml(it.district || "SF")} · ${escapeHtml(relTime(it.received_datetime))}</span>
        <span class="badge ${escapeHtml(it.status)}">${escapeHtml(it.status)}</span>
      </div>
      <h3>${escapeHtml(it.call_type_final_desc || "Unknown call")}</h3>
      <p>${escapeHtml(street(it.intersection))}
         ${it.neighborhood ? " · " + escapeHtml(it.neighborhood) : ""}</p>
    </article>
  `).join("") + (more > 0
    ? `<button type="button" class="more" id="feedMore">Show more · ${more} remaining</button>`
    : "");
  document.querySelectorAll(".card").forEach((el) => {
    el.onclick = () => focusCad(el.dataset.cad);
  });
  const moreBtn = document.getElementById("feedMore");
  if (moreBtn) {
    moreBtn.onclick = () => {
      state.feedShown += FEED_PAGE;
      renderFeed(state.incidents);
    };
  }
}

function renderDetail(it) {
  const el = document.getElementById("detail");
  if (!it) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML = `
    <button type="button" class="close-detail" id="closeDetail">close</button>
    <h3>${escapeHtml(it.call_type_final_desc || "CAD")}</h3>
    <dl>
      <dt>CAD</dt><dd>${escapeHtml(it.cad_number)}</dd>
      <dt>Status</dt><dd>${escapeHtml(it.status)}</dd>
      <dt>Priority</dt><dd>${escapeHtml(it.priority || "—")}</dd>
      <dt>Agency</dt><dd>${escapeHtml(it.agency || "—")}</dd>
      <dt>Received</dt><dd>${escapeHtml(relTime(it.received_datetime))}</dd>
      <dt>On scene</dt><dd>${escapeHtml(it.onscene_datetime ? relTime(it.onscene_datetime) : "—")}</dd>
      <dt>Where</dt><dd>${escapeHtml(street(it.intersection))}</dd>
    </dl>
  `;
  document.getElementById("closeDetail").onclick = () => {
    state.selected = null;
    renderDetail(null);
    document.querySelectorAll(".card").forEach((c) => c.classList.remove("active"));
  };
}

function popupHtml(it) {
  return `<div class="incident-popup">
    <h3>${escapeHtml(it.call_type_final_desc || "CAD")}</h3>
    <p>${escapeHtml(street(it.intersection))}<br>
    ${escapeHtml(it.neighborhood || "")} · ${escapeHtml(it.district || "")} · ${escapeHtml(relTime(it.received_datetime))}</p>
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
    marker.on("click", () => focusCad(it.cad_number));
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
      0.65: "#e8a317",
      0.85: "#f97316",
      1.0: "#ef4444",
    },
  }).addTo(map);
}

function focusCad(cad) {
  const it = state.incidents.find((x) => x.cad_number === cad);
  state.selected = cad;
  document.querySelectorAll(".card").forEach((el) => {
    el.classList.toggle("active", el.dataset.cad === cad);
  });
  renderDetail(it);
  if (!it || it.lat == null) return;
  map.flyTo([it.lat, it.lon], 16);
  pinLayer.eachLayer((layer) => {
    if (layer.cad === cad) layer.openPopup();
  });
}

function paintLocal() {
  // Filtering happens server-side (see qs(): q=...), so the fetched rows
  // are exactly the visible set - even across the whole store, not just
  // the 250 newest.
  const items = state.incidents;
  renderFeed(items);
  renderPins(items);
  if (state.selected) {
    const still = items.find((x) => x.cad_number === state.selected);
    renderDetail(still || null);
  }
}

function resetFeedPaging() {
  state.feedShown = FEED_PAGE;
}

async function reload() {
  document.getElementById("pulse").classList.remove("idle");
  writeUrl();
  renderWindows();
  setPressed("heatmap", state.heatmap);
  setPressed("pins", state.pins);
  setPressed("openOnly", state.openOnly);
  setPressed("hideRoutine", state.hideRoutine);
  try {
    // Single round trip (was 3 parallel: incidents+heatmap+stats).
    const data = await getJSON(`/api/bundle?${qs()}`);
    const incidents = data.incidents || [];
    const heat = { points: data.heat || [] };
    const stats = data.stats;
    state.incidents = incidents;
    state.heat = heat.points || [];
    state.stats = stats;
    resetFeedPaging();
    renderCats(stats);
    renderStats(stats);
    renderHeat(state.heat);
    paintLocal();
  } catch (err) {
    document.getElementById("statusLine").textContent = `error: ${err.message}`;
    document.getElementById("pulse").classList.add("idle");
  }
}

document.getElementById("windows").onclick = (e) => {
  const btn = e.target.closest("[data-window]");
  if (!btn) return;
  state.window = btn.dataset.window;
  reload();
};
document.getElementById("district").onchange = (e) => {
  state.district = e.target.value;
  reload();
};
document.getElementById("heatmap").onclick = () => {
  // Local-only toggle: reuse the cached heat points, no refetch.
  state.heatmap = !state.heatmap;
  setPressed("heatmap", state.heatmap);
  renderHeat(state.heat || []);
};
document.getElementById("pins").onclick = () => {
  state.pins = !state.pins;
  setPressed("pins", state.pins);
  renderPins(state.incidents);
};
document.getElementById("openOnly").onclick = () => {
  state.openOnly = !state.openOnly;
  reload();
};
document.getElementById("hideRoutine").onclick = () => {
  state.hideRoutine = !state.hideRoutine;
  reload();
};
let qTimer = null;
document.getElementById("q").addEventListener("input", (e) => {
  state.q = e.target.value;
  writeUrl();
  // Debounce: search runs server-side over the whole store.
  clearTimeout(qTimer);
  qTimer = setTimeout(reload, 200);
});
document.getElementById("refresh").onclick = async () => {
  document.getElementById("statusLine").textContent = "syncing CAD…";
  await fetch("/api/refresh", { method: "POST" });
  reload();
};
document.getElementById("feedToggle").onclick = () => {
  document.getElementById("panel").classList.toggle("open");
};
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
    e.preventDefault();
    document.getElementById("q").focus();
  }
  if (e.key === "Escape") {
    state.selected = null;
    renderDetail(null);
  }
});

readUrl();
document.getElementById("q").value = state.q;
initBasemap();
reload();
setInterval(() => {
  // Skip the bundle fetch while backgrounded; refresh on return.
  if (!document.hidden) reload();
}, 60000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) reload();
});
