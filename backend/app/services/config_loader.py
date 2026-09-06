"""Loads stream taxonomy configs + roles config from backend/configs.

Everything the app needs to run (skill taxonomy, target roles, learning
resources, generator templates) lives here so streams are re-seedable via
config, never hardcoded in application logic.
"""
import json
from functools import lru_cache

from app.config import BASE_DIR

CONFIGS_DIR = BASE_DIR / "configs"


@lru_cache(maxsize=32)
def _load_json(name: str) -> dict:
    return json.loads((CONFIGS_DIR / name).read_text(encoding="utf-8"))


def reload_configs() -> None:
    """Drop caches after a live reseed so new configs are picked up."""
    _load_json.cache_clear()


def list_streams() -> list[dict]:
    return _load_json("streams.json")["streams"]


def stream_keys() -> list[str]:
    return [s["key"] for s in list_streams()]


def stream_config(stream: str) -> dict:
    path = CONFIGS_DIR / f"stream_{stream}.json"
    if not path.exists():
        raise FileNotFoundError(f"No config for stream '{stream}' ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def roles_config() -> list[dict]:
    return _load_json("roles.json")["roles"]
