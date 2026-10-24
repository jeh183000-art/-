# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: python verify_batch.py BATCH [CHECKOUT COMMIT REMOTE_PREFIX]
"""Validate an explicit research inventory and optionally its published Git bytes."""
from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

REQUIRED: Final = frozenset({"strategy_code", "settings", "results_csv", "fills", "costs", "statistics_report", "environment"})
SECRET: Final = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?i:app[_-]?(?:key|secret)|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][A-Za-z0-9+/=_-]{16,}[\"'])")
BLOCKED: Final = frozenset({".pem", ".key", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db"})


@dataclass(frozen=True, slots=True)
class InventoryError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class Entry:
    path: str
    role: str
    size: int
    sha256: str


def read_inventory(batch: Path) -> tuple[Entry, ...]:
    with (batch / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["path", "role", "bytes", "sha256"]:
            raise InventoryError("INVALID_MANIFEST_COLUMNS")
        entries = tuple(Entry(r["path"], r["role"], int(r["bytes"]), r["sha256"]) for r in reader)
    names = {entry.path for entry in entries}
    if len(names) != len(entries) or "manifest.csv" in names:
        raise InventoryError("DUPLICATE_OR_SELF_REFERENCING_MANIFEST")
    if REQUIRED - {entry.role for entry in entries}:
        raise InventoryError("MISSING_REQUIRED_ARTIFACT_ROLE")
    actual = {file.relative_to(batch).as_posix() for file in batch.rglob("*") if file.is_file()}
    if actual != names | {"manifest.csv"}:
        raise InventoryError("UNMANIFESTED_OR_MISSING_FILES")
    for entry in entries:
        relative = PurePosixPath(entry.path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry.path or ":" in entry.path:
            raise InventoryError("UNSAFE_RELATIVE_PATH")
        if any(part.startswith(".env") or part in {".git", "__pycache__"} for part in relative.parts):
            raise InventoryError("BLOCKED_PATH")
        if relative.suffix.lower() in BLOCKED or relative.name.endswith(("-wal", "-shm")):
            raise InventoryError("BLOCKED_FILE_TYPE")
        file = batch / entry.path
        if any(parent.is_symlink() for parent in (file, *file.parents)):
            raise InventoryError("SYMLINK_NOT_ALLOWED")
        if entry.size > 45 * 1024 * 1024:
            raise InventoryError("LOSSLESS_ARCHIVE_OR_LFS_REQUIRED")
        data = file.read_bytes()
        if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
            raise InventoryError(f"LOCAL_HASH_OR_SIZE_MISMATCH: {entry.path}")
        if SECRET.search(data):
            raise InventoryError(f"POSSIBLE_CREDENTIAL_LITERAL: {entry.path}; contents withheld")
    return entries


def main() -> None:
    if len(sys.argv) not in {2, 5}:
        raise InventoryError("USAGE: verify_batch.py BATCH [CHECKOUT COMMIT REMOTE_PREFIX]")
    batch = Path(sys.argv[1]).resolve(strict=True)
    entries = read_inventory(batch)
    print(f"LOCAL_VERIFIED files={len(entries) + 1} roles={len(REQUIRED)}")
    if len(sys.argv) == 5:
        checkout, commit, prefix = sys.argv[2:]
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise InventoryError("FULL_COMMIT_SHA_REQUIRED")
        if prefix.startswith(("/", "-")) or ".." in PurePosixPath(prefix).parts:
            raise InventoryError("UNSAFE_REMOTE_PREFIX")
        for name in [entry.path for entry in entries] + ["manifest.csv"]:
            result = subprocess.run(["git", "-C", checkout, "show", f"{commit}:{prefix}/{name}", "--"], capture_output=True, check=True, timeout=60)
            if result.stdout != (batch / name).read_bytes():
                raise InventoryError(f"REMOTE_BYTES_MISMATCH: {name}")
        print(f"PUBLISHED_VERIFIED commit={commit} files={len(entries) + 1}")


if __name__ == "__main__":
    main()

