"""Database connection management."""

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DATABASE_URL


def get_connection():
    """Get a database connection."""
    return psycopg2.connect(DATABASE_URL)


def get_dict_cursor(connection):
    """Get a cursor that returns dict-like rows."""
    return connection.cursor(cursor_factory=RealDictCursor)
