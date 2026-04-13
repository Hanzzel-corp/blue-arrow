#!/usr/bin/env python3
"""
Configuration management for Python modules.
Provides centralized configuration access for all Python workers.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class Config:
    """Configuration manager for Python modules."""

    _instance = None
    _config = None
    _project_root = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._project_root = self._resolve_project_root()
            self._config = self._load_config()

    def _resolve_project_root(self) -> Path:
        """Resolve project root robustly."""
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)

        current_file = Path(__file__).resolve()

        candidates = [
            current_file.parent,
            current_file.parent.parent,
            current_file.parent.parent.parent,
        ]

        for candidate in candidates:
            config_dir = candidate / "config"
            modules_dir = candidate / "modules"
            runtime_dir = candidate / "runtime"

            if config_dir.exists() and (modules_dir.exists() or runtime_dir.exists()):
                return candidate

        return current_file.parent

    @property
    def project_root(self) -> Path:
        return self._project_root

    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Load JSON file safely."""
        try:
            if not file_path.exists():
                return {}
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as error:
            raise RuntimeError(f"Invalid config in {file_path}: {error}") from error

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON files and environment variables."""
        config_dir = self.project_root / "config"

        config: Dict[str, Any] = {}

        default_config_path = config_dir / "default.json"
        config = self._load_json_file(default_config_path)

        env = os.getenv("NODE_ENV", "development")
        env_config_path = config_dir / f"{env}.json"

        if env_config_path.exists():
            env_config = self._load_json_file(env_config_path)
            config = self._merge_configs(config, env_config)

        config = self._apply_environment_overrides(config)
        return config

    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge two configuration dictionaries."""
        result = dict(base)

        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_environment_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        overrides = {
            "TELEGRAM_BOT_TOKEN": ["telegram", "bot_token"],
            "TELEGRAM_WEBHOOK_URL": ["telegram", "webhook_url"],
            "LOG_LEVEL": ["logging", "level"],
            "DEBUG_MODE": ["runtime", "debug"],
            "MESSAGE_VALIDATION": ["runtime", "message_validation"],
            "SAFETY_ENABLED": ["safety", "enabled"],
            "APPROVAL_ENABLED": ["approval", "enabled"],
            "MONITORING_ENABLED": ["monitoring", "enabled"],
            "MEMORY_RETENTION_DAYS": ["memory", "retention_days"],
            "SUPERVISOR_TASK_TIMEOUT": ["supervisor", "task_timeout"],
            "WORKER_DESKTOP_TIMEOUT": ["workers", "desktop", "timeout"],
            "WORKER_BROWSER_TIMEOUT": ["workers", "browser", "timeout"],
            "WORKER_SYSTEM_TIMEOUT": ["workers", "system", "timeout"],
        }

        for env_var, config_path in overrides.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested_value(config, config_path, self._parse_env_value(value))

        return config

    def _parse_env_value(self, value: str) -> Union[str, int, float, bool, Dict[str, Any], List[Any]]:
        """Parse environment variable value to appropriate type."""
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _set_nested_value(self, obj: Dict[str, Any], path: List[str], value: Any) -> None:
        """Set a nested value in a dictionary using a path list."""
        current = obj

        for key in path[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        current[path[-1]] = value

    def get(self, path_value: Union[str, List[str]], default: Any = None) -> Any:
        """Get config value by dotted path or path list."""
        path = path_value.split(".") if isinstance(path_value, str) else path_value
        current: Any = self._config

        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]

        return current

    def has(self, path_value: Union[str, List[str]]) -> bool:
        """Check if config path exists."""
        sentinel = object()
        return self.get(path_value, sentinel) is not sentinel

    def set(self, path_value: Union[str, List[str]], value: Any) -> None:
        """Set config value at path."""
        path = path_value.split(".") if isinstance(path_value, str) else path_value
        self._set_nested_value(self._config, path, value)

    def get_all(self) -> Dict[str, Any]:
        """Return deep copy of config."""
        return json.loads(json.dumps(self._config))

    def reload(self) -> Dict[str, Any]:
        """Reload configuration from disk."""
        self._config = self._load_config()
        return self._config

    def get_environment(self) -> str:
        return os.getenv("NODE_ENV", "development")

    def is_development(self) -> bool:
        return self.get_environment() == "development"

    def is_production(self) -> bool:
        return self.get_environment() == "production"

    def get_logging_config(self) -> Dict[str, Any]:
        return self.get("logging", {})

    def get_runtime_config(self) -> Dict[str, Any]:
        return self.get("runtime", {})

    def get_telegram_config(self) -> Dict[str, Any]:
        return self.get("telegram", {})

    def get_monitoring_config(self) -> Dict[str, Any]:
        return self.get("monitoring", {})

    def get_workers_config(self) -> Dict[str, Any]:
        return self.get("workers", {})

    def get_supervisor_config(self) -> Dict[str, Any]:
        return self.get("supervisor", {})

    def get_safety_config(self) -> Dict[str, Any]:
        return self.get("safety", {})

    def get_approval_config(self) -> Dict[str, Any]:
        return self.get("approval", {})


config = Config()
PROJECT_ROOT = config.project_root
