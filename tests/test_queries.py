"""One test per function in db/queries.py, against the seeded database.

9.2 Step 6 asks for Read, Predict, Verify on every query: write down the exact
rows you expect, including how many, then run the function and compare. These
tests are those predictions written as assertions, so they are checked again on
every run instead of once by eye.
"""

import sqlite3

import pytest

from conftest import ANA, ANA_ICS603, ANA_READING_GROUP, MARCUS, NOELANI
from db import queries

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_get_student(conn):
    assert queries.get_student(conn, ANA) == (
        ANA,
        "Ana Kealoha",
        "ana.kealoha@hawaii.edu",
        "2026-08-24T18:02:11Z",
    )


def test_get_student_returns_none_for_an_unknown_id(conn):
    assert queries.get_student(conn, 9999) is None


def test_get_student_settings_names_the_default_notebook(conn):
    assert queries.get_student_settings(conn, ANA) == (
        "dark",
        ANA_ICS603,
        "ICS 603 Building LLM Applications",
        1,
    )


def test_get_student_settings_when_no_default_notebook_is_chosen(conn):
    """The LEFT JOIN is what keeps this row. An INNER JOIN would return nothing
    for a student whose default_notebook_id is NULL."""
    assert queries.get_student_settings(conn, NOELANI) == ("system", None, None, 0)


def test_get_notebook(conn):
    assert queries.get_notebook(conn, ANA_ICS603) == (
        ANA_ICS603,
        ANA,
        "ICS 603 Building LLM Applications",
        "2026-08-24T18:04:50Z",
    )
    assert queries.get_notebook(conn, 9999) is None


def test_list_notebooks_counts_notes_and_keeps_the_empty_notebook(conn):
    """Four notebooks, ordered by name, and "Reading group" reports 0 rather
    than being dropped. COUNT(*) would report 1 for it."""
    assert queries.list_notebooks(conn, ANA) == [
        (3, "ICS 601 Applied Industry Seminar", 2),
        (ANA_ICS603, "ICS 603 Building LLM Applications", 8),
        (2, "ICS 635 Applied Machine Learning", 3),
        (ANA_READING_GROUP, "Reading group", 0),
    ]


def test_get_note(conn):
    note = queries.get_note(conn, 1)
    assert note[0] == 1
    assert note[1] == ANA_ICS603
    assert note[2] == "Parameterized queries are the only safe way to pass user text"
    assert note[3].startswith("Never build SQL with an f-string.")
    assert note[4] == note[5] == "2026-10-20T19:12:44Z"


def test_get_note_returns_a_null_body_as_none(conn):
    """Note 8 is a title typed during class with the body still to come."""
    note = queries.get_note(conn, 8)
    assert note[2] == "Week 12 lecture — write this up"
    assert note[3] is None


def test_get_note_returns_none_for_an_unknown_id(conn):
    assert queries.get_note(conn, 9999) is None


def test_notes_with_notebook_name_joins_through_the_notebook(conn):
    """Thirteen notes, most recently changed first. This is the only way to
    answer the question: notes has no student_id column."""
    rows = queries.notes_with_notebook_name(conn, ANA)
    assert len(rows) == 13
    assert rows[0] == (
        8,
        "Week 12 lecture — write this up",
        "ICS 603 Building LLM Applications",
        "2026-11-17T19:04:58Z",
    )
    assert rows[-1][1] == "response_model does two things"

    updated = [row[3] for row in rows]
    assert updated == sorted(updated, reverse=True)

    # Every row names one of Ana's four notebooks and none of anyone else's.
    assert {row[2] for row in rows} == {
        "ICS 601 Applied Industry Seminar",
        "ICS 603 Building LLM Applications",
        "ICS 635 Applied Machine Learning",
    }


def test_notes_with_tag(conn):
    """Three notes carry Ana's 'sql' tag, ordered by title."""
    assert queries.notes_with_tag(conn, ANA, "sql") == [
        (3, "A junction table is what a many-to-many needs", "ICS 603 Building LLM Applications"),
        (2, "PRAGMA foreign_keys is per connection", "ICS 603 Building LLM Applications"),
        (1, "Parameterized queries are the only safe way to pass user text", "ICS 603 Building LLM Applications"),
    ]


def test_notes_with_tag_returns_nothing_for_a_tag_no_note_uses(conn):
    """The spec lists this as something that happens. It is an empty result, not
    an error."""
    assert queries.notes_with_tag(conn, ANA, "review") == []


def test_notes_with_tag_returns_nothing_for_a_tag_that_does_not_exist(conn):
    assert queries.notes_with_tag(conn, ANA, "thermodynamics") == []


def test_notes_with_tag_does_not_cross_between_students(conn):
    """Ana and Marcus each have a tag named 'docker'. Each query returns only
    that student's notes."""
    ana = queries.notes_with_tag(conn, ANA, "docker")
    marcus = queries.notes_with_tag(conn, MARCUS, "docker")

    assert [row[1] for row in ana] == [
        "Copy the dependency files before the code",
        "EXPOSE does not publish the port",
    ]
    assert [row[1] for row in marcus] == [
        "A volume is not the writable layer",
        "The app reaches the database at db, not localhost",
    ]


def test_note_count_per_tag(conn):
    """Seven tags with counts that differ, largest first, and 'review' at 0
    because the LEFT JOIN keeps it."""
    assert queries.note_count_per_tag(conn, ANA) == [
        (2, "exam", 8),
        (4, "reading", 4),
        (6, "sql", 3),
        (7, "todo", 3),
        (1, "docker", 2),
        (3, "lab", 1),
        (5, "review", 0),
    ]


def test_note_count_per_tag_counts_only_this_students_notes(conn):
    assert queries.note_count_per_tag(conn, MARCUS) == [
        (8, "docker", 2),
        (9, "exam", 2),
    ]


def test_tags_used_at_least(conn):
    """HAVING filters whole groups after the counts are computed."""
    assert queries.tags_used_at_least(conn, ANA, 3) == [
        ("exam", 8),
        ("reading", 4),
        ("sql", 3),
        ("todo", 3),
    ]


def test_tags_used_at_least_zero_keeps_the_unused_tag(conn):
    assert len(queries.tags_used_at_least(conn, ANA, 0)) == 7
    assert queries.tags_used_at_least(conn, ANA, 0)[-1] == ("review", 0)


def test_tags_used_at_least_a_number_nothing_reaches(conn):
    assert queries.tags_used_at_least(conn, ANA, 20) == []


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_create_student_creates_the_settings_row_too(conn):
    student_id = queries.create_student(
        conn, "Kai Nakamura", "kai.nakamura@hawaii.edu", "light", True
    )
    assert queries.get_student(conn, student_id)[1] == "Kai Nakamura"
    assert queries.get_student_settings(conn, student_id) == ("light", None, None, 1)


def test_create_student_rolls_both_inserts_back_on_failure(conn):
    """Both tables change or neither does. A theme the CHECK constraint rejects
    fails the second insert, and the student row has to go with it."""
    before = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_student(
            conn, "Kai Nakamura", "kai.nakamura@hawaii.edu", "neon", False
        )
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == before


def test_create_student_rejects_a_repeated_email(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_student(conn, "Someone Else", "ana.kealoha@hawaii.edu")


def test_create_notebook(conn):
    notebook_id = queries.create_notebook(conn, ANA, "ICS 605 Deep Learning")
    assert queries.get_notebook(conn, notebook_id)[2] == "ICS 605 Deep Learning"
    assert len(queries.list_notebooks(conn, ANA)) == 5


def test_create_notebook_rejects_a_repeated_name_for_one_student(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_notebook(conn, ANA, "ICS 603 Building LLM Applications")


def test_delete_notebook_removes_an_empty_one(conn):
    assert queries.delete_notebook(conn, ANA_READING_GROUP) == 1
    assert len(queries.list_notebooks(conn, ANA)) == 3


def test_delete_notebook_reports_zero_for_an_unknown_id(conn):
    assert queries.delete_notebook(conn, 9999) == 0


def test_delete_notebook_refuses_while_it_holds_notes(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.delete_notebook(conn, ANA_ICS603)
    assert queries.get_notebook(conn, ANA_ICS603) is not None


def test_add_note_fills_both_timestamps_from_the_column_default(conn):
    note_id = queries.add_note(conn, ANA_ICS603, "Read chapter 4", None)
    note = queries.get_note(conn, note_id)
    assert note[2] == "Read chapter 4"
    assert note[3] is None
    assert note[4] == note[5]
    assert note[4].endswith("Z") and len(note[4]) == 20


def test_add_note_rejects_a_notebook_that_does_not_exist(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.add_note(conn, 9999, "Nowhere", None)


def test_update_note_body_moves_updated_at_and_leaves_created_at(conn):
    """The new updated_at is the database's current time.

    It is not compared with the seeded value: the sample rows are dated during
    the Fall 2026 term, so before that term starts the current time is the
    earlier of the two.
    """
    before = queries.get_note(conn, 1)
    assert queries.update_note_body(conn, 1, "Rewritten during review.") == 1

    after = queries.get_note(conn, 1)
    now = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')").fetchone()[0]

    assert after[3] == "Rewritten during review."
    assert after[4] == before[4]  # created_at does not move
    assert after[5] != before[5]  # updated_at does
    assert after[5] <= now


def test_update_note_body_reports_zero_for_an_unknown_id(conn):
    assert queries.update_note_body(conn, 9999, "nothing to change") == 0


def test_create_tag(conn):
    tag_id = queries.create_tag(conn, ANA, "project")
    assert (tag_id, "project", 0) in queries.note_count_per_tag(conn, ANA)


def test_create_tag_rejects_a_repeated_name_for_one_student(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_tag(conn, ANA, "exam")


def test_create_tag_allows_a_name_another_student_already_uses(conn):
    tag_id = queries.create_tag(conn, NOELANI, "exam")
    # Ordered by count first, so the new unused tag comes after "reading".
    assert queries.note_count_per_tag(conn, NOELANI) == [
        (10, "reading", 1),
        (tag_id, "exam", 0),
    ]


def test_add_note_with_tags_writes_both_tables(conn):
    exam, sql = 2, 6
    note_id = queries.add_note_with_tags(
        conn, ANA_ICS603, "Window functions", "Not on the midterm.", [exam, sql]
    )
    assert queries.get_note(conn, note_id)[2] == "Window functions"
    assert (note_id, "Window functions", "ICS 603 Building LLM Applications") in (
        queries.notes_with_tag(conn, ANA, "sql")
    )
    assert queries.note_count_per_tag(conn, ANA)[0] == (2, "exam", 9)


def test_add_note_with_tags_accepts_an_empty_tag_list(conn):
    note_id = queries.add_note_with_tags(conn, ANA_ICS603, "Untagged", None, [])
    assert queries.get_note(conn, note_id)[2] == "Untagged"


def test_add_note_with_tags_leaves_no_note_behind_when_a_tag_fails(conn):
    """The operation completes fully or changes nothing. A tag id that does not
    exist has to undo the note insert as well."""
    before = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        queries.add_note_with_tags(conn, ANA_ICS603, "Half a write", None, [2, 9999])
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == before


def test_add_note_with_tags_rejects_a_repeated_tag_id(conn):
    """A repeated pair in this call is a mistake in the call, so the whole
    operation is undone. attach_tag_to_note() treats a repeat differently."""
    before = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        queries.add_note_with_tags(conn, ANA_ICS603, "Twice tagged", None, [2, 2])
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == before


def test_attach_tag_to_note_is_idempotent(conn):
    """Note 11 carries only 'lab'. Attaching 'exam' stores a pair; attaching it
    again changes nothing and is not an error."""
    exam = 2
    assert queries.attach_tag_to_note(conn, 11, exam) is True
    assert queries.attach_tag_to_note(conn, 11, exam) is False
    assert queries.note_count_per_tag(conn, ANA)[0] == (2, "exam", 9)


def test_attach_tag_to_note_still_rejects_a_row_that_does_not_exist(conn):
    """OR IGNORE skips a duplicate pair. It does not skip a foreign-key
    violation."""
    with pytest.raises(sqlite3.IntegrityError):
        queries.attach_tag_to_note(conn, 9999, 2)
    with pytest.raises(sqlite3.IntegrityError):
        queries.attach_tag_to_note(conn, 1, 9999)


def test_update_settings(conn):
    assert queries.update_settings(conn, ANA, "light", None, False) == 1
    assert queries.get_student_settings(conn, ANA) == ("light", None, None, 0)


def test_update_settings_reports_zero_for_a_student_with_no_settings_row(conn):
    assert queries.update_settings(conn, 9999, "light", None, False) == 0


def test_update_settings_rejects_a_theme_outside_the_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.update_settings(conn, ANA, "neon", None, False)


def test_update_settings_rejects_a_notebook_that_does_not_exist(conn):
    with pytest.raises(sqlite3.IntegrityError):
        queries.update_settings(conn, ANA, "dark", 9999, False)
