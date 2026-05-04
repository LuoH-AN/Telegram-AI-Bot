#!/usr/bin/env python3
"""Migrate old S3 state to new format with url_id.

Run this once after deploying the new S3 engine code.
Usage: python plugins/s3/migrate_url_id.py
"""

from __future__ import annotations

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plugins.s3.hf_backend import get_s3_backend
from plugins.s3.local_backend import LocalS3Backend


def migrate_state(backend) -> int:
    """Migrate state for all users in the backend."""
    total_objects = 0

    # For HF backend, we need to scan .s3/users/*/state.json
    # For Local backend, we scan runtime/s3_data/*/index.json

    if hasattr(backend, '_root'):
        # Local backend
        return migrate_local_backend(backend)
    else:
        # HF backend
        return migrate_hf_backend(backend)


def migrate_local_backend(backend: LocalS3Backend) -> int:
    """Migrate local backend state files."""
    import json
    total = 0

    if not backend._root.is_dir():
        print("No local S3 data found.")
        return 0

    for user_dir in backend._root.iterdir():
        if not user_dir.is_dir():
            continue
        try:
            user_id = int(user_dir.name)
        except ValueError:
            continue

        idx_file = user_dir / "index.json"
        if not idx_file.is_file():
            continue

        try:
            data = idx_file.read_bytes()
            # Try decrypt if cipher available
            if backend._cipher:
                from plugins.s3.local_backend import _decrypt_payload, _aad
                decrypted = _decrypt_payload(data, backend._cipher, _aad(user_id, "state"))
                if decrypted:
                    data = decrypted
            state = json.loads(data.decode("utf-8"))
        except Exception as e:
            print(f"Failed to read state for user {user_id}: {e}")
            continue

        changed = migrate_state_dict(state)
        if changed:
            total += changed
            # Save updated state
            try:
                new_data = json.dumps(state, separators=(",", ":")).encode("utf-8")
                if backend._cipher:
                    from plugins.s3.local_backend import _encrypt_payload, _aad
                    encrypted = _encrypt_payload(new_data, backend._cipher, _aad(user_id, "state"))
                    if encrypted:
                        new_data = encrypted
                idx_file.write_bytes(new_data)
                print(f"Migrated user {user_id}: {changed} objects")
            except Exception as e:
                print(f"Failed to save state for user {user_id}: {e}")

    return total


def migrate_hf_backend(backend) -> int:
    """Migrate HF backend state files."""
    # HF backend stores state via the store interface
    # We need to list all user state files and migrate them
    store = backend._store
    if not store or not store.enabled:
        print("HF store not enabled, skipping.")
        return 0

    import json
    total = 0

    # List all state files
    try:
        paths = store.list_paths(prefix=".s3/users/", limit=10000)
    except Exception as e:
        print(f"Failed to list HF paths: {e}")
        return 0

    for p in paths:
        path = p.get("path", "")
        if not path.endswith("/state.json"):
            continue

        # Extract user_id from path: .s3/users/{user_id}/state.json
        parts = path.split("/")
        if len(parts) < 4:
            continue
        try:
            user_id = int(parts[2])
        except ValueError:
            continue

        try:
            state = store.get_json(path, allow_plaintext=True)
            if not isinstance(state, dict):
                continue
        except Exception as e:
            print(f"Failed to read {path}: {e}")
            continue

        changed = migrate_state_dict(state)
        if changed:
            total += changed
            try:
                store.put_json(path, state, commit_message=f"migrate: add url_id for user {user_id}", encrypt=False)
                print(f"Migrated user {user_id}: {changed} objects")
            except Exception as e:
                print(f"Failed to save {path}: {e}")

    return total


def migrate_state_dict(state: dict) -> int:
    """Migrate a state dict in place. Returns number of objects migrated."""
    total = 0

    buckets = state.get("buckets", [])
    for bucket in buckets:
        next_id = bucket.get("next_url_id", 1)
        if not isinstance(next_id, int) or next_id < 1:
            next_id = 1

        objects = bucket.get("objects", {})
        for key, obj in objects.items():
            if "url_id" not in obj or not obj["url_id"]:
                obj["url_id"] = next_id
                next_id += 1
                total += 1

        bucket["next_url_id"] = next_id

    return total


def main():
    print("S3 State Migration: Adding url_id to objects")
    print("=" * 50)

    # Try HF backend first
    hf_backend = get_s3_backend()
    if hf_backend.enabled:
        print("\nMigrating HF backend...")
        total = migrate_hf_backend(hf_backend)
        print(f"HF migration complete: {total} objects")
    else:
        print("\nHF backend not enabled, skipping.")

    # Also check local backend
    from plugins.s3.local_backend import LocalS3Backend
    local_backend = LocalS3Backend()

    print("\nMigrating Local backend...")
    total = migrate_local_backend(local_backend)
    print(f"Local migration complete: {total} objects")

    print("\nMigration finished.")


if __name__ == "__main__":
    main()
