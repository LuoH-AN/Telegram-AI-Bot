"""Application constants."""

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096

# Streaming update interval fallback (seconds).
# Runtime value is environment-configurable in config/settings.py.
STREAM_UPDATE_INTERVAL = 0.35

# Database sync interval (seconds)
DB_SYNC_INTERVAL = 30

# Models per page for pagination
MODELS_PER_PAGE = 5

# --- AI streaming timeouts --------------------------------------------------
AI_STREAM_INIT_TIMEOUT = 25        # seconds waiting for stream object creation
AI_STREAM_NO_OUTPUT_TIMEOUT = 45   # seconds while stream has produced no visible activity
AI_STREAM_OUTPUT_IDLE_TIMEOUT = 120  # seconds idle timeout once output has started

# --- Tool dispatch -----------------------------------------------------------
MAX_TOOL_ROUNDS = 3                # max tool-call / AI-response loops per request
EXTRA_TOOL_CONTINUATION_ROUNDS = 2  # extra decision/continuation rounds after tool results are pending
TOOL_TIMEOUT = 30                  # default per-round timeout for tool execution (s)
MAX_TOOL_ERROR_SNIPPETS = 3        # max error snippets kept for empty-response fallback
TOOL_EXECUTOR_WORKERS = 4          # max parallel workers for tool calls
TOOL_CONTINUE_OR_FINISH_PROMPT = (
    "Decide the next step based on your task completion status. "
    "If the task is already complete, return the complete final answer to the user now. "
    "If the task is not complete yet, continue calling the necessary tools and keep working until you can finish. "
    "Do not stop mid-sentence."
)
TOOL_LIMIT_FALLBACK_PROMPT = (
    "You have reached the tool-call safety limit for this turn. "
    "If the task is complete, return the complete final answer now. "
    "If the task is still incomplete, clearly tell the user what has already been completed, what remains unfinished, "
    "and what blocked further tool execution."
)

# --- Auth / JWT --------------------------------------------------------------
JWT_SHORT_TOKEN_TTL_MINUTES = 10   # short-lived web login token TTL

# --- Cron --------------------------------------------------------------------
MAX_CRON_TASKS_PER_USER = 10       # per-user limit on scheduled tasks

# --- Reasoning ---------------------------------------------------------------
VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}

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
