"""The constraints in db/schema.sql actually reject what they claim to reject.

A constraint works only if the database refuses data that violates it. These
tests are the "Read, Predict, Verify" step from 9.2 Step 4 written down as
assertions, plus one test for each `ON DELETE` action recorded in
docs/design.md.

The exact wording of a `sqlite3.IntegrityError` differs between SQLite versions,
so these tests check which statement fails, never the message text.

SQLITE-SPECIFIC: this file is part of the 10.1 migration.

These tests import ``sqlite3``, catch ``sqlite3.IntegrityError``, and assert on
SQLite behavior such as ``PRAGMA foreign_keys`` and text timestamps. They change
when ``db/`` changes. A migration that edits only ``db/`` and ``app/`` leaves a
test suite that either fails for SQLite reasons or keeps testing behavior the
application no longer has.
"""

import sqlite3

import pytest

from conftest import ANA, ANA_ICS603, ANA_READING_GROUP, MARCUS


def test_foreign_key_enforcement_is_on(conn):
    """PRAGMA foreign_keys is off by default; connect() has to turn it on."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# The three violations from 9.2 Step 4
# ---------------------------------------------------------------------------


def test_child_row_with_no_parent_is_rejected(conn):
    """1. An INSERT into a child table whose foreign key matches no parent row."""
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO notes (notebook_id, title) VALUES (?, ?)",
                (9999, "A note in a notebook that does not exist"),
            )


def test_the_same_junction_pair_twice_is_rejected(conn):
    """2. The same (note, tag) pair inserted twice.

    This is the constraint behind "a student applies the same tag twice to one
    note". The seeded data already contains the pair, so the first insert here is
    the duplicate.
    """
    pair = conn.execute("SELECT note_id, tag_id FROM note_tags LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)", pair
            )


def test_missing_not_null_column_is_rejected(conn):
    """3. An INSERT that omits a NOT NULL column."""
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO notes (notebook_id) VALUES (?)", (ANA_ICS603,)
            )


# ---------------------------------------------------------------------------
# UNIQUE constraints
# ---------------------------------------------------------------------------


def test_one_student_cannot_have_two_notebooks_with_one_name(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO notebooks (student_id, name) VALUES (?, ?)",
                (ANA, "ICS 603 Building LLM Applications"),
            )


def test_two_students_may_use_the_same_notebook_name(conn):
    """UNIQUE (student_id, name), not UNIQUE (name). Both students already have
    a notebook with this name in the seeded data."""
    names = conn.execute(
        "SELECT COUNT(*) FROM notebooks WHERE name = ?",
        ("ICS 603 Building LLM Applications",),
    ).fetchone()[0]
    assert names == 2


def test_one_student_cannot_have_two_tags_with_one_name(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO tags (student_id, name) VALUES (?, ?)", (ANA, "exam")
            )


def test_two_students_may_use_the_same_tag_name(conn):
    """Tags are per student, so 'exam' is two different rows with two ids."""
    rows = conn.execute(
        "SELECT student_id, id FROM tags WHERE name = ? ORDER BY student_id",
        ("exam",),
    ).fetchall()
    assert [row[0] for row in rows] == [ANA, MARCUS]
    assert rows[0][1] != rows[1][1]


def test_a_student_cannot_have_two_settings_rows(conn):
    """UNIQUE on student_id is what makes the relationship one-to-one. Without
    it the schema would permit several settings rows per student."""
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO student_settings (student_id, theme) VALUES (?, ?)",
                (ANA, "light"),
            )


def test_two_accounts_cannot_share_an_email_address(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO students (name, email) VALUES (?, ?)",
                ("Someone Else", "ana.kealoha@hawaii.edu"),
            )


# ---------------------------------------------------------------------------
# CHECK constraints
# ---------------------------------------------------------------------------


def test_theme_is_limited_to_three_values(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "UPDATE student_settings SET theme = ? WHERE student_id = ?",
                ("neon", ANA),
            )


def test_compact_view_is_limited_to_zero_and_one(conn):
    """SQLite has no boolean storage class and its declared types are affinities,
    so without this CHECK the column would accept 7 or 'yes'."""
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "UPDATE student_settings SET compact_view = ? WHERE student_id = ?",
                (7, ANA),
            )


def test_a_python_bool_is_stored_as_zero_or_one(conn):
    """sqlite3 adapts True to 1 on the way in. That adaptation is why the column
    can be an INTEGER at all, and it is one of the things 10.1 changes: psycopg
    sends a Python bool as a PostgreSQL boolean, which an integer column rejects.
    """
    with conn:
        conn.execute(
            "UPDATE student_settings SET compact_view = ? WHERE student_id = ?",
            (True, ANA),
        )
    stored = conn.execute(
        "SELECT compact_view FROM student_settings WHERE student_id = ?", (ANA,)
    ).fetchone()[0]
    assert stored == 1
    assert isinstance(stored, int)


# ---------------------------------------------------------------------------
# ON DELETE actions (docs/design.md, D1, D5, D10, D11)
# ---------------------------------------------------------------------------


def test_deleting_a_notebook_that_holds_notes_is_rejected(conn):
    """D1: RESTRICT. The notes are the data; the notebook is a container."""
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("DELETE FROM notebooks WHERE id = ?", (ANA_ICS603,))


def test_deleting_an_empty_notebook_succeeds(conn):
    with conn:
        conn.execute("DELETE FROM notebooks WHERE id = ?", (ANA_READING_GROUP,))
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM notebooks WHERE id = ?", (ANA_READING_GROUP,)
        ).fetchone()[0]
        == 0
    )


def test_deleting_the_default_notebook_clears_the_setting(conn):
    """D5: SET NULL. The student returns to having no default, which the
    application already handles, rather than the delete being blocked."""
    with conn:
        conn.execute(
            "UPDATE student_settings SET default_notebook_id = ? WHERE student_id = ?",
            (ANA_READING_GROUP, ANA),
        )
        conn.execute("DELETE FROM notebooks WHERE id = ?", (ANA_READING_GROUP,))

    assert (
        conn.execute(
            "SELECT default_notebook_id FROM student_settings WHERE student_id = ?",
            (ANA,),
        ).fetchone()[0]
        is None
    )


def test_deleting_a_note_removes_its_tag_pairs(conn):
    """D10: CASCADE. A note_tags row has no meaning without its note."""
    note_id = conn.execute(
        "SELECT note_id FROM note_tags LIMIT 1"
    ).fetchone()[0]
    with conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM note_tags WHERE note_id = ?", (note_id,)
        ).fetchone()[0]
        == 0
    )


def test_deleting_a_tag_removes_its_labels_but_not_the_notes(conn):
    """D10: CASCADE on the other side. Deleting a tag un-labels notes; it does
    not delete them."""
    notes_before = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    tag_id = conn.execute(
        "SELECT id FROM tags WHERE student_id = ? AND name = ?", (ANA, "sql")
    ).fetchone()[0]

    with conn:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    assert (
        conn.execute(
            "SELECT COUNT(*) FROM note_tags WHERE tag_id = ?", (tag_id,)
        ).fetchone()[0]
        == 0
    )
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == notes_before


def test_deleting_a_student_who_has_notes_is_rejected(conn):
    """D11's stated consequence. Deleting a student cascades to their notebooks,
    and each of those is protected by the RESTRICT on notes.notebook_id, so the
    delete fails. Account deletion is not a version 1 feature; when it is added
    it will delete notes, then notebooks, then the student, in one transaction.
    """
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("DELETE FROM students WHERE id = ?", (ANA,))


def test_deleting_a_student_with_no_notes_removes_everything_they_own(conn):
    """D11: CASCADE, on a student the RESTRICT above does not block."""
    with conn:
        cur = conn.execute(
            "INSERT INTO students (name, email) VALUES (?, ?)",
            ("Kai Nakamura", "kai.nakamura@hawaii.edu"),
        )
        student_id = cur.lastrowid
        conn.execute(
            "INSERT INTO student_settings (student_id, theme) VALUES (?, ?)",
            (student_id, "light"),
        )
        conn.execute(
            "INSERT INTO notebooks (student_id, name) VALUES (?, ?)",
            (student_id, "ICS 605 Deep Learning"),
        )
        conn.execute(
            "INSERT INTO tags (student_id, name) VALUES (?, ?)", (student_id, "exam")
        )

    with conn:
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))

    for table in ("notebooks", "tags", "student_settings"):
        remaining = conn.execute(
            "SELECT COUNT(*) FROM " + table + " WHERE student_id = ?", (student_id,)
        ).fetchone()[0]
        assert remaining == 0, table


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


def test_the_two_declared_indexes_exist(conn):
    """PRAGMA index_list reports the indexes a UNIQUE or PRIMARY KEY constraint
    created as well as the ones CREATE INDEX made, so the check is by name."""
    note_indexes = {row[1] for row in conn.execute("PRAGMA index_list('notes')")}
    assert "idx_notes_notebook_id" in note_indexes

    pair_indexes = {row[1] for row in conn.execute("PRAGMA index_list('note_tags')")}
    assert "idx_note_tags_tag_id" in pair_indexes


def test_the_indexes_a_constraint_already_creates_are_not_repeated(conn):
    """9.2 checklist row 7 says to count the indexes a PRIMARY KEY or UNIQUE
    constraint creates. These four foreign-key columns are covered by one, so
    schema.sql deliberately does not create an index for them."""
    for table in ("notebooks", "tags", "student_settings", "note_tags"):
        created_by_hand = [
            row[1]
            for row in conn.execute("PRAGMA index_list('" + table + "')")
            if row[1].startswith("idx_")
        ]
        assert created_by_hand in ([], ["idx_note_tags_tag_id"]), table


def test_the_timestamp_format_is_the_one_the_schema_records(conn):
    """One format everywhere: ISO 8601, UTC, to the second, with a Z suffix.
    Text sorting is only date sorting while that stays true."""
    import re

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    values = [
        row[0]
        for row in conn.execute(
            """
            SELECT created_at FROM students
            UNION ALL SELECT created_at FROM notebooks
            UNION ALL SELECT created_at FROM notes
            UNION ALL SELECT updated_at FROM notes
            """
        )
    ]
    assert values
    assert all(pattern.match(value) for value in values)


def test_the_column_default_fills_a_timestamp_in_the_same_format(conn):
    """The strftime() default in schema.sql has to produce the same format the
    seeded rows use, or text sorting stops working."""
    import re

    with conn:
        cur = conn.execute(
            "INSERT INTO notes (notebook_id, title) VALUES (?, ?)",
            (ANA_ICS603, "Written without a timestamp"),
        )
    created_at, updated_at = conn.execute(
        "SELECT created_at, updated_at FROM notes WHERE id = ?", (cur.lastrowid,)
    ).fetchone()

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    assert pattern.match(created_at)
    assert pattern.match(updated_at)
    assert created_at == updated_at
