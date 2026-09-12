"""Train all ML models and write a consolidated metrics report (metrics.json).

Run:  python -m app.ml.train_all
"""
import json
import os

from app.ml import train_anomaly, train_safety, train_zones


def main(models_dir: str = "ml_models") -> None:
    os.makedirs(models_dir, exist_ok=True)
    report = {
        "anomaly": train_anomaly.train(models_dir),
        "safety": train_safety.train(models_dir),
        "zones": train_zones.train(models_dir),
    }
    with open(os.path.join(models_dir, "metrics.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("\n=== All models trained. metrics.json written. ===")


if __name__ == "__main__":
    main()
