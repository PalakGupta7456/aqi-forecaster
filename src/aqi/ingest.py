"""Pull live hourly air-quality and weather data from the free Open-Meteo APIs.

No API key is required. Both endpoints accept a comma-separated list of
coordinates, so all cities are fetched in two HTTP calls.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests

from .config import AIR_VARS, CITIES, DATA_DIR, HISTORY_DAYS, WEATHER_VARS, City

log = logging.getLogger(__name__)

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _get(url: str, params: dict, retries: int = 4) -> list[dict]:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            payload = r.json()
            return payload if isinstance(payload, list) else [payload]
        except requests.RequestException as exc:  # pragma: no cover - network
            wait = 2**attempt
            log.warning("Request failed (%s), retrying in %ss", exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"Could not fetch {url}")


def _to_frame(payloads: list[dict], cities: list[City], variables: list[str]) -> pd.DataFrame:
    frames = []
    for city, payload in zip(cities, payloads, strict=True):
        hourly = payload["hourly"]
        df = pd.DataFrame({v: hourly.get(v) for v in variables})
        df.insert(0, "time", pd.to_datetime(hourly["time"]))
        df.insert(0, "city", city.name)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def fetch(cities: list[City] = CITIES, past_days: int = HISTORY_DAYS, forecast_days: int = 2) -> pd.DataFrame:
    """Return one tidy hourly table: city, time, pollutants, weather."""
    common = {
        "latitude": ",".join(str(c.lat) for c in cities),
        "longitude": ",".join(str(c.lon) for c in cities),
        "timezone": "Asia/Kolkata",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    air = _to_frame(_get(AIR_URL, {**common, "hourly": ",".join(AIR_VARS)}), cities, AIR_VARS)
    wx = _to_frame(_get(WEATHER_URL, {**common, "hourly": ",".join(WEATHER_VARS)}), cities, WEATHER_VARS)
    df = air.merge(wx, on=["city", "time"], how="left")
    return df.sort_values(["city", "time"]).reset_index(drop=True)


def split_observed(df: pd.DataFrame, now: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into observed history (<= now) and future weather rows (> now)."""
    now = now or pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).floor("h")
    return df[df["time"] <= now].copy(), df[df["time"] > now].copy()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = fetch()
    out = DATA_DIR / "raw.parquet"
    df.to_parquet(out, index=False)
    log.info("Saved %d rows for %d cities to %s", len(df), df["city"].nunique(), out)


if __name__ == "__main__":
    main()
