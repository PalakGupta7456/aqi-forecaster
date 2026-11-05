"""Generate the live 24-hour forecast and the JSON that powers the dashboard."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd

from .aqi_index import aqi, category
from .config import CITIES, DATA_DIR, MODEL_DIR, SITE_DATA_DIR
from .features import build_training_frame
from .ingest import split_observed

log = logging.getLogger(__name__)
HISTORY_HOURS = 72
LOG_KEEP_DAYS = 30


def _r(x, n=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def forecast(raw: pd.DataFrame, bundle: dict, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Return rows (city, issue_time, horizon, target_time, pred, cams) for the latest issue hour."""
    observed, future = split_observed(raw, now)
    issue = observed.groupby("city")["time"].max()
    frame = build_training_frame(raw)
    frame = frame[frame["time"].eq(frame["city"].map(issue))]
    pred = np.clip(bundle["model"].predict(frame[bundle["features"]]), 0, None)
    return pd.DataFrame({
        "city": frame["city"].values, "issue_time": frame["time"].values, "horizon": frame["horizon"].values,
        "target_time": frame["target_time"].values, "pred": pred.round(2),
        "cams": frame["target"].values,  # Open-Meteo/CAMS physics-model forecast, shown for reference
    })


def update_log(fc: pd.DataFrame, observed: pd.DataFrame, path) -> dict:
    """Append forecasts, score the ones whose target hour has passed (live accuracy)."""
    cols = ["city", "issue_time", "horizon", "target_time", "pred"]
    log_df = pd.read_csv(path, parse_dates=["issue_time", "target_time"]) if path.exists() else pd.DataFrame(columns=cols)
    log_df = pd.concat([log_df[cols], fc[cols]]).drop_duplicates(["city", "issue_time", "horizon"], keep="last")
    cutoff = pd.Timestamp(fc["issue_time"].max()) - pd.Timedelta(days=LOG_KEEP_DAYS)
    log_df = log_df[pd.to_datetime(log_df["issue_time"]) >= cutoff]
    log_df.to_csv(path, index=False)

    actual = observed[["city", "time", "pm2_5"]].rename(columns={"time": "target_time", "pm2_5": "actual"})
    scored = log_df.assign(target_time=pd.to_datetime(log_df["target_time"])).merge(actual, on=["city", "target_time"])
    if scored.empty:
        return {"n_scored": 0}
    err = (scored["pred"] - scored["actual"]).abs()
    return {"n_scored": int(len(scored)), "mae": _r(err.mean(), 2),
            "mae_6h": _r(err[scored["horizon"] <= 6].mean(), 2), "mae_24h": _r(err[scored["horizon"] > 18].mean(), 2)}


def build_site_payload(raw: pd.DataFrame, fc: pd.DataFrame, metrics: dict, live: dict, now=None) -> dict:
    observed, _ = split_observed(raw, now)
    cities = []
    for c in CITIES:
        hist = observed[observed["city"] == c.name].tail(HISTORY_HOURS)
        if hist.empty:
            continue
        last = hist.iloc[-1]
        f = fc[fc["city"] == c.name].sort_values("horizon")
        idx = aqi(last["pm2_5"], last["pm10"])
        label, color = category(idx)
        peak = f.loc[f["pred"].idxmax()] if not f.empty else None
        peak_aqi = aqi(peak["pred"]) if peak is not None else None
        cities.append({
            "name": c.name, "lat": c.lat, "lon": c.lon,
            "now": {
                "time": last["time"].isoformat(), "aqi": idx, "category": label, "color": color,
                "pm2_5": _r(last["pm2_5"]), "pm10": _r(last["pm10"]), "no2": _r(last["nitrogen_dioxide"]),
                "o3": _r(last["ozone"]), "so2": _r(last["sulphur_dioxide"]), "co": _r(last["carbon_monoxide"], 0),
                "temp": _r(last["temperature_2m"]), "humidity": _r(last["relative_humidity_2m"], 0),
                "wind": _r(last["wind_speed_10m"]),
            },
            "history": {"time": [t.isoformat() for t in hist["time"]], "pm2_5": [_r(v) for v in hist["pm2_5"]]},
            "forecast": {"time": [pd.Timestamp(t).isoformat() for t in f["target_time"]],
                         "pm2_5": [_r(v) for v in f["pred"]], "cams": [_r(v) for v in f["cams"]],
                         "aqi": [aqi(v) for v in f["pred"]]},
            "peak": None if peak is None else {"time": pd.Timestamp(peak["target_time"]).isoformat(),
                                               "pm2_5": _r(peak["pred"]), "aqi": peak_aqi,
                                               "category": category(peak_aqi)[0]},
        })
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": metrics, "live_accuracy": live, "cities": cities}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    raw = pd.read_parquet(DATA_DIR / "raw.parquet")
    bundle = joblib.load(MODEL_DIR / "model.joblib")
    metrics = json.loads((MODEL_DIR / "metrics.json").read_text())
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    fc = forecast(raw, bundle)
    observed, _ = split_observed(raw)
    live = update_log(fc, observed, SITE_DATA_DIR / "forecast_log.csv")
    payload = build_site_payload(raw, fc, metrics, live)
    (SITE_DATA_DIR / "forecast.json").write_text(json.dumps(payload, separators=(",", ":")))
    log.info("Wrote forecast for %d cities", len(payload["cities"]))


if __name__ == "__main__":
    main()
