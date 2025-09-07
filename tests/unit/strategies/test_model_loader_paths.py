import os
from pathlib import Path

from strategies.ml_utils import model_loader as ml


def test_model_loader_path_normalization(tmp_path, monkeypatch):
    # Prepare a dummy model file under strategies/models/
    strategies_dir = Path(ml.__file__).resolve().parent.parent
    models_dir = strategies_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    fname = "test_model_loader_dummy.joblib"
    fpath = models_dir / fname
    fpath.write_bytes(b"dummy")

    # Monkeypatch joblib to avoid real loading
    class _DummyJoblib:
        @staticmethod
        def load(p):
            return {"loaded_from": str(p)}

    monkeypatch.setattr(ml, "joblib", _DummyJoblib())
    monkeypatch.setattr(ml, "HAS_JOBLIB", True)

    # Clear cache
    ml.ModelLoader.clear_cache()

    # Case 1: models/<file>
    m1 = ml.ModelLoader.load_model(f"models/{fname}")
    assert m1 and isinstance(m1, dict)
    assert m1["loaded_from"].endswith(str(fpath))

    # Case 2: strategies/models/<file> (should normalize to same target)
    ml.ModelLoader.clear_cache()
    m2 = ml.ModelLoader.load_model(f"strategies/models/{fname}")
    assert m2 and isinstance(m2, dict)
    assert m2["loaded_from"].endswith(str(fpath))

