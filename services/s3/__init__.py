"""S3-compatible object storage service."""

from .engine import S3Service, S3Backend, S3Bucket, S3Object
from .hf_backend import HFS3Backend, get_s3_backend
from .local_backend import LocalS3Backend

__all__ = [
    "S3Service",
    "S3Backend",
    "S3Bucket",
    "S3Object",
    "HFS3Backend",
    "get_s3_backend",
    "LocalS3Backend",
]
