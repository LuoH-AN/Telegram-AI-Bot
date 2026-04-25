"""File type detection utilities."""

from config import TEXT_EXTENSIONS, IMAGE_EXTENSIONS


def get_file_extension(file_name: str) -> str:
    """Extract file extension from filename."""
    if "." in file_name:
        return "." + file_name.rsplit(".", 1)[-1].lower()
    return ""


def is_text_file(file_name: str) -> bool:
    """Check if file is a supported text file."""
    return get_file_extension(file_name) in TEXT_EXTENSIONS


def is_image_file(file_name: str) -> bool:
    """Check if file is a supported image file."""
    return get_file_extension(file_name) in IMAGE_EXTENSIONS


def is_likely_text(data: bytearray) -> bool:
    """Check if data is likely text content by analyzing bytes."""
    try:
        # Try to decode as UTF-8
        sample = bytes(data[:8192]).decode("utf-8")
        # Check if it contains mostly printable characters
        printable_ratio = sum(c.isprintable() or c in "\n\r\t" for c in sample) / len(sample)
        return printable_ratio > 0.9
    except (UnicodeDecodeError, ZeroDivisionError):
        return False


def decode_file_content(file_bytes: bytearray) -> str | None:
    """Try to decode file content as text."""
    try:
        return bytes(file_bytes).decode("utf-8")
    except UnicodeDecodeError:
        try:
            return bytes(file_bytes).decode("latin-1")
        except UnicodeDecodeError:
            return None
