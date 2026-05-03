"""Read/write operations for supported config formats."""

from __future__ import annotations

import configparser
import json
from pathlib import Path

from .path_ops import delete_path, get_path, set_path


def _read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text("utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip("'\"")
    return data


def _write_env(path: Path, data: dict[str, object]) -> None:
    lines = [f"{key}={str(value)}" for key, value in sorted(data.items())]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _read_json(path: Path):
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_ini(path: Path) -> dict:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    data = {section: dict(parser.items(section)) for section in parser.sections()}
    if parser.defaults():
        data["DEFAULT"] = dict(parser.defaults())
    return data


def _write_ini(path: Path, data: dict) -> None:
    parser = configparser.ConfigParser()
    defaults = data.get("DEFAULT")
    if isinstance(defaults, dict):
        parser["DEFAULT"] = {key: str(value) for key, value in defaults.items()}
    for section, values in data.items():
        if section == "DEFAULT" or not isinstance(values, dict):
            continue
        parser[section] = {key: str(value) for key, value in values.items()}
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def load_data(path: Path, file_format: str):
    if file_format == "env":
        return _read_env(path)
    if file_format == "json":
        return _read_json(path)
    if file_format == "ini":
        return _read_ini(path)
    return path.read_text("utf-8", errors="ignore") if path.exists() else ""


def dump_data(path: Path, file_format: str, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if file_format == "env":
        return _write_env(path, data)
    if file_format == "json":
        return _write_json(path, data)
    if file_format == "ini":
        return _write_ini(path, data)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def render_value(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def get_value(data, file_format: str, key: str | None):
    if file_format == "text":
        if key:
            raise ValueError("text format does not support key lookups")
        return data
    return data if not key else get_path(data, key)


def set_value(data, file_format: str, key: str | None, value):
    if file_format == "text":
        if key:
            raise ValueError("text format does not support key writes")
        return str(value)
    if file_format == "env":
        if not key:
            if not isinstance(value, dict):
                raise ValueError("env format requires a key or a full object value")
            return {str(k): str(v) for k, v in value.items()}
        data[str(key)] = "" if value is None else str(value)
        return data
    if file_format == "ini":
        if not key:
            if not isinstance(value, dict):
                raise ValueError("ini format requires a key or a full object value")
            return value
        set_path(data, key, "" if value is None else str(value))
        return data
    if not key:
        return value
    set_path(data, key, value)
    return data


def delete_value(data, file_format: str, key: str | None):
    if file_format == "text":
        if key:
            raise ValueError("text format does not support key deletes")
        return True
    if not key:
        return True
    return delete_path(data, key)
