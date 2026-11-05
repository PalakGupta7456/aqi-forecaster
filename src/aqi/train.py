"""Train and compare models; keep the best one.

Models compared on a time-based hold-out (last 14 days):
  * Persistence baseline  - "PM2.5 stays where it is now"
  * XGBoost regressor
  * LightGBM regressor
The winner is retrained on all data and saved with its metrics.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .config import DATA_DIR, MODEL_DIR
from .features import build_training_frame, feature_columns
from .ingest import split_observed

log = logging.getLogger(__name__)
TEST_DAYS = 14


def make_models(seed: int = 42) -> dict:
    return {
        "xgboost": xgb.XGBRegressor(
            n_estimators=600, learning_rate=0.05, max_depth=7, subsample=0.8,
            colsample_bytree=0.8, min_child_weight=3, tree_method="hist", random_state=seed, n_jobs=-1,
        ),
        "lightgbm": lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.04, num_leaves=63, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, min_child_samples=30, random_state=seed, n_jobs=-1, verbose=-1,
        ),
    }


def _metrics(y_true, y_pred) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def _log_mlflow(results: dict, best: str) -> None:
    """Log to MLflow when it is installed (local ./mlruns or MLFLOW_TRACKING_URI)."""
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_experiment("aqi-forecaster")
    for name, res in results.items():
        with mlflow.start_run(run_name=name):
            mlflow.log_metrics({k: v for k, v in res.items() if isinstance(v, (int, float))})
            mlflow.set_tag("selected", str(name == best))


def train(raw: pd.DataFrame) -> dict:
    observed, _ = split_observed(raw)
    frame = build_training_frame(observed).dropna(subset=["target"])
    feats = feature_columns(frame)

    cutoff = frame["time"].max() - pd.Timedelta(days=TEST_DAYS)
    tr, te = frame[frame["time"] <= cutoff], frame[frame["target_time"] > cutoff + pd.Timedelta(hours=24)]
    log.info("Train rows %d | test rows %d | features %d", len(tr), len(te), len(feats))

    results: dict[str, dict] = {"persistence": _metrics(te["target"], te["pm25_now"])}
    fitted = {}
    for name, model in make_models().items():
        model.fit(tr[feats], tr["target"])
        pred = np.clip(model.predict(te[feats]), 0, None)
        results[name] = _metrics(te["target"], pred)
        fitted[name] = (model, pred)
        log.info("%s: %s", name, results[name])

    best = min(fitted, key=lambda n: results[n]["mae"])
    base_mae = results["persistence"]["mae"]
    skill = 1 - results[best]["mae"] / base_mae if base_mae else 0.0

    # Error by horizon for the dashboard
    te = te.assign(pred=fitted[best][1], abs_err=lambda d: (d["pred"] - d["target"]).abs(),
                   base_err=lambda d: (d["pm25_now"] - d["target"]).abs())
    by_h = te.groupby("horizon")[["abs_err", "base_err"]].mean().round(2)

    # Feature importance (gain) from the winning model
    model = fitted[best][0]
    imp = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False).head(15)

    # Refit winner on all data for production
    final = make_models()[best].fit(frame[feats], frame["target"])
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": feats, "name": best}, MODEL_DIR / "model.joblib")

    report = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "best_model": best,
        "skill_vs_persistence": round(skill, 4),
        "models": results,
        "mae_by_horizon": {"horizon": by_h.index.tolist(), "model": by_h["abs_err"].tolist(),
                           "persistence": by_h["base_err"].tolist()},
        "feature_importance": {k: round(float(v / imp.sum()), 4) for k, v in imp.items()},
        "n_train": int(len(tr)), "n_test": int(len(te)), "n_features": len(feats),
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(report, indent=2))
    if os.getenv("MLFLOW_LOG", "0") == "1":
        _log_mlflow(results, best)
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    raw = pd.read_parquet(DATA_DIR / "raw.parquet")
    report = train(raw)
    log.info("Best: %s, skill vs persistence %.1f%%", report["best_model"], 100 * report["skill_vs_persistence"])


if __name__ == "__main__":
    main()
