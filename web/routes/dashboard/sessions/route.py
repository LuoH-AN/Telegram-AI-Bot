"""Shared APIRouter instance for sessions routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

