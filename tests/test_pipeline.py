import numpy as np
import pandas as pd
import pytest

from aqi.aqi_index import aqi, category
from aqi.config import CITIES
from aqi.features import build_training_frame, feature_columns
from aqi.synthetic import generate

NOW = pd.Timestamp("2026-01-15 12:00")


@pytest.fixture(scope="module")
def raw():
    return generate(days=12, forecast_hours=30, end=NOW)


def test_aqi_breakpoints():
    assert aqi(0) == 0
    assert aqi(30) == 50
    assert aqi(60) == 100
    assert aqi(250) == 400
    assert aqi(1000) == 500
    assert category(42)[0] == "Good"
    assert category(350)[0] == "Very Poor"


def test_aqi_uses_worst_pollutant():
    assert aqi(10, pm10=300) > aqi(10)


def test_synthetic_schema(raw):
    assert set(raw["city"]) == {c.name for c in CITIES}
    assert raw["pm2_5"].min() > 0
    assert not raw.duplicated(["city", "time"]).any()


def test_features_have_no_future_leakage(raw):
    frame = build_training_frame(raw[raw["city"] == "Delhi"], horizons=[1, 6])
    feats = feature_columns(frame)
    assert "target" not in feats
    # pm25_now must equal the observation at issue time, never the target hour
    row = frame[(frame["horizon"] == 6)].dropna(subset=["target"]).iloc[50]
    delhi = raw[raw["city"] == "Delhi"].set_index("time")["pm2_5"]
    assert row["pm25_now"] == pytest.approx(delhi[row["time"]])
    assert row["target"] == pytest.approx(delhi[row["time"] + pd.Timedelta(hours=6)])
    assert row["pm25_lag_1"] == pytest.approx(delhi[row["time"] - pd.Timedelta(hours=1)])


def test_train_and_forecast_end_to_end(raw, tmp_path, monkeypatch):
    import aqi.train as train_mod
    from aqi import predict

    monkeypatch.setattr(train_mod, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(train_mod, "TEST_DAYS", 3)
    monkeypatch.setattr(train_mod, "split_observed", lambda df: (df[df["time"] <= NOW], df[df["time"] > NOW]))
    small = {name: m.set_params(n_estimators=50) for name, m in train_mod.make_models().items()}
    monkeypatch.setattr(train_mod, "make_models", lambda seed=42: small)

    report = train_mod.train(raw)
    assert report["best_model"] in {"xgboost", "lightgbm"}
    assert report["models"][report["best_model"]]["mae"] < report["models"]["persistence"]["mae"]

    import joblib
    bundle = joblib.load(tmp_path / "model.joblib")
    fc = predict.forecast(raw, bundle, now=NOW)
    assert len(fc) == len(CITIES) * 24
    assert (fc["pred"] >= 0).all()
    payload = predict.build_site_payload(raw, fc, report, {"n_scored": 0}, now=NOW)
    assert len(payload["cities"]) == len(CITIES)
    assert len(payload["cities"][0]["forecast"]["pm2_5"]) == 24
    assert np.isfinite(payload["cities"][0]["now"]["aqi"])
