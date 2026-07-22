"""Config Manager — reads and validates ~/.config/sopx/config.yaml (XDG).

Creates defaults on first run. Only ingestion knobs — no API keys (those
belong to the future LLM Router item).
"""
from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

DEFAULT_CONFIG_DIR = Path("~/.config/sopx").expanduser()
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"

DEFAULTS: dict = {
    "language": "pt-BR",
    "cache_enabled": True,
    "output_dir": "output/",
    "whisper": {
        "model_size": "base",
    },
    "rescue_frames": False,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict:
    """Load config from YAML file, merging with defaults."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path = config_path.expanduser()

    config = dict(DEFAULTS)

    if config_path.exists() and yaml is not None:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
            if isinstance(user_config, dict):
                config = _deep_merge(config, user_config)
        except Exception:
            pass

    return config


def save_config(config: dict, path: str | Path | None = None) -> Path:
    """Save config to YAML file. Creates parent directories."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path = config_path.expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if yaml is None:
        raise ImportError(
            "pyyaml is required for config save. Install: pip install pyyaml"
        )

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    return config_path


def ensure_config(path: str | Path | None = None) -> dict:
    """Load config, creating defaults file if missing."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path = config_path.expanduser()

    if not config_path.exists():
        save_config(DEFAULTS, config_path)

    return load_config(config_path)


def get(config: dict, key: str, default=None):
    """Get a value using dot notation (e.g. 'whisper.model_size')."""
    parts = key.split(".")
    val = config
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
        if val is None:
            return default
    return val
