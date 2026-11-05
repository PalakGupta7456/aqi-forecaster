"""India National Air Quality Index (NAQI, CPCB) from PM2.5 and PM10.

Official NAQI uses 24-hour averages. The dashboard applies the same
breakpoints to hourly values as a "now-cast" approximation.
"""
from __future__ import annotations

import numpy as np

# (concentration_low, concentration_high, index_low, index_high)
PM25_BREAKS = [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200), (90, 120, 200, 300), (120, 250, 300, 400), (250, 500, 400, 500)]
PM10_BREAKS = [(0, 50, 0, 50), (50, 100, 50, 100), (100, 250, 100, 200), (250, 350, 200, 300), (350, 430, 300, 400), (430, 600, 400, 500)]

CATEGORIES = [
    (50, "Good", "#2fb380"),
    (100, "Satisfactory", "#9acd32"),
    (200, "Moderate", "#f2c12e"),
    (300, "Poor", "#f28c28"),
    (400, "Very Poor", "#e5484d"),
    (500, "Severe", "#8e1f4f"),
]


def sub_index(conc: float, breaks: list[tuple]) -> float:
    if conc is None or np.isnan(conc):
        return float("nan")
    conc = max(conc, 0.0)
    for c_lo, c_hi, i_lo, i_hi in breaks:
        if conc <= c_hi:
            return i_lo + (conc - c_lo) * (i_hi - i_lo) / (c_hi - c_lo)
    return 500.0


def aqi(pm25: float, pm10: float | None = None) -> float:
    values = [sub_index(pm25, PM25_BREAKS)]
    if pm10 is not None:
        values.append(sub_index(pm10, PM10_BREAKS))
    values = [v for v in values if not np.isnan(v)]
    return round(max(values), 1) if values else float("nan")


def category(index: float) -> tuple[str, str]:
    for upper, label, color in CATEGORIES:
        if index <= upper:
            return label, color
    return CATEGORIES[-1][1], CATEGORIES[-1][2]
