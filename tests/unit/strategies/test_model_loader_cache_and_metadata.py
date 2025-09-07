from pathlib import Path

from strategies.ml_utils import model_loader as ml


class _DummyModel:
    def __init__(self):
        self.n_features_in_ = 5
        self.version = "1.2.3"


def test_model_loader_cache_and_metadata(tmp_path, monkeypatch):
    # Ensure joblib is present via monkeypatch
    class _DummyJoblib:
        @staticmethod
        def load(p):
            return _DummyModel()

    monkeypatch.setattr(ml, "joblib", _DummyJoblib())
    monkeypatch.setattr(ml, "HAS_JOBLIB", True)

    # Create a fake model file path under strategies/models/
    strategies_dir = Path(ml.__file__).resolve().parent.parent
    models_dir = strategies_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    fpath = models_dir / "dummy_cache_meta.joblib"
    fpath.write_bytes(b"dummy")

    # Clear cache and load
    ml.ModelLoader.clear_cache()
    m1 = ml.ModelLoader.load_model(f"models/{fpath.name}")
    assert m1 is not None
    # Load again; should come from cache (same identity)
    m2 = ml.ModelLoader.load_model(f"strategies/models/{fpath.name}")
    assert m2 is m1

    # Metadata extraction
    meta = ml.ModelLoader.get_model_metadata(m1)
    assert meta.get("model_class") == _DummyModel.__name__
    assert meta.get("n_features_in") == 5
    assert meta.get("model_version") == "1.2.3"

