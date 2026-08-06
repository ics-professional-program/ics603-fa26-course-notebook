"""Every question the Course Notebook application asks its database.

One function per question. Each docstring names the question and says what the
function returns, including what it returns when there is no row. Values always
reach SQLite as ``?`` parameters; no SQL string is built by formatting.

Rows come back as tuples, in the order the ``SELECT`` lists its columns. That is
the default ``sqlite3`` behavior, and it is what 9.0 and 9.1 use.

SQLITE-SPECIFIC constructs in this file
---------------------------------------

Session 10.1 migrates this file to PostgreSQL and ``psycopg`` as a live
demonstration. These are the places that change. Each one is marked with a
``SQLITE-SPECIFIC`` comment where it appears. None of them is a defect; they are
correct SQLite and they are what the migration works on.

===========================  =================================================
Here (``sqlite3``)           There (``psycopg`` 3)
===========================  =================================================
``sqlite3.connect(path)``    ``psycopg.connect(os.environ["DATABASE_URL"])``
``PRAGMA foreign_keys = ON`` delete it; PostgreSQL always enforces foreign keys
``?`` placeholders           ``%s`` placeholders — every ``execute`` call below
``cursor.lastrowid``         ``INSERT ... RETURNING id`` then ``fetchone()``
``with conn:``               ``with conn.transaction():`` — see the note below
``strftime(...)``            ``now()``; PostgreSQL has no ``strftime``
``INSERT OR IGNORE``         ``INSERT ... ON CONFLICT DO NOTHING``
Python ``bool`` for 0/1      the column becomes ``boolean``; see ``compact_view``
===========================  =================================================

The ``with conn:`` row is the one that produces a confusing failure. In
``sqlite3`` it opens a transaction and leaves the connection open. In psycopg 3
it *closes the connection* at the end of the block, so code written this way
appears to work once and then fails on the next query.
"""

import os
import sqlite3
from pathlib import Path
from collections.abc import Sequence

# The database file. 10.1 replaces this with a DATABASE_URL naming a PostgreSQL
# service reached over the network, so the environment variable is already how
# the path is supplied.
DB_PATH = Path(os.environ.get("COURSE_NOTEBOOK_DB", "app.db"))


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def connect(db_path=DB_PATH) -> sqlite3.Connection:
    """Open a connection to the notebook database with foreign keys enforced.

    Every part of the application opens its connection here, so 10.1 changes one
    function instead of every call site.

    Returns an open ``sqlite3.Connection``. The caller closes it.
    """
    conn = sqlite3.connect(db_path)

    # SQLITE-SPECIFIC: SQLite does not enforce foreign keys unless this is set,
    # it is set per connection, and it must be set before a transaction begins.
    # Forgetting it makes every REFERENCES clause in the schema decorative.
    # PostgreSQL always enforces foreign keys and has no PRAGMA statement, so
    # 10.1 deletes this line.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Students and settings
# ---------------------------------------------------------------------------


def create_student(
    conn: sqlite3.Connection,
    name: str,
    email: str,
    theme: str = "system",
    compact_view: bool = False,
) -> int:
    """A student signs up. What rows does that create?

    Creates the account and its one settings row. Two tables change, so both
    changes happen or neither does — this is one of the two write-across-two-
    tables operations 9.2 Step 6 requires.

    The schema cannot require a settings row to exist: ``UNIQUE`` on
    ``student_settings.student_id`` enforces at most one, never exactly one. This
    function is where "one settings row per student" is actually maintained.

    Returns the new ``students.id``. Raises ``sqlite3.IntegrityError`` if the
    email address is already used.
    """
    # SQLITE-SPECIFIC: `with conn:` is a transaction block in sqlite3 and leaves
    # the connection open. In psycopg 3 it CLOSES the connection at the end of
    # the block; there it becomes `with conn.transaction():`.
    with conn:
        cur = conn.execute(
            "INSERT INTO students (name, email) VALUES (?, ?)",
            (name, email),
        )
        # SQLITE-SPECIFIC: lastrowid. PostgreSQL needs
        # "INSERT ... RETURNING id" followed by fetchone().
        student_id = cur.lastrowid

        conn.execute(
            """
            INSERT INTO student_settings (student_id, theme, compact_view)
            VALUES (?, ?, ?)
            """,
            # SQLITE-SPECIFIC: compact_view is a Python bool going into an
            # INTEGER column. sqlite3 stores True as 1. psycopg sends a Python
            # bool as a PostgreSQL boolean, which an integer column rejects, so
            # 10.1 changes the column type to boolean rather than this call.
            (student_id, theme, compact_view),
        )
    return student_id


def get_student(
    conn: sqlite3.Connection, student_id: int
) -> tuple[int, str, str, str] | None:
    """Who is this account?

    Returns ``(id, name, email, created_at)``, or ``None`` when no student has
    that id.
    """
    return conn.execute(
        "SELECT id, name, email, created_at FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()


def get_student_settings(
    conn: sqlite3.Connection, student_id: int
) -> tuple[str, int | None, str | None, int] | None:
    """What are this student's settings, and what is their default notebook called?

    This is the one-to-one read. The join is a ``LEFT JOIN`` because
    ``default_notebook_id`` may be ``NULL`` — a student who has not chosen a
    default still has settings, and an ``INNER JOIN`` would drop them.

    Returns ``(theme, default_notebook_id, default_notebook_name, compact_view)``.
    The middle two are ``None`` when no default notebook is chosen.
    ``compact_view`` is 0 or 1. Returns ``None`` when the student has no settings
    row at all.
    """
    return conn.execute(
        """
        SELECT student_settings.theme,
               student_settings.default_notebook_id,
               notebooks.name,
               student_settings.compact_view
        FROM student_settings
        LEFT JOIN notebooks ON notebooks.id = student_settings.default_notebook_id
        WHERE student_settings.student_id = ?
        """,
        (student_id,),
    ).fetchone()


def update_settings(
    conn: sqlite3.Connection,
    student_id: int,
    theme: str,
    default_notebook_id: int | None,
    compact_view: bool,
) -> int:
    """Change a student's theme, default notebook and list density.

    Returns the number of rows changed: 1 normally, 0 when the student has no
    settings row. Raises ``sqlite3.IntegrityError`` if ``theme`` is not one of
    the three values the ``CHECK`` constraint permits, or if
    ``default_notebook_id`` names a notebook that does not exist.
    """
    with conn:  # SQLITE-SPECIFIC transaction block; see the module docstring.
        cur = conn.execute(
            """
            UPDATE student_settings
            SET theme = ?, default_notebook_id = ?, compact_view = ?
            WHERE student_id = ?
            """,
            (theme, default_notebook_id, compact_view, student_id),
        )
    return cur.rowcount


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


def create_notebook(conn: sqlite3.Connection, student_id: int, name: str) -> int:
    """Start a notebook, usually for one course.

    Returns the new ``notebooks.id``. Raises ``sqlite3.IntegrityError`` if the
    student already has a notebook with this name, or if no student has that id.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute(
            "INSERT INTO notebooks (student_id, name) VALUES (?, ?)",
            (student_id, name),
        )
        # SQLITE-SPECIFIC: lastrowid.
        notebook_id = cur.lastrowid
    return notebook_id


def get_notebook(
    conn: sqlite3.Connection, notebook_id: int
) -> tuple[int, int, str, str] | None:
    """Which notebook is this, and whose is it?

    The application calls this before writing a note, so that a request naming a
    notebook that does not exist gets a 404 instead of a foreign-key error it
    would then have to guess the meaning of.

    Returns ``(id, student_id, name, created_at)``, or ``None`` when no notebook
    has that id.
    """
    return conn.execute(
        "SELECT id, student_id, name, created_at FROM notebooks WHERE id = ?",
        (notebook_id,),
    ).fetchone()


def list_notebooks(
    conn: sqlite3.Connection, student_id: int
) -> list[tuple[int, str, int]]:
    """Which notebooks does this student have, and how many notes is each holding?

    ``LEFT JOIN`` and ``COUNT(notes.id)``, so a notebook with no notes appears
    with a count of 0 rather than being dropped. ``COUNT(*)`` would report 1 for
    that notebook, because the unmatched left row is still one joined row.

    Returns a list of ``(notebook_id, name, note_count)``, ordered by name.
    """
    return conn.execute(
        """
        SELECT notebooks.id, notebooks.name, COUNT(notes.id) AS note_count
        FROM notebooks
        LEFT JOIN notes ON notes.notebook_id = notebooks.id
        WHERE notebooks.student_id = ?
        GROUP BY notebooks.id
        ORDER BY notebooks.name
        """,
        (student_id,),
    ).fetchall()


def delete_notebook(conn: sqlite3.Connection, notebook_id: int) -> int:
    """Remove a notebook the student no longer wants.

    Returns the number of rows deleted: 1 normally, 0 when no notebook has that
    id.

    Raises ``sqlite3.IntegrityError`` when the notebook still holds notes, because
    ``notes.notebook_id`` is declared ``ON DELETE RESTRICT``. The application
    turns that into HTTP 409 rather than deleting a term of notes by accident.

    Deleting a notebook that is somebody's default notebook succeeds and sets
    ``student_settings.default_notebook_id`` back to ``NULL``.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    return cur.rowcount


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def add_note(
    conn: sqlite3.Connection,
    notebook_id: int,
    title: str,
    body: str | None = None,
) -> int:
    """Write down one note. This is the insert 9.2 Step 6 requires.

    ``created_at`` and ``updated_at`` are left out of the column list on purpose,
    so the ``DEFAULT`` in db/schema.sql fills both with the current UTC time.

    Returns the new ``notes.id``. Raises ``sqlite3.IntegrityError`` if no
    notebook has that id.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute(
            "INSERT INTO notes (notebook_id, title, body) VALUES (?, ?, ?)",
            (notebook_id, title, body),
        )
        # SQLITE-SPECIFIC: lastrowid.
        note_id = cur.lastrowid
    return note_id


def get_note(
    conn: sqlite3.Connection, note_id: int
) -> tuple[int, int, str, str | None, str, str] | None:
    """Show me this note. This is the read 9.2 Step 6 requires.

    Returns ``(id, notebook_id, title, body, created_at, updated_at)``, or
    ``None`` when no note has that id. ``body`` is ``None`` for a note whose body
    has not been written yet.
    """
    return conn.execute(
        """
        SELECT id, notebook_id, title, body, created_at, updated_at
        FROM notes
        WHERE id = ?
        """,
        (note_id,),
    ).fetchone()


def update_note_body(conn: sqlite3.Connection, note_id: int, body: str) -> int:
    """I edited this note. Save the new body and record that it changed just now.

    This is where "every note records when it was last changed" is actually
    maintained: the column default covers the insert, and this statement covers
    every change afterwards.

    Returns the number of rows changed: 1 normally, 0 when no note has that id.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute(
            # SQLITE-SPECIFIC: strftime() is a SQLite function. PostgreSQL has
            # no strftime; there this becomes "updated_at = now()" against a
            # timestamptz column.
            """
            UPDATE notes
            SET body = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ?
            """,
            (body, note_id),
        )
    return cur.rowcount


def notes_with_notebook_name(
    conn: sqlite3.Connection, student_id: int
) -> list[tuple[int, str, str, str]]:
    """Which notes has this student written, and which notebook is each one in?

    This is the ``JOIN`` over a declared relationship that 9.2 Step 6 requires.
    It is also the only way to answer the question: ``notes`` has no
    ``student_id`` column, so a note's owner is reached through its notebook.

    Returns a list of ``(note_id, title, notebook_name, updated_at)``, most
    recently changed first.
    """
    return conn.execute(
        """
        SELECT notes.id, notes.title, notebooks.name, notes.updated_at
        FROM notes
        INNER JOIN notebooks ON notebooks.id = notes.notebook_id
        WHERE notebooks.student_id = ?
        ORDER BY notes.updated_at DESC, notes.id
        """,
        (student_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Tags and the notes they label
# ---------------------------------------------------------------------------


def create_tag(conn: sqlite3.Connection, student_id: int, name: str) -> int:
    """Add a label this student can put on notes.

    Returns the new ``tags.id``. Raises ``sqlite3.IntegrityError`` if this
    student already has a tag with this name. A different student may have one
    with the same name; the constraint is ``UNIQUE (student_id, name)``.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute(
            "INSERT INTO tags (student_id, name) VALUES (?, ?)",
            (student_id, name),
        )
        # SQLITE-SPECIFIC: lastrowid.
        tag_id = cur.lastrowid
    return tag_id


def add_note_with_tags(
    conn: sqlite3.Connection,
    notebook_id: int,
    title: str,
    body: str | None,
    tag_ids: Sequence[int],
) -> int:
    """Write a note and label it, as one action.

    The second write-across-two-tables operation 9.2 Step 6 requires. The
    requirement is not that a note has tags — ``tag_ids=[]`` is a valid call. The
    requirement is that the whole request either completes or changes nothing: if
    one tag insert fails, the note insert is undone with it.

    Because the transaction boundary is inside this function, it is a complete
    operation on its own and cannot be called from inside a larger transaction
    that the caller wants to commit.

    Returns the new ``notes.id``. Raises ``sqlite3.IntegrityError`` if the
    notebook does not exist, if any tag id does not exist, or if the same tag id
    appears twice in ``tag_ids``.
    """
    with conn:  # SQLITE-SPECIFIC transaction block; see the module docstring.
        cur = conn.execute(
            "INSERT INTO notes (notebook_id, title, body) VALUES (?, ?, ?)",
            (notebook_id, title, body),
        )
        # SQLITE-SPECIFIC: lastrowid.
        note_id = cur.lastrowid

        for tag_id in tag_ids:
            conn.execute(
                "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, tag_id),
            )
    return note_id


def attach_tag_to_note(conn: sqlite3.Connection, note_id: int, tag_id: int) -> bool:
    """Put one label on one existing note.

    Applying a tag that is already applied is not an error and changes nothing —
    the spec lists "a student applies the same tag twice to one note" as
    something that happens, and pressing a button twice should not produce a
    message. ``add_note_with_tags()`` treats a repeated pair differently, because
    a malformed list of tag ids sent to that operation is a mistake in the call.

    Returns ``True`` if a new pair was stored, ``False`` if the note already
    carried this tag. Raises ``sqlite3.IntegrityError`` if the note or the tag
    does not exist: ``OR IGNORE`` skips constraint violations, but foreign-key
    violations are still raised.
    """
    with conn:  # SQLITE-SPECIFIC transaction block.
        cur = conn.execute(
            # SQLITE-SPECIFIC: "INSERT OR IGNORE" is SQLite's conflict-resolution
            # syntax. PostgreSQL writes it "INSERT ... ON CONFLICT DO NOTHING".
            "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
            (note_id, tag_id),
        )
    return cur.rowcount == 1


def notes_with_tag(
    conn: sqlite3.Connection, student_id: int, tag_name: str
) -> list[tuple[int, str, str]]:
    """List every note this student has associated with a chosen tag.

    Two joins, because the relationship is many-to-many: one to the junction
    table and one to the entity table reached after it. A third join reaches
    ``notebooks``, both to report which notebook each note is in and to check
    that the note belongs to this student — ``notes`` has no ``student_id``
    column of its own.

    A tag name that labels no notes, and a tag name the student has never
    created, both return an empty list. Finding nothing is a correct answer.

    Returns a list of ``(note_id, title, notebook_name)``, ordered by title.
    """
    return conn.execute(
        """
        SELECT notes.id, notes.title, notebooks.name
        FROM notes
        INNER JOIN notebooks ON notebooks.id = notes.notebook_id
        INNER JOIN note_tags ON note_tags.note_id = notes.id
        INNER JOIN tags      ON tags.id = note_tags.tag_id
        WHERE notebooks.student_id = ?
          AND tags.student_id = ?
          AND tags.name = ?
        ORDER BY notes.title
        """,
        (student_id, student_id, tag_name),
    ).fetchall()


def note_count_per_tag(
    conn: sqlite3.Connection, student_id: int
) -> list[tuple[int, str, int]]:
    """How many notes is each of this student's tags associated with?

    The aggregate with ``GROUP BY`` that 9.2 Step 6 requires, and the second of
    the two questions the spec asks for by name.

    ``LEFT JOIN`` with ``COUNT(note_tags.note_id)`` keeps tags that label no
    notes and reports 0 for them, which is what a student looking at their tag
    list wants to see. ``COUNT(*)`` would report 1 for those tags, because the
    unmatched left row is still one joined row.

    Returns a list of ``(tag_id, name, note_count)``, largest count first and
    then by name.
    """
    return conn.execute(
        """
        SELECT tags.id, tags.name, COUNT(note_tags.note_id) AS note_count
        FROM tags
        LEFT JOIN note_tags ON note_tags.tag_id = tags.id
        WHERE tags.student_id = ?
        GROUP BY tags.id
        ORDER BY note_count DESC, tags.name
        """,
        (student_id,),
    ).fetchall()


def tags_used_at_least(
    conn: sqlite3.Connection, student_id: int, minimum: int
) -> list[tuple[str, int]]:
    """Which of this student's tags label at least ``minimum`` notes?

    ``WHERE`` filters rows before grouping; ``HAVING`` filters whole groups after
    their counts are computed, so the threshold has to be in ``HAVING``.

    The aggregate is repeated in ``HAVING`` rather than referring to the
    ``note_count`` alias. SQLite accepts the alias there and PostgreSQL does not,
    and 9.1 asks for the form that works on both.

    Returns a list of ``(name, note_count)``, largest count first and then by
    name. ``minimum=0`` returns every tag, including unused ones.
    """
    return conn.execute(
        """
        SELECT tags.name, COUNT(note_tags.note_id) AS note_count
        FROM tags
        LEFT JOIN note_tags ON note_tags.tag_id = tags.id
        WHERE tags.student_id = ?
        GROUP BY tags.id
        HAVING COUNT(note_tags.note_id) >= ?
        ORDER BY note_count DESC, tags.name
        """,
        (student_id, minimum),
    ).fetchall()
