"""Shell tool - execute commands in the container."""

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time

from hf_dataset_store import get_hf_dataset_store

from .registry import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120
_MAX_OUTPUT = 10000
_HEAD_TAIL = 4000
_DEFAULT_WORK_ROOT = (os.getenv("SHELL_WORK_ROOT") or "/tmp/shell").strip() or "/tmp/shell"

_HF_SNAPSHOT_MAX_BYTES = int(os.getenv("SHELL_HF_SNAPSHOT_MAX_BYTES", "0"))
_HF_SNAPSHOT_MAX_FILE_BYTES = int(os.getenv("SHELL_HF_SNAPSHOT_MAX_FILE_BYTES", "0"))
_HF_SYNC_INTERVAL_SECONDS = max(
    1,
    int(os.getenv("SHELL_HF_SYNC_INTERVAL_SECONDS", "8")),
)
_HF_MAX_FILES = int(os.getenv("SHELL_HF_MAX_FILES", "0"))
_HF_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
}
_HF_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".swp",
}
_HF_STATE_LOCK = threading.Lock()
_HF_RESTORED_USERS: set[int] = set()
_HF_LAST_SYNC_AT: dict[int, float] = {}

_PKG_SINGLE_TIMEOUT = 120
_PKG_RESTORED_USERS: set[int] = set()

_INSTALL_PATTERNS: dict[str, re.Pattern] = {
    "pip": re.compile(
        r"(?:pip3?|python3?\s+-m\s+pip)\s+(?:install|uninstall)\b",
        re.IGNORECASE,
    ),
    "npm": re.compile(
        r"npm\s+(?:install|i|uninstall|remove)\s+(?:.*\s)?(?:-g|--global)\b"
        r"|npm\s+(?:install|i|uninstall|remove)\s+(?:-g|--global)\b",
        re.IGNORECASE,
    ),
    "apt": re.compile(
        r"(?:apt|apt-get)\s+(?:install|remove|purge)\b",
        re.IGNORECASE,
    ),
}
_APT_PKG_EXTRACT = re.compile(
    r"(?:apt|apt-get)\s+(?:install|remove|purge)\s+(.*)",
    re.IGNORECASE,
)

# Patterns that should be blocked
_BLOCKED_PATTERNS = [
    r"\brm\s+-[^\s]*r[^\s]*f\s+/",  # rm -rf /
    r"\brm\s+-[^\s]*f[^\s]*r\s+/",  # rm -fr /
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bhalt\b",
    r"\binit\s+[06]\b",
    r"\bmkfs\b",
    r"\bdd\b.*\bof=/dev/",  # dd writing to devices
    r"\bsudo\b",
    r"\bsu\s",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;",  # fork bomb :(){ :|:& };:
    r"\biptables\b",
    r"\bnft\b",
    r"\bcrontab\b",
    r"\bchmod\s+[0-7]*s",  # setuid
    r"\bchown\s+-R\s+.*\s+/",  # recursive chown on /
    r"\bmount\b",
    r"\bumount\b",
    r"\bsystemctl\b",
    r"\bservice\b",
    r"\bnsenter\b",
    r"\bunshare\b",
    r">\s*/dev/[sh]d",  # redirect to block devices
    r"\bkill\s+-9\s+1\b",  # kill init
    r"\bpkill\b.*-9",
    r"\bkillall\b",
]
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

# Environment variable keywords to scrub
_SENSITIVE_KEYWORDS = [
    "TOKEN",
    "SECRET",
    "KEY",
    "PASSWORD",
    "PASSWD",
    "DATABASE_URL",
    "CREDENTIAL",
    "AUTH",
]


def _is_blocked(command: str) -> str | None:
    """Return a reason string if the command is blocked, else None."""
    for pattern in _BLOCKED_RE:
        if pattern.search(command):
            return f"Command blocked by security policy (matched: {pattern.pattern})"
    return None


def _clean_env() -> dict[str, str]:
    """Return a copy of os.environ with sensitive variables removed."""
    env = {}
    for k, v in os.environ.items():
        upper = k.upper()
        if any(kw in upper for kw in _SENSITIVE_KEYWORDS):
            continue
        env[k] = v
    return env


def _truncate_output(text: str) -> str:
    """Truncate output to _MAX_OUTPUT chars, keeping head and tail."""
    if len(text) <= _MAX_OUTPUT:
        return text
    head = text[:_HEAD_TAIL]
    tail = text[-_HEAD_TAIL:]
    skipped = len(text) - _HEAD_TAIL * 2
    return f"{head}\n\n... [{skipped} characters truncated] ...\n\n{tail}"


def _workspace_has_content(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _safe_extract_tar_gz(data: bytes, target_dir: str) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            root = os.path.abspath(target_dir)
            safe_members = []
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    continue
                destination = os.path.abspath(os.path.join(root, member.name))
                if destination == root or destination.startswith(root + os.sep):
                    safe_members.append(member)
            archive.extractall(path=target_dir, members=safe_members)
        return True
    except Exception as e:
        logger.warning("Failed to restore shell workspace archive: %s", e)
        return False


def _build_workspace_snapshot(cwd: str) -> tuple[bytes | None, dict]:
    files: list[tuple[str, str, int]] = []
    total_input_bytes = 0

    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if d not in _HF_SKIP_DIRS]
        rel_dir = os.path.relpath(dirpath, cwd)
        rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")

        for filename in filenames:
            if _HF_MAX_FILES > 0 and len(files) >= _HF_MAX_FILES:
                break
            if any(filename.endswith(suffix) for suffix in _HF_SKIP_SUFFIXES):
                continue
            abs_path = os.path.join(dirpath, filename)
            if not os.path.isfile(abs_path):
                continue
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                continue
            if _HF_SNAPSHOT_MAX_FILE_BYTES > 0 and size > _HF_SNAPSHOT_MAX_FILE_BYTES:
                continue

            rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
            rel_path = rel_path.replace("\\", "/")
            files.append((abs_path, rel_path, size))
            total_input_bytes += size

        if _HF_MAX_FILES > 0 and len(files) >= _HF_MAX_FILES:
            break

    metadata = {
        "files": len(files),
        "total_input_bytes": total_input_bytes,
    }
    if not files:
        return None, metadata

    try:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for abs_path, rel_path, _size in files:
                archive.add(abs_path, arcname=rel_path, recursive=False)
        archive_bytes = buffer.getvalue()
    except Exception as e:
        logger.warning("Failed to build shell workspace archive: %s", e)
        return None, metadata

    metadata["archive_bytes"] = len(archive_bytes)
    if _HF_SNAPSHOT_MAX_BYTES > 0 and len(archive_bytes) > _HF_SNAPSHOT_MAX_BYTES:
        logger.warning(
            "Skip shell workspace snapshot: archive too large (%d > %d bytes).",
            len(archive_bytes),
            _HF_SNAPSHOT_MAX_BYTES,
        )
        return None, metadata

    return archive_bytes, metadata


def _restore_workspace_from_hf(user_id: int, cwd: str) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    with _HF_STATE_LOCK:
        if user_id in _HF_RESTORED_USERS:
            return
        _HF_RESTORED_USERS.add(user_id)

    if _workspace_has_content(cwd):
        return

    archive_path = f"shell/{user_id}/workspace.tar.gz"
    archive = store.get_bytes(archive_path)
    if not archive:
        return

    if _safe_extract_tar_gz(archive, cwd):
        logger.info("[user=%d] restored shell workspace from HF dataset", user_id)


def _snapshot_workspace_to_hf(user_id: int, cwd: str, command: str) -> None:
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    now = time.time()
    with _HF_STATE_LOCK:
        last = _HF_LAST_SYNC_AT.get(user_id, 0.0)
        if now - last < _HF_SYNC_INTERVAL_SECONDS:
            return
        _HF_LAST_SYNC_AT[user_id] = now

    archive, snapshot_meta = _build_workspace_snapshot(cwd)
    if not archive:
        return

    archive_path = f"shell/{user_id}/workspace.tar.gz"
    meta_path = f"shell/{user_id}/workspace_meta.json"
    ok = store.put_bytes(
        archive_path,
        archive,
        commit_message=f"shell workspace snapshot user={user_id}",
    )
    if not ok:
        return

    store.put_json(
        meta_path,
        {
            "user_id": user_id,
            "cwd": cwd,
            "updated_at": int(now),
            "archive_bytes": len(archive),
            "last_command": command[:200],
            **snapshot_meta,
        },
        commit_message=f"shell workspace metadata user={user_id}",
    )


# ── Package manifest backup / restore ──────────────────────────────


def _detect_pkg_managers(command: str) -> list[str]:
    """Return list of package manager names that the command invokes."""
    return [name for name, pat in _INSTALL_PATTERNS.items() if pat.search(command)]


def _extract_apt_packages(command: str) -> list[str]:
    """Parse package names from an apt install/remove/purge command."""
    m = _APT_PKG_EXTRACT.search(command)
    if not m:
        return []
    args = m.group(1)
    packages = []
    for token in args.split():
        if token.startswith("-"):
            continue
        # skip version specifiers like package=1.2.3
        name = token.split("=")[0]
        if name and name[0].isalpha():
            packages.append(name)
    return packages


def _capture_pip_manifest() -> list[str]:
    """Run ``pip freeze --local`` and return the list of installed packages."""
    try:
        proc = subprocess.run(
            ["pip", "freeze", "--local"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except Exception as e:
        logger.warning("Failed to capture pip manifest: %s", e)
        return []


def _capture_npm_manifest() -> list[str]:
    """Run ``npm list -g --depth=0`` and return global packages."""
    if not shutil.which("npm"):
        return []
    try:
        proc = subprocess.run(
            ["npm", "list", "-g", "--depth=0", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0 and not proc.stdout:
            return []
        data = json.loads(proc.stdout)
        deps = data.get("dependencies", {})
        packages = []
        for pkg, info in deps.items():
            if pkg == "npm":
                continue
            version = info.get("version", "")
            packages.append(f"{pkg}@{version}" if version else pkg)
        return packages
    except Exception as e:
        logger.warning("Failed to capture npm manifest: %s", e)
        return []


def _get_existing_manifest(user_id: int) -> dict:
    """Load the existing package manifest from HF, or return an empty skeleton."""
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"version": 1, "updated_at": 0, "pip": [], "npm": [], "apt": []}
    path = f"shell/{user_id}/packages_manifest.json"
    data = store.get_json(path)
    if isinstance(data, dict) and data.get("version"):
        return data
    return {"version": 1, "updated_at": 0, "pip": [], "npm": [], "apt": []}


def _snapshot_packages_to_hf(user_id: int, command: str, exit_code: int) -> None:
    """After a successful install/uninstall, capture manifests and upload."""
    if exit_code != 0:
        return

    managers = _detect_pkg_managers(command)
    if not managers:
        return

    store = get_hf_dataset_store()
    if not store.enabled:
        return

    manifest = _get_existing_manifest(user_id)

    # Determine if this is an apt remove/purge
    is_apt_remove = bool(
        re.search(r"(?:apt|apt-get)\s+(?:remove|purge)\b", command, re.IGNORECASE)
    )

    for mgr in managers:
        if mgr == "pip":
            manifest["pip"] = _capture_pip_manifest()
        elif mgr == "npm":
            manifest["npm"] = _capture_npm_manifest()
        elif mgr == "apt":
            if is_apt_remove:
                removed = _extract_apt_packages(command)
                manifest["apt"] = [
                    p for p in manifest.get("apt", []) if p not in removed
                ]
            else:
                new_pkgs = _extract_apt_packages(command)
                existing = set(manifest.get("apt", []))
                for pkg in new_pkgs:
                    existing.add(pkg)
                manifest["apt"] = sorted(existing)

    manifest["updated_at"] = int(time.time())
    path = f"shell/{user_id}/packages_manifest.json"
    store.put_json(
        path,
        manifest,
        commit_message=f"shell package manifest user={user_id}",
    )
    logger.info(
        "[user=%d] saved package manifest (pip=%d, npm=%d, apt=%d)",
        user_id,
        len(manifest.get("pip", [])),
        len(manifest.get("npm", [])),
        len(manifest.get("apt", [])),
    )


def _restore_apt(user_id: int, packages: list[str]) -> None:
    """Reinstall apt packages."""
    if not packages:
        return
    try:
        subprocess.run(
            ["apt-get", "update"],
            capture_output=True,
            timeout=_PKG_SINGLE_TIMEOUT,
        )
        subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends", *packages],
            capture_output=True,
            timeout=_PKG_SINGLE_TIMEOUT,
        )
        logger.info("[user=%d] restored %d apt packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] apt restore failed: %s", user_id, e)


def _restore_pip(user_id: int, packages: list[str]) -> None:
    """Reinstall pip packages."""
    if not packages:
        return
    try:
        subprocess.run(
            ["pip", "install", "--quiet", *packages],
            capture_output=True,
            timeout=_PKG_SINGLE_TIMEOUT,
        )
        logger.info("[user=%d] restored %d pip packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] pip restore failed: %s", user_id, e)


def _restore_npm(user_id: int, packages: list[str]) -> None:
    """Reinstall global npm packages."""
    if not packages or not shutil.which("npm"):
        return
    try:
        subprocess.run(
            ["npm", "install", "-g", "--silent", *packages],
            capture_output=True,
            timeout=_PKG_SINGLE_TIMEOUT,
        )
        logger.info("[user=%d] restored %d npm packages", user_id, len(packages))
    except Exception as e:
        logger.warning("[user=%d] npm restore failed: %s", user_id, e)


def _restore_packages_from_hf(user_id: int) -> None:
    """Load the package manifest from HF and reinstall everything."""
    store = get_hf_dataset_store()
    if not store.enabled:
        return

    with _HF_STATE_LOCK:
        if user_id in _PKG_RESTORED_USERS:
            return
        _PKG_RESTORED_USERS.add(user_id)

    manifest = _get_existing_manifest(user_id)
    apt_pkgs = manifest.get("apt", [])
    pip_pkgs = manifest.get("pip", [])
    npm_pkgs = manifest.get("npm", [])

    if not apt_pkgs and not pip_pkgs and not npm_pkgs:
        return

    logger.info(
        "[user=%d] restoring packages (apt=%d, pip=%d, npm=%d)",
        user_id,
        len(apt_pkgs),
        len(pip_pkgs),
        len(npm_pkgs),
    )

    # Restore order: apt → pip → npm
    _restore_apt(user_id, apt_pkgs)
    _restore_pip(user_id, pip_pkgs)
    _restore_npm(user_id, npm_pkgs)


class ShellTool(BaseTool):
    """Execute shell commands in the container."""

    @property
    def name(self) -> str:
        return "shell"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "shell_exec",
                    "description": (
                        "Execute a shell command in the container and return the output. "
                        "Supports pipes, redirects, and chained commands. "
                        "Use for file operations, running scripts, system info, etc."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute",
                            },
                            "timeout": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": _MAX_TIMEOUT,
                                "default": _DEFAULT_TIMEOUT,
                                "description": f"Timeout in seconds (1-{_MAX_TIMEOUT}, default {_DEFAULT_TIMEOUT})",
                            },
                            "working_directory": {
                                "type": "string",
                                "description": "Working directory for the command (default: per-user temp dir)",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "shell_exec":
            return f"Unknown tool: {tool_name}"

        command = (arguments.get("command") or "").strip()
        if not command:
            return "Error: No command provided."

        # Security check
        reason = _is_blocked(command)
        if reason:
            logger.warning("[user=%d] shell command blocked: %s", user_id, command[:200])
            return f"Error: {reason}"

        # Timeout
        timeout = _DEFAULT_TIMEOUT
        if arguments.get("timeout") is not None:
            try:
                timeout = max(1, min(_MAX_TIMEOUT, int(arguments["timeout"])))
            except (TypeError, ValueError):
                pass

        # Working directory
        default_cwd = f"{_DEFAULT_WORK_ROOT}/{user_id}"
        cwd = (arguments.get("working_directory") or "").strip() or default_cwd
        os.makedirs(cwd, exist_ok=True)
        _restore_workspace_from_hf(user_id, cwd)
        _restore_packages_from_hf(user_id)

        # Execute
        logger.info("[user=%d] shell_exec: %s (timeout=%ds, cwd=%s)", user_id, command[:200], timeout, cwd)
        result = None
        timeout_error = False
        runtime_error: Exception | None = None
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=_clean_env(),
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            timeout_error = True
            logger.warning("[user=%d] shell command timed out after %ds: %s", user_id, timeout, command[:200])
        except Exception as e:
            runtime_error = e
            logger.exception("[user=%d] shell exec error", user_id)
        finally:
            _snapshot_workspace_to_hf(user_id, cwd, command)
            if result is not None:
                _snapshot_packages_to_hf(user_id, command, result.returncode)

        if timeout_error:
            return f"Error: Command timed out after {timeout} seconds."
        if runtime_error is not None:
            return "Error. Please retry."
        if result is None:
            return "Error: command execution returned no result."

        # Build output
        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")

        output = "\n".join(parts) if parts else "(no output)"
        return _truncate_output(output)

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the shell_exec tool to execute shell commands in the container.\n"
            "Use it when the user asks you to run commands, write/run scripts, check system info, "
            "process files, or perform tasks that require a terminal.\n"
            "You can use pipes, redirects, and chain multiple commands.\n"
            f"Each user has their own working directory at {_DEFAULT_WORK_ROOT}/<user_id>/.\n"
            "When HF_DATASET_USERNAME/HF_DATASET_TOKEN/HF_DATASET_NAME are configured, "
            "workspace snapshots are synced to a Hugging Face dataset.\n"
        )
