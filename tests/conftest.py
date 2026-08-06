"""Fixtures shared by the tests.

Each test gets a database of its own, built in a temporary directory from
db/schema.sql and db/seed.py. The tests therefore run against the same sample
rows a student sees after running the seed script, and a test that writes cannot
disturb the next one.

SQLITE-SPECIFIC: this file is part of the 10.1 migration.

These tests import ``sqlite3``, catch ``sqlite3.IntegrityError``, and assert on
SQLite behavior such as ``PRAGMA foreign_keys`` and text timestamps. They change
when ``db/`` changes. A migration that edits only ``db/`` and ``app/`` leaves a
test suite that either fails for SQLite reasons or keeps testing behavior the
application no longer has.
"""

import pytest

from db.seed import build

# ids the seeded data always assigns, because db/seed.py inserts in a fixed
# order into an empty database. Tests use these names rather than bare numbers.
ANA = 1
MARCUS = 2
NOELANI = 3

ANA_ICS603 = 1  # Ana's "ICS 603 Building LLM Applications" notebook (8 notes)
ANA_ICS635 = 2  # Ana's "ICS 635 Applied Machine Learning" notebook (3 notes)
ANA_READING_GROUP = 4  # Ana's empty notebook


@pytest.fixture
def conn(tmp_path):
    """A freshly seeded database, closed when the test ends."""
    connection = build(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient whose application reads a freshly seeded database."""
    from fastapi.testclient import TestClient

    from app.main import app, get_conn
    from db import queries

    db_path = tmp_path / "app.db"
    build(db_path).close()

    def get_test_conn():
        connection = queries.connect(db_path)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_conn] = get_test_conn
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
