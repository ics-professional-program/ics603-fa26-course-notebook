# Course Notebook — implementation plan

The plan session 5.0's workflow produces from `docs/design.md`: what gets built,
in what order, and what each file is responsible for. Each step ends at something
that can be run or read, so a step that went wrong is found at that step rather
than three steps later.

## Build order

| # | Step | Done when |
|---|---|---|
| 1 | `db/schema.sql` — the six tables, their constraints, and two indexes | the file reads correctly against the 9.2 Step 4 checklist, before any data exists |
| 2 | `db/queries.py` — `connect()` only | `connect()` opens a database and `PRAGMA foreign_keys` reports 1 |
| 3 | `db/seed.py` — reset, create tables, load sample rows | the script runs twice in a row without error and the row counts match what was written |
| 4 | `tests/test_schema.py` — constraint checks | each of the three violations from 9.2 Step 4 raises `sqlite3.IntegrityError`, and the `ON DELETE` actions behave as `docs/design.md` says |
| 5 | `db/queries.py` — the rest of the functions | every function returns the rows predicted from the seeded data |
| 6 | `tests/test_queries.py` — one test per function | the predictions are written down as assertions rather than checked by eye |
| 7 | `app/main.py` — the FastAPI application | `GET /health` answers with no database; every other route answers against the seeded database |
| 8 | `tests/test_app.py` — endpoint checks | each route returns the status code the design document says, including the failure paths |
| 9 | `pyproject.toml`, `Dockerfile`, `.dockerignore` | `uv lock` produces a lock file and `docker build` produces an image |
| 10 | `README.md` | states what the application is, how to run it, and which constructs 10.1 migrates |

Steps 1 and 2 come before step 3 because a constraint added after rows exist may
be rejected by the rows already stored. Step 4 comes before step 5 for the same
reason: a query verified against a schema whose constraints do not work is
verified against nothing.

## What each file is responsible for

### `db/schema.sql`

The six `CREATE TABLE` statements and the two `CREATE INDEX` statements, and
nothing else. No rows. It is read by `db/seed.py` through
`conn.executescript()`, which is why it holds several statements in one file.

It also contains the two comments 9.2 Step 7 asks for: which relationship kind was
chosen for each pair, and what format the date and time columns use.

Every construct PostgreSQL rejects is marked `SQLITE-SPECIFIC` with the
PostgreSQL form named in the comment, so 10.1 can be rehearsed from the file.

### `db/queries.py`

`connect()`, plus one function per question the application asks the database.
Rules that hold for all of them:

- Every value reaches SQLite as a `?` parameter. No SQL string is built by
  formatting.
- A function that changes more than one table wraps its statements in `with
  conn:` so the whole operation commits or none of it does.
- A function that changes exactly one table also uses `with conn:`, so the
  caller never has to remember to commit.
- Each function has a docstring that names the question it answers and says what
  it returns, including what it returns when there is no row.
- Rows come back as tuples in the order the `SELECT` lists them, which is the
  default `sqlite3` behavior 9.0 and 9.1 use.

`connect()` is deliberately the only place a connection is opened. 10.1 changes
one function rather than every call site.

### `db/seed.py`

Deletes the database file, creates the tables from `db/schema.sql`, and loads the
sample rows in one transaction. Safe to run repeatedly — that is the point of
deleting the file first.

The sample rows are three students, seven notebooks, seventeen notes, ten tags
and the pairs that connect them. They are chosen, not generated: one notebook with no
notes, one note whose body is absent, one tag with no notes, one student who has
chosen no default notebook, text outside plain ASCII, and tag counts that differ
so a `GROUP BY` result is worth reading.

Timestamps are supplied explicitly here rather than left to the column default,
because seeded data has to be spread across a term for the "recently changed"
ordering to mean anything.

`seed_database(conn)` is a function, not top-level code, so the tests can load
the same rows into a temporary database.

### `app/main.py`

The FastAPI application, in the form 4.3 teaches: Pydantic models for request and
response bodies, `response_model` on each route, `HTTPException` with a status
code chosen for the situation.

It opens one connection per request through a dependency and closes it in a
`finally` block. SQLite connections are not shared between threads, and FastAPI
runs synchronous route functions in a thread pool, so a single module-level
connection would be wrong.

Route functions do no SQL. They call `db/queries.py`, translate its return values
into response models, and turn a missing row into `404`, a rejected foreign key
into `404`, and a rejected delete into `409`.

`GET /health` does not access the database. 10.0 needs an endpoint that answers inside a
container that has no database file.

### `tests/`

Three files, split by what they check:

- `test_schema.py` — the constraints. Each of the three violations 9.2 Step 4
  lists, plus the `ON DELETE` actions from `docs/design.md` and the presence of
  the two indexes.
- `test_queries.py` — one test per function in `db/queries.py`, asserting the
  exact rows the seeded data produces.
- `test_app.py` — one test per route, including each failure path that returns
  something other than `200`.

`conftest.py` builds a fresh database in a temporary directory for each test
module and points the application at it.

### `pyproject.toml`, `Dockerfile`, `.dockerignore`

The `uv` project definition and the image, following the Dockerfile pattern from
10.0: copy `pyproject.toml` and `uv.lock` first, install, then copy the code, so
a code edit does not reinstall every package.

`.dockerignore` excludes `*.db`, which is what makes `GET /health` the endpoint
that has to work in a container.

## Things that are settled before coding, not during

- The relationship kinds. Decided in `docs/design.md` and given to the agent as
  statements, not left for it to infer from the spec.
- The `ON DELETE` action on every foreign key.
- The date format and its time zone.
- Which constructs stay SQLite-specific. This application is the source material
  for 10.1's migration, so portable SQL would be the wrong output here.
