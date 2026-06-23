import os
from pathlib import Path

def app_root() -> Path:
    return Path(os.environ.get("APP_ROOT", "/app"))

def config_path(name: str) -> Path:
    return app_root() / "config" / name

def data_path(name: str) -> Path:
    return app_root() / "data" / name

def ledger_path() -> Path:
    return Path(os.environ.get("SIDE_EFFECT_LEDGER", str(data_path("side_effect_ledger.json"))))

def dlq_path() -> Path:
    return Path(os.environ.get("DLQ_STATE", str(data_path("dlq_state.json"))))
