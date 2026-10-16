from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("JOBAGENT_HOME", Path.cwd())).resolve()
CONFIG = ROOT / "config"
DATA = ROOT / "data"


def _load(name: str, required: bool) -> dict:
    real, example = CONFIG / f"{name}.yaml", CONFIG / f"{name}.example.yaml"
    path = real if real.exists() else example
    if not path.exists():
        if required:
            raise SystemExit(f"Missing {real}. Run `jobagent init` first.")
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def settings() -> dict:
    return _load("settings", required=True)


def profile() -> dict:
    p = CONFIG / "profile.yaml"
    if not p.exists():
        raise SystemExit("Missing config/profile.yaml. Run `jobagent init`, then fill it in.")
    return _load("profile", required=True)


def init() -> list[str]:
    created = []
    for name in ("settings", "profile"):
        src, dst = CONFIG / f"{name}.example.yaml", CONFIG / f"{name}.yaml"
        if src.exists() and not dst.exists():
            shutil.copy(src, dst)
            created.append(str(dst.relative_to(ROOT)))
    for d in ("resumes", "data", "data/screenshots", "data/cover_letters"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    return created


def resolve(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else ROOT / p
