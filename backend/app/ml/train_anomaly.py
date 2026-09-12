"""Train the IsolationForest anomaly detector and report precision/recall."""
from __future__ import annotations

import json
import os

import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.ml import registry
from app.ml.generate_data import generate_movement_data

FEATURES = ["speed_kmh", "dist_from_prev_m", "inactivity_min", "dist_from_route_m"]


def train(models_dir: str = "ml_models") -> dict:
    os.makedirs(models_dir, exist_ok=True)
    df = generate_movement_data()
    X = df[FEATURES].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler().fit(X_train)
    Xtr, Xte = scaler.transform(X_train), scaler.transform(X_test)

    contamination = float(y_train.mean())  # expected anomaly fraction
    model = IsolationForest(
        n_estimators=200, contamination=contamination, random_state=42, n_jobs=-1
    )
    # Unsupervised: fit on training features only
    model.fit(Xtr)

    # Evaluate against known labels: predict -1 (anomaly) / 1 (normal)
    pred = model.predict(Xte)
    y_pred = (pred == -1).astype(int)
    scores = -model.decision_function(Xte)  # higher = more anomalous

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", zero_division=0
    )
    auc = roc_auc_score(y_test, scores)

    joblib.dump(model, os.path.join(models_dir, "anomaly_isoforest.joblib"))
    joblib.dump(scaler, os.path.join(models_dir, "anomaly_scaler.joblib"))

    # Reference distribution for live drift monitoring (app/services/drift.py).
    # speed_kmh is the one feature both this training set and the live
    # LocationPing table actually record, so it's the one drift can honestly
    # compare -- the other three engineered features aren't persisted per ping.
    # Built from the NORMAL-labelled rows only: `df` also contains the
    # synthetic injected anomalies (including the ~150-260 km/h abduction
    # scenario), and drift is "does live traffic still look like ordinary
    # behaviour", not "does it look like our anomaly-injected training mix".
    normal_speeds = df.loc[df["label"] == 0, "speed_kmh"].values
    registry.save_reference_distribution(models_dir, "speed_kmh", normal_speeds)

    # Persist the actual evaluation curve and matrix so the dashboard renders
    # measured results rather than numbers retyped from a console log.
    fpr, tpr, _ = roc_curve(y_test, scores)
    step = max(1, len(fpr) // 100)  # thin to ~100 points for the chart
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()

    metrics = {
        "model": "IsolationForest",
        "task": "anomaly detection (unsupervised)",
        "features": FEATURES,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "contamination": round(contamination, 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "roc_auc": round(float(auc), 4),
        "confusion_matrix": {
            "true_negative": int(tn), "false_positive": int(fp),
            "false_negative": int(fn), "true_positive": int(tp),
        },
        "roc_curve": [
            {"fpr": round(float(a), 4), "tpr": round(float(b), 4)}
            for a, b in zip(fpr[::step], tpr[::step], strict=True)
        ],
    }
    version_record = registry.record_version(
        models_dir, "anomaly", registry.dataset_hash(df), metrics,
        active_files=["anomaly_isoforest.joblib", "anomaly_scaler.joblib"],
    )
    metrics["version"] = version_record["version"]

    print("=== IsolationForest anomaly detector ===")
    print(classification_report(y_test, y_pred, target_names=["normal", "anomaly"],
                                zero_division=0))
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    train()
