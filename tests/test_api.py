import pandas as pd
import pytest
from fastapi.testclient import TestClient

from aqi.synthetic import generate


@pytest.fixture(scope="module")
def client():
    from api import main

    if not (main.MODEL_DIR / "model.joblib").exists():
        pytest.skip("No trained model available")
    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).floor("h")
    main._live_data = lambda bucket: generate(days=5, end=now)  # no network in tests
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["model_loaded"] is True


def test_unknown_city(client):
    assert client.get("/forecast/atlantis").status_code == 404


def test_forecast(client):
    r = client.get("/forecast/delhi")
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "Delhi"
    assert len(body["forecast"]) == 24
    assert all(h["pm2_5"] >= 0 for h in body["forecast"])
