"""Constants for HF dataset storage backend."""

TRUTHY = {"1", "true", "yes", "on", "y"}
FALSY = {"0", "false", "no", "off", "n"}

ENC_MAGIC = b"HFENC1:"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"

LFS_PUSH_RETRIES = 3
LFS_PUSH_RETRY_BACKOFF_SECONDS = 2.0
LFS_CONCURRENT_TRANSFERS = 1
LFS_TRANSFER_MAX_RETRIES = 8
LFS_TRANSFER_MAX_RETRY_DELAY = 10
LFS_LOG_TAIL_LINES = 120
