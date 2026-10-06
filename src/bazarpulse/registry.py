"""A small model registry kept in git: models/registry.json + gzipped LightGBM models.

Git is the source of truth so the daily pipeline can serve the champion with no
external service. Every training run is also logged to MLflow (see tracking.py).
"""
import gzip
import json
import os
from datetime import UTC, datetime

import lightgbm as lgb

MODELS_DIR = "models"
REGISTRY = os.path.join(MODELS_DIR, "registry.json")
KEEP_FILES = 3


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def load():
    if not os.path.exists(REGISTRY):
        return {"champion": None, "previous": None, "decisions": []}
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def save(reg):
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)


def _model_path(version):
    return os.path.join(MODELS_DIR, f"model_v{version:04d}.txt.gz").replace(os.sep, "/")


def load_booster(entry):
    with gzip.open(entry["file"], "rt", encoding="utf-8") as f:
        return lgb.Booster(model_str=f.read())


def load_champion():
    reg = load()
    if not reg["champion"]:
        raise RuntimeError("no champion model registered - run `python -m bazarpulse.train --initial`")
    return load_booster(reg["champion"]), reg["champion"]


def register(booster, config, trained_until, backtest, decision):
    """Store a new champion version; the old champion becomes `previous` (rollback target)."""
    reg = load()
    version = 1 + max([d.get("version", 0) for d in reg["decisions"]] + [0])
    path = _model_path(version)
    os.makedirs(MODELS_DIR, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(booster.model_to_string())
    entry = {"version": version, "config": config, "file": path, "trained_until": str(trained_until),
             "trained_at": now(), "backtest": backtest}
    reg["previous"], reg["champion"] = reg["champion"], entry
    reg["decisions"].append({**decision, "version": version, "at": entry["trained_at"]})
    save(reg)
    _prune(reg)
    return entry


def log_decision(decision):
    reg = load()
    reg["decisions"].append({**decision, "at": now()})
    save(reg)


def rollback(reason):
    reg = load()
    if not reg["previous"]:
        return None
    bad = reg["champion"]
    reg["champion"], reg["previous"] = reg["previous"], None
    reg["decisions"].append({"kind": "rollback", "from_version": bad["version"],
                             "to_version": reg["champion"]["version"], "reason": reason, "at": now()})
    save(reg)
    return reg["champion"]


def _prune(reg):
    keep = {e["file"] for e in (reg["champion"], reg["previous"]) if e}
    files = sorted(f for f in os.listdir(MODELS_DIR) if f.startswith("model_v"))
    for f in files[:-KEEP_FILES]:
        p = os.path.join(MODELS_DIR, f).replace(os.sep, "/")
        if p not in keep:
            os.remove(p)
