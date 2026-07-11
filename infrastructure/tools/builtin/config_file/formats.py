"""Read/write operations for supported config file formats."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from pathlib import Path

from .path_ops import delete_path, get_path, set_path


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temp_name, path.stat().st_mode & 0o777)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


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
    lines = [f"{key}={value}" for key, value in sorted(data.items())]
    _atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def set_env_key(path: Path, key: str, value: object) -> None:
    lines = path.read_text("utf-8", errors="ignore").splitlines() if path.exists() else []
    replacement = f"{key}={'' if value is None else value}"
    output: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            current = stripped.split("=", 1)[0].strip()
            if current == key:
                if not replaced:
                    output.append(replacement)
                    replaced = True
                continue
        output.append(line)
    if not replaced:
        output.append(replacement)
    _atomic_write_text(path, "\n".join(output) + "\n")


def delete_env_key(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text("utf-8", errors="ignore").splitlines()
    output: list[str] = []
    deleted = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            current = stripped.split("=", 1)[0].strip()
            if current == key:
                deleted = True
                continue
        output.append(line)
    if deleted:
        _atomic_write_text(path, "\n".join(output) + ("\n" if output else ""))
    return deleted


def _read_json(path: Path):
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _write_json(path: Path, data) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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
    from io import StringIO

    buffer = StringIO()
    parser.write(buffer)
    _atomic_write_text(path, buffer.getvalue())


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
    _atomic_write_text(path, data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2))


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
