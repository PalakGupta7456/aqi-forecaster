"""Feature engineering for direct multi-horizon PM2.5 forecasting.

One row = (city, issue time t, horizon h). The target is PM2.5 at t+h.
Features combine what is known at issue time t (pollution lags and rolling
stats) with the *weather forecast* for the target hour t+h, which is how
operational air-quality forecasts are built.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AIR_VARS, CITIES, HORIZONS, LAGS, ROLL_WINDOWS, TARGET, WEATHER_VARS

CITY_CODES = {c.name: i for i, c in enumerate(CITIES)}


def _issue_features(g: pd.DataFrame) -> pd.DataFrame:
    """Features available at issue time t for one city (g sorted by time)."""
    out = pd.DataFrame({"time": g["time"].values})
    y = g[TARGET].astype(float).reset_index(drop=True)
    out["pm25_now"] = y
    for lag in LAGS:
        out[f"pm25_lag_{lag}"] = y.shift(lag)
    for w in ROLL_WINDOWS:
        out[f"pm25_roll_mean_{w}"] = y.rolling(w, min_periods=1).mean()
        out[f"pm25_roll_std_{w}"] = y.rolling(w, min_periods=2).std()
    out["pm25_diff_1"] = y.diff(1)
    out["pm25_diff_24"] = y.diff(24)
    for v in AIR_VARS:
        if v != TARGET:
            out[f"{v}_now"] = g[v].astype(float).values
    return out


def _target_hour_features(times: pd.Series) -> pd.DataFrame:
    hour = times.dt.hour
    dow = times.dt.dayofweek
    return pd.DataFrame(
        {
            "tgt_hour_sin": np.sin(2 * np.pi * hour / 24),
            "tgt_hour_cos": np.cos(2 * np.pi * hour / 24),
            "tgt_dow_sin": np.sin(2 * np.pi * dow / 7),
            "tgt_dow_cos": np.cos(2 * np.pi * dow / 7),
            "tgt_is_weekend": (dow >= 5).astype(int),
        }
    )


def _wind_components(df: pd.DataFrame) -> pd.DataFrame:
    rad = np.deg2rad(df["wind_direction_10m"].astype(float))
    df["wind_u"] = df["wind_speed_10m"] * np.sin(rad)
    df["wind_v"] = df["wind_speed_10m"] * np.cos(rad)
    return df.drop(columns=["wind_direction_10m"])


def build_training_frame(df: pd.DataFrame, horizons: list[int] = HORIZONS) -> pd.DataFrame:
    """Expand an hourly table into (issue time, horizon) training rows."""
    rows = []
    weather_cols = [c for c in WEATHER_VARS if c != "wind_direction_10m"] + ["wind_u", "wind_v"]
    for city, g in df.sort_values("time").groupby("city"):
        g = _wind_components(g.reset_index(drop=True).copy())
        base = _issue_features(g)
        for h in horizons:
            block = base.copy()
            block["horizon"] = h
            block["target_time"] = block["time"] + pd.Timedelta(hours=h)
            future = g[["time", TARGET, *weather_cols]].rename(columns={"time": "target_time", TARGET: "target"})
            future = future.rename(columns={c: f"tgt_{c}" for c in weather_cols})
            block = block.merge(future, on="target_time", how="left")
            block = pd.concat([block.reset_index(drop=True), _target_hour_features(block["target_time"])], axis=1)
            block["city"] = city
            block["city_code"] = CITY_CODES.get(city, -1)
            rows.append(block)
    out = pd.concat(rows, ignore_index=True)
    return out


def feature_columns(frame: pd.DataFrame) -> list[str]:
    drop = {"time", "target_time", "target", "city"}
    return [c for c in frame.columns if c not in drop]
