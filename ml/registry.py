import pickle
import logging
from pathlib import Path

log = logging.getLogger("statrush.registry")
_registry = {}

def load_all(model_dir="./artifacts/models", version="v4"):
    base = Path(model_dir)
    if not base.exists():
        log.warning(f"[registry] Model dir '{model_dir}' not found — using stub models (dev mode)")
        return
    loaded = 0
    for path in base.glob("*.pkl"):
        try:
            with open(path, "rb") as f:
                _registry[path.stem] = pickle.load(f)
            loaded += 1
        except Exception as e:
            log.warning(f"[registry] Failed to load {path.name}: {e}")
    if loaded > 0:
        log.info(f"[registry] Loaded {loaded} models from {model_dir}")
    else:
        log.warning(f"[registry] No models found in {model_dir} — using stub models (dev mode)")

def get(stat, algo, version="v4"):
    return _registry.get(f"{stat}_{algo}_{version}")

def save(stat, algo, model, model_dir="./artifacts/models", version="v4"):
    key = f"{stat}_{algo}_{version}"
    _registry[key] = model
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    with open(f"{model_dir}/{key}.pkl", "wb") as f:
        pickle.dump(model, f)

def list_models():
    return list(_registry.keys())

def has_model(stat, version="v4"):
    return (
        _registry.get(f"{stat}_xgb_{version}") is not None and
        _registry.get(f"{stat}_lgbm_{version}") is not None
    )
