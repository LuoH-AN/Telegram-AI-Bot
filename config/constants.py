"""Application constants."""

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096

# Streaming update interval (seconds)
STREAM_UPDATE_INTERVAL = 1.0

# Database sync interval (seconds)
DB_SYNC_INTERVAL = 30

# Models per page for pagination
MODELS_PER_PAGE = 5

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
