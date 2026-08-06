"""Create the Course Notebook tables and load sample rows into them.

Run it from the project root::

    python db/seed.py            # or: python -m db.seed

It deletes any existing database file first, so it is safe to run as often as
you like while working.

About the sample rows
---------------------

They are chosen, not generated. Reading them should feel like reading a real
student's notebook, and between them they cover the cases the queries have to
handle:

- a notebook holding no notes (Ana's "Reading group")
- a note whose body has not been written yet (``body`` is ``NULL``)
- a tag that labels no notes (Ana's "review")
- a student who has chosen no default notebook (Noelani)
- text outside plain ASCII (a name with an ʻokina and a kahakō, and "Résumé")
- two students with a tag of the same name, so per-student tag scoping is visible
- tag counts that differ from each other, so a GROUP BY result is worth reading

Timestamps are supplied here rather than left to the column defaults in
db/schema.sql, because seeded notes have to be spread across a term for
"most recently changed first" to mean anything. Every value uses the format the
schema records: ISO 8601, UTC, to the second.

SQLITE-SPECIFIC constructs in this file
---------------------------------------

- ``Path.unlink()`` as the reset. Deleting the file deletes the database,
  because in SQLite the file *is* the database. Against PostgreSQL there is no
  file to delete; the reset there is ``DROP TABLE`` or ``docker compose down -v``
  followed by re-creating the schema.
- ``conn.executescript()``. ``sqlite3`` needs it because ``execute`` accepts only
  one statement and a schema file holds several. psycopg's ``execute`` accepts
  several statements in one string, so the call becomes an ordinary ``execute``.
- ``with conn:`` as a transaction block. In psycopg 3 that closes the connection;
  there it becomes ``with conn.transaction():`` -- but only together with
  ``psycopg.connect(..., autocommit=True)``. Without autocommit the schema
  statements above open a transaction, this block becomes a savepoint inside it,
  and closing the connection discards every seeded row while still printing the
  expected counts. ``db/queries.py`` explains this in full.
- ``cursor.lastrowid``. PostgreSQL needs ``INSERT ... RETURNING id`` followed
  by ``fetchone()[0]``; psycopg returns rows as tuples, so a bare ``fetchone()``
  gives ``(4,)`` rather than ``4``.
- ``?`` placeholders. psycopg uses ``%s``.
- Python ``bool`` values for ``compact_view``, an INTEGER column here.
"""

import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Running as `python db/seed.py` puts db/ on sys.path, not the project root.
    # Add the root so `from db.queries import connect` works either way.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.queries import DB_PATH, connect  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# ---------------------------------------------------------------------------
# The sample rows
# ---------------------------------------------------------------------------

# (name, email, account created at, theme, default notebook, compact view)
STUDENTS = [
    {
        "name": "Ana Kealoha",
        "email": "ana.kealoha@hawaii.edu",
        "created_at": "2026-08-24T18:02:11Z",
        "theme": "dark",
        "default_notebook": "ICS 603 Building LLM Applications",
        "compact_view": True,
    },
    {
        "name": "Marcus Tanaka",
        "email": "marcus.tanaka@hawaii.edu",
        "created_at": "2026-08-25T02:41:07Z",
        "theme": "light",
        "default_notebook": "ICS 603 Building LLM Applications",
        "compact_view": False,
    },
    {
        # An ʻokina and a kahakō, so the sample data is not all plain ASCII.
        "name": "Noelani Kaʻōpua",
        "email": "noelani.kaopua@hawaii.edu",
        "created_at": "2026-08-24T21:15:44Z",
        "theme": "system",
        # This student has not chosen a default notebook. The application asks
        # which notebook to write into instead of choosing one for her.
        "default_notebook": None,
        "compact_view": False,
    },
]

# student email -> [(notebook name, created at), ...]
NOTEBOOKS = {
    "ana.kealoha@hawaii.edu": [
        ("ICS 603 Building LLM Applications", "2026-08-24T18:04:50Z"),
        ("ICS 635 Applied Machine Learning", "2026-08-24T18:05:12Z"),
        ("ICS 601 Applied Industry Seminar", "2026-08-26T19:30:03Z"),
        # Holds no notes. It is here so list_notebooks() has a row whose count
        # is 0, and so there is a notebook that delete_notebook() can remove.
        ("Reading group", "2026-09-09T20:11:38Z"),
    ],
    "marcus.tanaka@hawaii.edu": [
        # Same name as one of Ana's notebooks. UNIQUE (student_id, name) permits
        # this; UNIQUE (name) alone would have rejected it.
        ("ICS 603 Building LLM Applications", "2026-08-25T02:44:19Z"),
        ("ICS 604 Data Science", "2026-08-25T02:45:02Z"),
    ],
    "noelani.kaopua@hawaii.edu": [
        ("ICS 635 Applied Machine Learning", "2026-08-24T21:18:26Z"),
    ],
}

# student email -> [tag name, ...]
TAGS = {
    "ana.kealoha@hawaii.edu": [
        "docker",
        "exam",
        "lab",
        "reading",
        # Labels no notes. note_count_per_tag() reports 0 for it, which is only
        # true because that query uses a LEFT JOIN and COUNT(note_tags.note_id).
        "review",
        "sql",
        "todo",
    ],
    # Marcus has his own rows named "docker" and "exam". They are different rows
    # from Ana's, with different ids, and neither student sees the other's.
    "marcus.tanaka@hawaii.edu": ["docker", "exam"],
    "noelani.kaopua@hawaii.edu": ["reading"],
}

# (student email, notebook name, title, body, created at, updated at, [tags])
NOTES = [
    # -- Ana, ICS 603 -------------------------------------------------------
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "Parameterized queries are the only safe way to pass user text",
        "Never build SQL with an f-string. A ? sends the value to SQLite "
        "separately from the statement, so an apostrophe in a note title stays "
        "a character instead of closing the quoted value and starting new SQL.",
        "2026-10-20T19:12:44Z",
        "2026-10-20T19:12:44Z",
        ["sql", "exam"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "PRAGMA foreign_keys is per connection",
        "SQLite does not enforce foreign keys unless the connection sets "
        "PRAGMA foreign_keys = ON, and it has to be set before a transaction "
        "starts. A schema full of REFERENCES clauses can still accept a child "
        "row with no parent if this is forgotten.",
        "2026-10-22T19:05:02Z",
        "2026-10-23T04:38:17Z",
        ["sql", "exam"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "A junction table is what a many-to-many needs",
        "A foreign-key column holds one value, so it cannot hold a list of "
        "tags. note_tags stores one row per (note, tag) pair, and "
        "PRIMARY KEY (note_id, tag_id) is what stops the same pair being "
        "stored twice.",
        "2026-10-22T19:31:56Z",
        "2026-10-22T19:31:56Z",
        ["sql", "exam"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "Midterm review — what to go over",
        "Redo the JOIN exercises from 9.1. Write out the difference between "
        "WHERE and HAVING from memory. Rerun the transaction demo with the "
        "error in the middle and check both balances afterwards.",
        "2026-10-27T02:20:09Z",
        "2026-11-02T18:44:31Z",
        ["exam", "todo"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "response_model does two things",
        "It documents the output shape on /docs, and it validates what the "
        "route returns. Without it a field I did not mean to send can leak "
        "into the response and nothing complains.",
        "2026-09-24T20:48:15Z",
        "2026-09-24T20:48:15Z",
        ["reading"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "Copy the dependency files before the code",
        "Docker reuses a layer's cache until something that layer depends on "
        "changes. Copy pyproject.toml and uv.lock and install first, then copy "
        "the source. Reverse the two and every one-line edit reinstalls every "
        "package.",
        "2026-11-05T19:22:40Z",
        "2026-11-05T19:22:40Z",
        ["docker", "exam"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "EXPOSE does not publish the port",
        "EXPOSE only records which port the process listens on inside the "
        "container. Publishing happens with -p on docker run, or a ports entry "
        "in Compose. Without it the container runs, the process listens, and "
        "the browser still gets nothing.",
        "2026-11-05T19:41:03Z",
        "2026-11-05T19:41:03Z",
        ["docker", "exam"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "Week 12 lecture — write this up",
        # body is NULL: a title typed during class with the body still to come.
        None,
        "2026-11-17T19:04:58Z",
        "2026-11-17T19:04:58Z",
        ["todo"],
    ),
    # -- Ana, ICS 635 -------------------------------------------------------
    (
        "ana.kealoha@hawaii.edu",
        "ICS 635 Applied Machine Learning",
        "Touch the test set once",
        "Fit on train, tune on validation, and use test at the very end. "
        "Choosing hyperparameters by the test score makes the reported number "
        "optimistic, and there is no way to undo it afterwards.",
        "2026-09-17T21:33:12Z",
        "2026-10-26T03:12:55Z",
        ["exam", "reading"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 635 Applied Machine Learning",
        "Precision and recall answer different questions",
        "Precision: of the rows I labeled positive, how many were positive. "
        "Recall: of the rows that were positive, how many did I find. Moving "
        "the threshold raises one and lowers the other, so quote both.",
        "2026-09-29T21:10:47Z",
        "2026-09-29T21:10:47Z",
        ["exam", "reading"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 635 Applied Machine Learning",
        "Lab 4: gradient descent by hand",
        "Worked one update step on paper for a two-parameter linear model "
        "before opening the notebook. The sign of the update is the part I "
        "kept getting wrong: the step goes against the gradient.",
        "2026-10-08T22:05:31Z",
        "2026-10-08T22:05:31Z",
        ["lab"],
    ),
    # -- Ana, ICS 601 -------------------------------------------------------
    (
        "ana.kealoha@hawaii.edu",
        "ICS 601 Applied Industry Seminar",
        "Guest talk — reading a production incident review",
        "The speaker's point was that a useful review names the failure and "
        "not the person, and that its output is a change to a system rather "
        "than a promise to be more careful next time.",
        "2026-10-15T20:52:19Z",
        "2026-10-15T20:52:19Z",
        ["reading"],
    ),
    (
        "ana.kealoha@hawaii.edu",
        "ICS 601 Applied Industry Seminar",
        "Résumé draft feedback",
        "One page. Lead each line with what changed, not with what I was "
        "assigned. Cut the skills list down to what I can be questioned on for "
        "ten minutes. Printed copy for the mock interview on Nov 3.",
        "2026-10-16T01:24:38Z",
        "2026-10-16T01:24:38Z",
        ["todo"],
    ),
    # -- Marcus ------------------------------------------------------------
    (
        "marcus.tanaka@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "A volume is not the writable layer",
        "Anything the application writes at runtime goes to that one "
        "container's writable layer, and removing the container discards it. A "
        "named volume is stored outside the container: docker compose down "
        "keeps it, and down -v deletes it.",
        "2026-11-06T20:15:27Z",
        "2026-11-06T20:15:27Z",
        ["docker", "exam"],
    ),
    (
        "marcus.tanaka@hawaii.edu",
        "ICS 603 Building LLM Applications",
        "The app reaches the database at db, not localhost",
        "Inside the application container, localhost is the application "
        "container. Compose gives the project a network on which the service "
        "name db resolves to the database container.",
        "2026-11-10T20:33:41Z",
        "2026-11-10T20:33:41Z",
        ["docker"],
    ),
    (
        "marcus.tanaka@hawaii.edu",
        "ICS 604 Data Science",
        "A missing value is not a zero",
        "Filling a missing measurement with 0 moves the mean and hides the "
        "gap. Say what the absence means first, then choose: drop the row, "
        "impute and record that you did, or treat absence as its own value.",
        "2026-10-01T22:47:56Z",
        "2026-10-01T22:47:56Z",
        ["exam"],
    ),
    # -- Noelani -----------------------------------------------------------
    (
        "noelani.kaopua@hawaii.edu",
        "ICS 635 Applied Machine Learning",
        "Write down the baseline before training anything",
        "Score a constant predictor first and write the number down. If the "
        "trained model does not beat it, the problem is in the features or the "
        "labels, not in the choice of model.",
        "2026-09-15T21:02:14Z",
        "2026-09-15T21:02:14Z",
        ["reading"],
    ),
]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def seed_database(conn: sqlite3.Connection) -> None:
    """Insert every sample row into an empty, already-created database.

    The whole load is one transaction, so a failure part-way leaves no rows
    behind instead of half a notebook.

    Parent rows go in before the child rows that refer to them: students, then
    notebooks and tags, then notes, then the note-tag pairs, and settings last
    because a settings row may name a notebook.
    """
    # SQLITE-SPECIFIC: `with conn:` opens a transaction and leaves the
    # connection open. In psycopg 3 it CLOSES the connection at the end of the
    # block; there it becomes `with conn.transaction():`, and the connection
    # must be opened with autocommit=True or nothing seeded here is committed.
    with conn:
        student_ids = {}
        for student in STUDENTS:
            cur = conn.execute(
                "INSERT INTO students (name, email, created_at) VALUES (?, ?, ?)",
                (student["name"], student["email"], student["created_at"]),
            )
            # SQLITE-SPECIFIC: lastrowid. PostgreSQL needs
            # "INSERT ... RETURNING id" and then fetchone()[0]; psycopg
            # returns a tuple, so a bare fetchone() gives (4,) rather than 4.
            student_ids[student["email"]] = cur.lastrowid

        notebook_ids = {}
        for email, notebooks in NOTEBOOKS.items():
            for name, created_at in notebooks:
                cur = conn.execute(
                    """
                    INSERT INTO notebooks (student_id, name, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (student_ids[email], name, created_at),
                )
                notebook_ids[(email, name)] = cur.lastrowid

        tag_ids = {}
        for email, names in TAGS.items():
            for name in names:
                cur = conn.execute(
                    "INSERT INTO tags (student_id, name) VALUES (?, ?)",
                    (student_ids[email], name),
                )
                tag_ids[(email, name)] = cur.lastrowid

        for email, notebook, title, body, created_at, updated_at, tags in NOTES:
            cur = conn.execute(
                """
                INSERT INTO notes
                    (notebook_id, title, body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (notebook_ids[(email, notebook)], title, body, created_at, updated_at),
            )
            note_id = cur.lastrowid
            for tag in tags:
                conn.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                    (note_id, tag_ids[(email, tag)]),
                )

        for student in STUDENTS:
            default_notebook = student["default_notebook"]
            default_notebook_id = (
                notebook_ids[(student["email"], default_notebook)]
                if default_notebook
                else None
            )
            conn.execute(
                """
                INSERT INTO student_settings
                    (student_id, theme, default_notebook_id, compact_view)
                VALUES (?, ?, ?, ?)
                """,
                (
                    student_ids[student["email"]],
                    student["theme"],
                    default_notebook_id,
                    # SQLITE-SPECIFIC: a Python bool going into an INTEGER
                    # column. sqlite3 stores True as 1. psycopg sends a Python
                    # bool as a PostgreSQL boolean, which an integer column
                    # rejects, so 10.1 changes the column type to boolean.
                    student["compact_view"],
                ),
            )


def build(db_path=DB_PATH) -> sqlite3.Connection:
    """Delete any existing database, create the tables, and load the sample rows.

    Returns the open connection, so a caller that wants to query the result does
    not have to open a second one.
    """
    # SQLITE-SPECIFIC: in SQLite the file is the database, so deleting the file
    # is the reset. There is nothing to delete on a PostgreSQL server; the
    # equivalent there is DROP TABLE, or `docker compose down -v` followed by
    # creating the schema again.
    Path(db_path).unlink(missing_ok=True)

    conn = connect(db_path)

    # SQLITE-SPECIFIC: executescript. sqlite3's execute() accepts one statement
    # and a schema file holds several. It also commits any pending transaction
    # before it runs, which is why it is called outside the `with conn:` block
    # in seed_database() rather than inside one.
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    seed_database(conn)
    return conn


def main() -> None:
    conn = build()
    counts = {
        table: conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in (
            "students",
            "notebooks",
            "notes",
            "tags",
            "note_tags",
            "student_settings",
        )
    }
    conn.close()

    print("Created", DB_PATH)
    for table, count in counts.items():
        print("  {:<17} {:>3} rows".format(table, count))


if __name__ == "__main__":
    main()
