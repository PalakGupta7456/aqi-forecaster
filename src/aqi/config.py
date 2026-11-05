"""Project configuration: cities, pollutants and model settings."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
SITE_DATA_DIR = ROOT / "docs" / "data"


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float


CITIES: list[City] = [
    City("Delhi", 28.6139, 77.2090),
    City("Mumbai", 19.0760, 72.8777),
    City("Kolkata", 22.5726, 88.3639),
    City("Chennai", 13.0827, 80.2707),
    City("Bengaluru", 12.9716, 77.5946),
    City("Hyderabad", 17.3850, 78.4867),
    City("Lucknow", 26.8467, 80.9462),
    City("Patna", 25.5941, 85.1376),
    City("Ahmedabad", 23.0225, 72.5714),
    City("Pune", 18.5204, 73.8567),
]

AIR_VARS = ["pm2_5", "pm10", "carbon_monoxide", "nitrogen_dioxide", "ozone", "sulphur_dioxide"]
WEATHER_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "precipitation",
    "boundary_layer_height",
]

TARGET = "pm2_5"
HORIZONS = list(range(1, 25))  # forecast 1..24 hours ahead
LAGS = [1, 2, 3, 6, 12, 24, 48]
ROLL_WINDOWS = [3, 6, 12, 24]
HISTORY_DAYS = 92  # Open-Meteo allows up to 92 past days
