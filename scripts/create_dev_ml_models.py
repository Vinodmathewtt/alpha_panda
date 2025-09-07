"""
Create development ML models with the correct input feature dimensions for
the sample ML strategies so they can register and run in development.

This script is safe for development/testing and produces tiny RandomForest
classifiers with synthetic data. It does NOT require any external datasets.

Models created under strategies/models/:
- momentum_v1.joblib          (5 features – matches MLMomentumProcessor)
- mean_reversion_v1.joblib    (4 features – matches MLMeanReversionProcessor)
- breakout_v1.joblib          (4 features – matches MLBreakoutProcessor)
- sample_momentum_v1.joblib   (for compatibility with older examples)

Usage:
    python scripts/create_dev_ml_models.py

After running, ensure your DB strategy rows reference these filenames in
parameters.model_path, or re-seed from YAMLs.
"""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib


def _train_and_save_model(n_features: int, out_path: Path) -> None:
    rng = np.random.default_rng(42)
    n_samples = 500
    X = rng.normal(size=(n_samples, n_features)).astype(np.float32)
    # Simple separable classes based on sum of features
    y = (X.sum(axis=1) > 0).astype(int)

    clf = RandomForestClassifier(n_estimators=25, max_depth=6, random_state=42)
    clf.fit(X, y)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, str(out_path))
    print(f"✅ Wrote model: {out_path} (features={n_features})")


def main() -> None:
    here = Path(__file__).resolve().parent
    models_dir = here.parent / "strategies" / "models"
    # Ensure directory exists
    models_dir.mkdir(parents=True, exist_ok=True)

    # Strategy-specific models
    _train_and_save_model(5, models_dir / "momentum_v1.joblib")
    _train_and_save_model(4, models_dir / "mean_reversion_v1.joblib")
    _train_and_save_model(4, models_dir / "breakout_v1.joblib")

    # Back-compat sample file (4 features)
    _train_and_save_model(4, models_dir / "sample_momentum_v1.joblib")

    print("\nAll development models created.\n")
    print("Next steps:")
    print("- Verify your DB strategy rows reference these filenames in parameters.model_path")
    print("- Or re-seed from YAMLs to sync configuration")


if __name__ == "__main__":
    main()

