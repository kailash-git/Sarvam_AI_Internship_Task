"""Test fixtures: every test runs against a fresh, isolated SQLite file."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

from app.db.migrate import migrate
from app.db.models import set_db_path


@pytest.fixture(autouse=True)
def isolated_db():
    path = Path(tempfile.gettempdir()) / f"kivi_test_{uuid.uuid4().hex}.db"
    set_db_path(str(path))
    migrate()
    yield
    set_db_path(None)
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.unlink(str(path) + suffix)
        except OSError:
            pass
