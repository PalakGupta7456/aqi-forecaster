"""Realistic synthetic data with the same schema as the live API.

Used by the unit tests and for running the pipeline offline
(`python -m aqi.synthetic`). Pollution follows daily cycles, weekly cycles,
city-specific baselines and weather effects (wind and rain clean the air,
a low boundary layer traps it).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CITIES, DATA_DIR

BASE = {"Delhi": 140, "Lucknow": 120, "Patna": 125, "Kolkata": 85, "Ahmedabad": 70,
        "Mumbai": 45, "Pune": 50, "Hyderabad": 48, "Chennai": 35, "Bengaluru": 32}


def generate(days: int = 60, forecast_hours: int = 48, seed: int = 7, end: pd.Timestamp | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = end or pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).floor("h")
    times = pd.date_range(end - pd.Timedelta(days=days), end + pd.Timedelta(hours=forecast_hours), freq="h")
    n = len(times)
    hour = times.hour.values
    frames = []
    for city in CITIES:
        base = BASE.get(city.name, 60)
        temp = 24 + 6 * np.sin(2 * np.pi * (hour - 9) / 24) + rng.normal(0, 1, n)
        wind = np.clip(8 + 4 * np.sin(2 * np.pi * (hour - 14) / 24) + rng.normal(0, 2.5, n), 0.2, None)
        rain = np.where(rng.random(n) < 0.04, rng.exponential(3, n), 0.0)
        blh = np.clip(400 + 900 * np.clip(np.sin(2 * np.pi * (hour - 7) / 24), 0, None) + rng.normal(0, 80, n), 50, None)
        noise = np.zeros(n)
        for i in range(1, n):
            noise[i] = 0.92 * noise[i - 1] + rng.normal(0, 6)
        diurnal = 1 + 0.35 * np.cos(2 * np.pi * (hour - 22) / 24)
        weekly = 1 - 0.08 * (times.dayofweek.values >= 5)
        pm25 = base * diurnal * weekly * (900 / (blh + 500)) * (10 / (wind + 5)) * np.exp(-0.15 * rain)
        pm25 = np.clip(pm25 + noise, 2, None)
        frames.append(pd.DataFrame({
            "city": city.name, "time": times,
            "pm2_5": pm25.round(1), "pm10": (pm25 * rng.uniform(1.5, 1.9, n)).round(1),
            "carbon_monoxide": (300 + 6 * pm25 + rng.normal(0, 30, n)).round(0),
            "nitrogen_dioxide": np.clip(20 + 0.2 * pm25 + rng.normal(0, 4, n), 1, None).round(1),
            "ozone": np.clip(60 + 30 * np.sin(2 * np.pi * (hour - 9) / 24) + rng.normal(0, 8, n), 1, None).round(1),
            "sulphur_dioxide": np.clip(8 + 0.05 * pm25 + rng.normal(0, 2, n), 0.5, None).round(1),
            "temperature_2m": temp.round(1), "relative_humidity_2m": np.clip(60 - (temp - 24) * 2 + rng.normal(0, 5, n), 10, 100).round(0),
            "wind_speed_10m": wind.round(1), "wind_direction_10m": rng.uniform(0, 360, n).round(0),
            "surface_pressure": (1005 + rng.normal(0, 2, n)).round(1), "precipitation": rain.round(1),
            "boundary_layer_height": blh.round(0),
        }))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generate().to_parquet(DATA_DIR / "raw.parquet", index=False)
    print(f"Synthetic data written to {DATA_DIR / 'raw.parquet'}")


if __name__ == "__main__":
    main()
