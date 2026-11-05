/* AQI Forecaster dashboard: reads data/forecast.json produced by the hourly pipeline. */
(() => {
  const SCALE = [
    [50, "Good", "#2fb380"], [100, "Satisfactory", "#9acd32"], [200, "Moderate", "#f2c12e"],
    [300, "Poor", "#f28c28"], [400, "Very Poor", "#e5484d"], [500, "Severe", "#8e1f4f"],
  ];
  const catFor = (v) => SCALE.find(([u]) => v <= u) || SCALE[SCALE.length - 1];
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const $ = (id) => document.getElementById(id);
  const fmtHour = (iso) => new Date(iso).toLocaleString("en-IN", { weekday: "short", hour: "numeric", hour12: true });
  const fmtClock = (iso) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", hour12: true });

  let data, selected, seriesChart, map, markers = {};

  // Repo link: <user>.github.io/<repo>  ->  github.com/<user>/<repo>
  const host = location.hostname.split(".");
  if (host[1] === "github" && host[2] === "io") {
    $("repo-link").href = `https://github.com/${host[0]}/${location.pathname.split("/")[1]}`;
  }

  fetch("data/forecast.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { data = d; render(); })
    .catch(() => { $("updated").textContent = "Live data isn't available yet. The pipeline publishes it within the hour."; });

  function render() {
    const gen = new Date(data.generated_at);
    const mins = Math.max(0, Math.round((Date.now() - gen) / 60000));
    $("updated").textContent = `Updated ${mins < 60 ? mins + " min" : Math.round(mins / 60) + " h"} ago, refreshed hourly`;
    const ranked = [...data.cities].sort((a, b) => b.now.aqi - a.now.aqi);
    renderRanking(ranked);
    renderMap();
    renderScale();
    renderModel();
    const fromHash = decodeURIComponent(location.hash.slice(1));
    select(data.cities.find((c) => c.name === fromHash) || ranked[0]);
  }

  function renderRanking(ranked) {
    $("ranking").innerHTML = ranked.map((c) => `
      <li><button type="button" data-city="${c.name}" style="--c:${c.now.color}" aria-pressed="false">
        <span>${c.name}</span><span class="v">${Math.round(c.now.aqi)}</span>
        <span class="bar"><i style="width:${Math.min(100, c.now.aqi / 5)}%"></i></span>
      </button></li>`).join("");
    $("ranking").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b) select(data.cities.find((c) => c.name === b.dataset.city));
    });
  }

  function select(city) {
    selected = city;
    history.replaceState(null, "", "#" + encodeURIComponent(city.name));
    document.querySelectorAll("#ranking button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.city === city.name));
    const n = city.now;
    $("city-name").textContent = city.name;
    $("big-aqi").textContent = Math.round(n.aqi);
    $("big-aqi").style.setProperty("--catc", n.color);
    $("cat").textContent = n.category;
    const root = document.documentElement.style;
    root.setProperty("--haze", n.color);
    root.setProperty("--haze-opacity", (0.12 + Math.min(n.aqi, 400) / 400 * 0.45).toFixed(2));

    const p = city.peak;
    if (p) {
      const dir = p.aqi > n.aqi + 15 ? "worsen" : p.aqi < n.aqi - 15 ? "improve" : "hold steady";
      $("outlook").innerHTML = dir === "worsen"
        ? `Expected to <strong>worsen</strong>, peaking at <strong>AQI ${Math.round(p.aqi)} (${p.category})</strong> around ${fmtHour(p.time)}.`
        : `Expected to <strong>${dir}</strong> over the next 24 hours. Highest point: AQI ${Math.round(p.aqi)} around ${fmtHour(p.time)}.`;
    }
    const items = [
      ["PM2.5", n.pm2_5, "µg/m³"], ["PM10", n.pm10, "µg/m³"], ["NO₂", n.no2, "µg/m³"], ["O₃", n.o3, "µg/m³"],
      ["SO₂", n.so2, "µg/m³"], ["Temperature", n.temp, "°C"], ["Humidity", n.humidity, "%"], ["Wind", n.wind, "km/h"],
    ];
    $("pollutants").innerHTML = items.map(([k, v, u]) => `<div><dt>${k}</dt><dd>${v ?? "–"}<small>${u}</small></dd></div>`).join("");
    drawSeries(city);
    if (map && markers[city.name]) markers[city.name].openTooltip();
  }

  function drawSeries(city) {
    const h = city.history, f = city.forecast;
    const labels = [...h.time, ...f.time];
    const pad = (arr, before, after = 0) => [...Array(before).fill(null), ...arr, ...Array(after).fill(null)];
    const last = h.pm2_5[h.pm2_5.length - 1];
    const ml = pad([last, ...f.pm2_5], h.time.length - 1);
    const cams = pad([last, ...f.cams], h.time.length - 1);
    const obs = pad(h.pm2_5, 0, f.time.length);
    const grid = css("--rule"), muted = css("--muted");
    const cfg = {
      type: "line",
      data: { labels, datasets: [
        { label: "Observed", data: obs, borderColor: css("--obs"), borderWidth: 2, pointRadius: 0, tension: .25 },
        { label: "Our model", data: ml, borderColor: css("--ml"), borderWidth: 2.5, pointRadius: 0, tension: .25,
          fill: { target: "origin" }, backgroundColor: css("--ml") + "1f" },
        { label: "CAMS", data: cams, borderColor: css("--cams"), borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0, tension: .25 },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => fmtHour(labels[i[0].dataIndex]),
            label: (i) => i.raw == null ? null : `${i.dataset.label}: ${i.raw.toFixed(1)} µg/m³` } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 8,
               callback: (v) => fmtHour(labels[v]) } },
          y: { beginAtZero: true, grid: { color: grid }, ticks: { color: muted }, title: { display: true, text: "µg/m³", color: muted } },
        },
      },
      plugins: [{ id: "now", afterDraw(c) {
        const x = c.scales.x.getPixelForValue(h.time.length - 1), { top, bottom } = c.chartArea, ctx = c.ctx;
        ctx.save(); ctx.strokeStyle = muted; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        ctx.fillStyle = muted; ctx.font = "12px Instrument Sans, sans-serif"; ctx.fillText("now", x + 5, top + 12); ctx.restore();
      } }],
    };
    if (seriesChart) seriesChart.destroy();
    seriesChart = new Chart($("series"), cfg);
  }

  function renderMap() {
    map = L.map("map", { scrollWheelZoom: false, attributionControl: true }).setView([22.5, 79], 4.6);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap, &copy; CARTO", subdomains: "abcd", maxZoom: 10,
    }).addTo(map);
    data.cities.forEach((c) => {
      const m = L.circleMarker([c.lat, c.lon], {
        radius: 8 + c.now.aqi / 18, color: c.now.color, weight: 2, fillColor: c.now.color, fillOpacity: .55,
      }).addTo(map);
      m.bindTooltip(`<strong>${c.name}</strong><br>AQI ${Math.round(c.now.aqi)}, ${c.now.category}`, { direction: "top" });
      m.on("click", () => { select(c); window.scrollTo({ top: 0, behavior: "smooth" }); });
      markers[c.name] = m;
    });
    map.fitBounds(L.featureGroup(Object.values(markers)).getBounds().pad(0.15));
  }

  function renderScale() {
    let lo = 0;
    $("scale").innerHTML = SCALE.map(([u, label, c]) => { const r = `<li style="--c:${c}"><i></i>${label}<span>${lo}–${u}</span></li>`; lo = u + 1; return r; }).join("");
  }

  function renderModel() {
    const m = data.model;
    $("skill").textContent = `${Math.round(m.skill_vs_persistence * 100)}%`;
    const names = { persistence: "Persistence baseline", xgboost: "XGBoost", lightgbm: "LightGBM" };
    $("leader").querySelector("tbody").innerHTML = Object.entries(m.models).sort((a, b) => a[1].mae - b[1].mae)
      .map(([k, v]) => `<tr class="${k === m.best_model ? "win" : ""}"><td>${names[k] || k}</td><td>${v.mae}</td><td>${v.rmse}</td><td>${v.r2}</td></tr>`).join("");
    const live = data.live_accuracy;
    $("live").textContent = live && live.n_scored > 0
      ? `Live check: across ${live.n_scored.toLocaleString("en-IN")} forecasts whose hour has passed, mean error is ${live.mae} µg/m³ (${live.mae_6h} for the next 6 hours). Retrained ${new Date(m.trained_at).toLocaleDateString("en-IN")}.`
      : `Live accuracy appears once logged forecasts reach their target hour. Retrained ${new Date(m.trained_at).toLocaleDateString("en-IN")}.`;

    const muted = css("--muted"), grid = css("--rule");
    const axis = { ticks: { color: muted }, grid: { color: grid } };
    new Chart($("horizon"), {
      type: "line",
      data: { labels: m.mae_by_horizon.horizon.map((h) => h + "h"), datasets: [
        { label: names[m.best_model] || m.best_model, data: m.mae_by_horizon.model, borderColor: css("--ml"), pointRadius: 0, borderWidth: 2.5 },
        { label: "Persistence", data: m.mae_by_horizon.persistence, borderColor: css("--cams"), borderDash: [4, 3], pointRadius: 0, borderWidth: 1.5 },
      ] },
      options: { plugins: { legend: { labels: { color: muted, boxWidth: 14, boxHeight: 2 } } },
        scales: { x: { ...axis, grid: { display: false }, ticks: { color: muted, maxTicksLimit: 8 } },
                  y: { ...axis, beginAtZero: true, title: { display: true, text: "MAE, µg/m³", color: muted } } } },
    });
    const imp = Object.entries(m.feature_importance).slice(0, 10);
    const NAMES = { tgt_wind_speed_10m: "Wind speed (forecast)", tgt_boundary_layer_height: "Mixing height (forecast)",
      tgt_temperature_2m: "Temperature (forecast)", tgt_relative_humidity_2m: "Humidity (forecast)", tgt_surface_pressure: "Pressure (forecast)",
      tgt_wind_u: "East-west wind (forecast)", tgt_wind_v: "North-south wind (forecast)", tgt_precipitation: "Rain (forecast)",
      tgt_hour_sin: "Hour of day", tgt_hour_cos: "Hour of day (cos)", city_code: "City", horizon: "Hours ahead", pm25_now: "PM2.5 now" };
    const pretty = (k) => NAMES[k] || k.replace(/^pm25_/, "PM2.5 ").replace("roll_mean_", "avg last ").replace("roll_std_", "volatility last ")
      .replace("lag_", "").replace("diff_", "change ").replace(/_now$/, " now").replace(/_/g, " ");
    new Chart($("importance"), {
      type: "bar",
      data: { labels: imp.map(([k]) => pretty(k)), datasets: [{ data: imp.map(([, v]) => +(v * 100).toFixed(1)), backgroundColor: css("--ml"), borderRadius: 3 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `${i.raw}% of importance` } } },
        scales: { x: { ...axis, title: { display: true, text: "% of total importance", color: muted } }, y: { ticks: { color: muted }, grid: { display: false } } } },
    });
  }
})();
