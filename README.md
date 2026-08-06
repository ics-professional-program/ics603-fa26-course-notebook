# Course Notebook — ICS 603 reference application

A study tool that lets a student collect class notes, organize them into
notebooks, label them with tags, and find them again later. A FastAPI service
over SQLite, using raw SQL through the standard library's `sqlite3` module. No
ORM: the course teaches SQL you can read and check, and an ORM would hide the
part being taught.

This is the instructor's reference implementation of the **Course Notebook**
design document — the fallback spec printed in session 9.2 for students whose
own project spec does not describe enough data to design a database to build a database from.

## The three jobs it does

1. **9.2 — Workshop: Give Your Project a Database.** A student without a usable
   spec of their own uses the Course Notebook design document instead and runs
   the workshop's seven steps on it. This repository is what those steps produce:
   `docs/design.md`, `db/schema.sql`, `db/seed.py` and `db/queries.py`.
2. **10.0 — Docker Fundamentals.** The instructor containerizes this application
   live, using the `uv` Dockerfile pattern the session teaches. `.dockerignore`
   excludes `*.db`, so the container starts with no database and `GET /health` is
   the endpoint the build is checked against.
3. **10.1 — Compose and the Postgres Swap.** The instructor migrates this exact
   code from SQLite to PostgreSQL live, and students then perform the same
   migration on their own projects. See the next section: the SQLite-specific
   code here is deliberate and is the material that migration works on.

## The SQLite-specific code is deliberate

This application does **not** use portable, dialect-neutral SQL. That is a
decision, not an oversight.

9.2 tells students to prefer SQL both databases accept. This application does
the opposite on purpose, because 10.1 begins with the instructor migrating it to
PostgreSQL in front of the class. Code that already runs on both databases has
nothing to demonstrate.

Everything in the table below is correct, idiomatic SQLite, written the way
sessions 9.0 to 9.2 teach it. Each one is marked with a `SQLITE-SPECIFIC`
comment at the place it appears, so the migration can be rehearsed by searching
for that word:

```bash
grep -rn "SQLITE-SPECIFIC" db/ app/ tests/
```

| What | Where | PostgreSQL form |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `db/schema.sql`, five tables | `integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY` |
| Timestamps as ISO 8601 `TEXT` | `db/schema.sql`, four columns | `timestamptz` |
| `DEFAULT (strftime(...))` | `db/schema.sql`, four columns | `DEFAULT now()`; PostgreSQL has no `strftime` |
| `strftime(...)` in an `UPDATE` | `db/queries.py`, `update_note_body` | `now()` |
| `INTEGER` + `CHECK (col IN (0, 1))` for true/false | `db/schema.sql`, `compact_view` | a `boolean` column, and the `CHECK` goes away |
| A Python `bool` bound to that column | `db/queries.py`, `db/seed.py` | works once the column is `boolean`; psycopg sends a bool as a bool, which an `integer` column rejects |
| `PRAGMA foreign_keys = ON` | `db/queries.py`, `connect` | delete it; PostgreSQL always enforces foreign keys |
| `sqlite3.connect(path)` | `db/queries.py`, `connect` | `psycopg.connect(os.environ["DATABASE_URL"])` |
| `?` placeholders | every `execute` call in `db/` | `%s` |
| `cursor.lastrowid` | `db/queries.py` (five sites), `db/seed.py` | `INSERT ... RETURNING id` then `fetchone()` |
| `with conn:` as a transaction | `db/queries.py` (nine sites), `db/seed.py` | `with conn.transaction():` — in psycopg 3, `with conn:` **closes the connection** |
| `INSERT OR IGNORE` | `db/queries.py`, `attach_tag_to_note` | `INSERT ... ON CONFLICT DO NOTHING` |
| `conn.executescript()` | `db/seed.py`, `build` | psycopg's `execute` takes several statements, so it becomes a plain `execute` |
| Deleting the database file as the reset | `db/seed.py`, `build` | `DROP TABLE`, or `docker compose down -v` and then create the schema again |

The `with conn:` row is the one that causes a confusing failure and the one 10.1
warns about: in `sqlite3` it opens a transaction and leaves the connection open,
and in psycopg 3 it closes the connection at the end of the block. Code written
the Module 9 way appears to work once and then fails on the next query.

## What is in here

```text
docs/design.md   the 9.2 design document, plus the sixteen decisions it does not make
docs/plan.md     the build order and what each file is responsible for
db/schema.sql    six tables, their constraints, and two indexes
db/seed.py       creates the tables and loads the sample rows
db/queries.py    one function per question the application asks the database
app/main.py      the FastAPI service
tests/           the constraints, the queries, and the endpoints
Dockerfile       the uv pattern from 10.0
```

## The schema

Six tables, covering all three relationship kinds 9.2 teaches.

```text
students          -- one to many -->   notebooks
notebooks         -- one to many -->   notes
students          -- one to many -->   tags
notes             <- many to many ->   tags        through note_tags
students          -- one to one  -->   student_settings
student_settings  -- at most one -->   notebooks   the default notebook
```

| Relationship | Kind | Stored as |
|---|---|---|
| a notebook holds many notes | one-to-many | `notes.notebook_id` foreign key, `NOT NULL` |
| a student has many notebooks | one-to-many | `notebooks.student_id` foreign key |
| a student has many tags | one-to-many | `tags.student_id` foreign key |
| notes and tags | many-to-many | `note_tags`, with `PRIMARY KEY (note_id, tag_id)` |
| a student has one settings row | one-to-one | `student_settings.student_id`, foreign key **plus `UNIQUE`** |

Every decision behind those constraints — what a notebook deletion does, whether
tags are global, how "last changed" is maintained, what a default notebook means
when that notebook is deleted — is written down with its reason in
`docs/design.md`. Read that before changing the schema.

## Running it

`uv` is what the course uses:

```bash
uv sync                    # uv.lock is committed; this installs exactly it
uv run python db/seed.py   # creates app.db and loads the sample rows
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>.

Without `uv`, the standard library is enough for the database and only the web
layer needs installing:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install fastapi uvicorn pydantic pytest httpx
.venv/bin/python db/seed.py
.venv/bin/python -m uvicorn app.main:app --reload
```

`db/seed.py` deletes `app.db` and rebuilds it, so run it as often as you like.
`app.db` is development data and is not committed.

Tests:

```bash
uv run pytest          # or: .venv/bin/python -m pytest
```

The tests build their own database in a temporary directory, so they neither
need nor disturb `app.db`.

## Try it from the command line

```bash
# a route that needs no database — the one to check a fresh container against
curl localhost:8000/health

# how many notes does each tag have?  (the GROUP BY query)
curl localhost:8000/students/1/tags

# every note associated with one tag
curl "localhost:8000/students/1/notes?tag=sql"

# a tag that labels no notes: an empty list and a 200, not a 404
curl "localhost:8000/students/1/notes?tag=review"

# write a note and its tags as one operation
curl -X POST localhost:8000/notebooks/1/notes \
  -H 'content-type: application/json' \
  -d '{"title": "Window functions", "body": "Not on the midterm.", "tag_ids": [6]}'

# deleting a notebook that still holds notes is refused, with 409
curl -i -X DELETE localhost:8000/notebooks/1
```

## The endpoints

| Method and path | What it does | Failures |
|---|---|---|
| `GET /` | what this service is | — |
| `GET /health` | is the process running (no database) | — |
| `POST /students` | create an account and its settings row | 409 if the email is in use |
| `GET /students/{id}` | read one account | 404 |
| `GET /students/{id}/settings` | theme, default notebook, list density | 404 |
| `PUT /students/{id}/settings` | replace all three | 404, 400 for an unknown notebook |
| `POST /students/{id}/notebooks` | start a notebook | 404, 409 for a repeated name |
| `GET /students/{id}/notebooks` | notebooks with note counts | 404 |
| `DELETE /notebooks/{id}` | delete a notebook | 404, **409 while it holds notes** |
| `POST /notebooks/{id}/notes` | write a note with its tags | 404, 400 for an unknown tag id |
| `GET /notes/{id}` | read one note | 404 |
| `PATCH /notes/{id}` | replace the body; sets `updated_at` to the current time | 404 |
| `GET /students/{id}/notes` | this student's notes; `?tag=` filters | 404 for an unknown student |
| `POST /students/{id}/tags` | create a tag | 404, 409 for a repeated name |
| `GET /students/{id}/tags` | notes per tag, unused tags included | 404 |
| `POST /notes/{id}/tags/{tag_id}` | label a note; repeating it is not an error | 404 |

## The sample data

Three students, seven notebooks, seventeen notes, ten tags and twenty-six
note-tag pairs. The rows are chosen rather than generated, and between them they
cover the cases the queries have to handle:

- a notebook holding no notes, so a `LEFT JOIN` count of 0 is visible
- a note whose body has not been written yet, so `NULL` is visible
- a tag that labels no notes, for the same reason
- a student who has chosen no default notebook
- text outside plain ASCII
- two students with tags of the same name, so per-student tag scoping is visible
- tag counts of 8, 4, 3, 3, 2, 1 and 0, so a `GROUP BY` result is worth reading

The notes are dated across the Fall 2026 term.

## Building the image

```bash
docker build -t course-notebook .
docker run -p 8000:8000 course-notebook
curl localhost:8000/health
```

Only `/health`, `/`, `/docs` and `/openapi.json` answer there. `.dockerignore`
keeps `*.db` out of the image, so the container has no database and every route
that reads a table fails. That is the intended state at the end of 10.0; 10.1 gives the container a
database, in a second container, running PostgreSQL.

The Dockerfile pins `uv` to a complete version (`0.12.1`), so that tag keeps
identifying the same image contents. `python:3.12-slim` names a series and can
change. Check both before the term, and record a digest if the image contents
have to stay exact.

If you change a dependency in `pyproject.toml`, run `uv lock` and commit the
result. `uv sync --locked` in the Dockerfile fails otherwise, which is the
intended behavior: it reports that the lock file needs updating.
