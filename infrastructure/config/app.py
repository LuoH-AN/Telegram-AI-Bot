"""Application constants."""

import os

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096

# Streaming update interval fallback (seconds).
# Runtime value is environment-configurable in infrastructure.config/env.py.
STREAM_UPDATE_INTERVAL = 0.35

# Database sync interval (seconds)
DB_SYNC_INTERVAL = 30

# Soft cap on messages held per session in memory. Old, already-persisted
# messages past this cap are dropped from the in-memory cache (they remain in
# the DB and are reloaded on next read). 0 disables eviction.
CONVERSATION_CACHE_CAP = int(os.getenv("CONVERSATION_CACHE_CAP", "0"))

# Models per page for pagination
MODELS_PER_PAGE = 5

# --- AI streaming timeouts --------------------------------------------------
AI_STREAM_INIT_TIMEOUT = 25        # seconds waiting for stream object creation
AI_STREAM_NO_OUTPUT_TIMEOUT = 45   # seconds while stream has produced no visible activity
AI_STREAM_OUTPUT_IDLE_TIMEOUT = 120  # seconds idle timeout once output has started

# --- Tool dispatch -----------------------------------------------------------
TOOL_TIMEOUT = 30                  # default per-round timeout for tool execution (s)
MAX_TOOL_ROUNDS = max(1, int(os.getenv("MAX_TOOL_ROUNDS", "6")))
TOOL_CONTINUE_OR_FINISH_PROMPT = (
    "First decide internally whether the task is fully complete. "
    "If it is already complete, immediately return the complete final answer to the user. "
    "If it is not complete yet, immediately call the next necessary tools and continue working. "
    "Do not tell the user that you are still working, that the task is incomplete, or that you will continue later. "
    "If more work is needed, just continue with the tool calls."
)

# --- Cron --------------------------------------------------------------------
MAX_CRON_TASKS_PER_USER = 10       # per-user limit on scheduled tasks

# --- Reasoning ---------------------------------------------------------------
VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def normalize_reasoning_effort(value: str | None) -> str:
    """Return the canonical lowercase effort name, or '' if invalid. Single source of truth."""
    current = (value or "").strip().lower()
    return current if current in VALID_REASONING_EFFORTS else ""

# Supported file extensions for text-based processing
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".html", ".css", ".scss", ".sass", ".less", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".bat", ".cmd", ".sql", ".r", ".m", ".pl", ".lua", ".vim", ".el", ".clj",
    ".hs", ".ml", ".ex", ".exs", ".erl", ".fs", ".v", ".sv", ".vhd", ".asm",
    ".s", ".makefile", ".cmake", ".dockerfile", ".gitignore", ".env", ".log",
    ".csv", ".tsv", ".rst", ".tex", ".bib", ".org", ".adoc", ".diff", ".patch",
}

# Supported image extensions (when sent as document)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# MIME type mapping for images
MIME_TYPE_MAP = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "gif": "gif",
    "webp": "webp",
    "bmp": "bmp",
}

# Maximum file size for uploads (20MB)
MAX_FILE_SIZE = 20 * 1024 * 1024

# Maximum characters for text file content
MAX_TEXT_CONTENT_LENGTH = 100000

# Prompt template for generating session titles
TITLE_GENERATION_PROMPT = """Generate a concise 3-5 word title summarizing the conversation below.
- Use the same language as the conversation content.
- Do not use quotes or special formatting.
- Output only the title text and nothing else.

User: {user_message}
Assistant: {ai_response}"""
