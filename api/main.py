"""FastAPI model-serving API.

Run locally:   uvicorn api.main:app --reload
Docker:        docker run -p 8000:8000 ghcr.io/<user>/aqi-forecaster
Docs:          http://localhost:8000/docs
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from contextlib import asynccontextmanager
from functools import lru_cache

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aqi import __version__
from aqi.aqi_index import aqi, category
from aqi.config import CITIES, MODEL_DIR
from aqi.ingest import fetch
from aqi.predict import forecast

log = logging.getLogger("api")
STATE: dict = {}
CACHE_SECONDS = 15 * 60


def _ensure_model() -> None:
    """Load the model from disk, downloading it first if MODEL_URL is set."""
    path = MODEL_DIR / "model.joblib"
    url = os.getenv("MODEL_URL")
    if not path.exists() and url:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        log.info("Downloading model from %s", url)
        urllib.request.urlretrieve(url, path)
        metrics_url = url.rsplit("/", 1)[0] + "/metrics.json"
        try:
            urllib.request.urlretrieve(metrics_url, MODEL_DIR / "metrics.json")
        except Exception:  # noqa: BLE001
            pass
    if path.exists():
        STATE["bundle"] = joblib.load(path)
        metrics = MODEL_DIR / "metrics.json"
        STATE["metrics"] = json.loads(metrics.read_text()) if metrics.exists() else {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_model()
    yield


app = FastAPI(title="AQI Forecaster API", version=__version__, lifespan=lifespan,
              description="24-hour PM2.5 and AQI forecasts for Indian cities from live Open-Meteo data.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


class HourForecast(BaseModel):
    time: str
    horizon_h: int
    pm2_5: float
    aqi: float
    category: str


class CityForecast(BaseModel):
    city: str
    issued_at: str
    model: str
    forecast: list[HourForecast]


@lru_cache(maxsize=1)
def _live_data(bucket: int) -> pd.DataFrame:
    """Fetch live data at most once per cache window (bucket = time // window)."""
    return fetch(past_days=7)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": "bundle" in STATE, "version": __version__}


@app.get("/cities")
def cities() -> list[dict]:
    return [{"name": c.name, "lat": c.lat, "lon": c.lon} for c in CITIES]


@app.get("/model")
def model_info() -> dict:
    if "bundle" not in STATE:
        raise HTTPException(503, "Model not loaded")
    return STATE.get("metrics", {"best_model": STATE["bundle"]["name"]})


@app.get("/forecast/{city}", response_model=CityForecast)
def city_forecast(city: str) -> CityForecast:
    if "bundle" not in STATE:
        raise HTTPException(503, "Model not loaded")
    match = next((c.name for c in CITIES if c.name.lower() == city.lower()), None)
    if match is None:
        raise HTTPException(404, f"Unknown city '{city}'. See /cities")
    raw = _live_data(int(time.time() // CACHE_SECONDS))
    fc = forecast(raw, STATE["bundle"])
    fc = fc[fc["city"] == match].sort_values("horizon")
    hours = []
    for r in fc.itertuples():
        idx = aqi(r.pred)
        hours.append(HourForecast(time=pd.Timestamp(r.target_time).isoformat(), horizon_h=int(r.horizon),
                                  pm2_5=float(r.pred), aqi=idx, category=category(idx)[0]))
    return CityForecast(city=match, issued_at=pd.Timestamp(fc["issue_time"].iloc[0]).isoformat(),
                        model=STATE["bundle"]["name"], forecast=hours)
