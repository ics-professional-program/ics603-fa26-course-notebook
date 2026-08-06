"""Course Notebook — the FastAPI application.

The HTTP boundary from 4.3 placed over the database from 9.2: Pydantic models
for request and response bodies, ``response_model`` on every route, and
``HTTPException`` with a status code chosen for the situation.

Route functions contain no SQL. They call ``db/queries.py``, turn its return
values into response models, and translate its failures:

===============================  =================================
Situation                        Status
===============================  =================================
no row with that id              ``404 Not Found``
a name or address already used   ``409 Conflict``
a notebook that still has notes  ``409 Conflict``
a tag id that does not exist     ``400 Bad Request``
request body fails validation    ``422`` (FastAPI produces it)
===============================  =================================

``GET /`` and ``GET /health`` answer without touching the database. Session 10.0
excludes ``*.db`` from the image with ``.dockerignore``, so a container built
from this application starts with no database file and those two routes plus
``/docs`` are what a first ``docker run`` can be checked against.

One connection is opened per request and closed when the request ends. SQLite
connections are not shared between threads, and FastAPI runs synchronous route
functions in a thread pool, so a single connection held at module level would be
wrong.
"""

import sqlite3
from collections.abc import Iterator
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

from db import queries

app = FastAPI(
    title="Course Notebook",
    description=(
        "A study tool that lets a student collect class notes, organize them, "
        "and find them again later. The ICS 603 reference application for "
        "sessions 9.2, 10.0 and 10.1."
    ),
    version="1.0.0",
)


def get_conn() -> Iterator[sqlite3.Connection]:
    """Open one connection for this request and close it when the request ends.

    10.1 replaces the call inside ``queries.connect()`` with a psycopg
    connection. Nothing in this file changes.
    """
    conn = queries.connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------

Theme = Literal["light", "dark", "system"]


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    theme: Theme = "system"
    compact_view: bool = False


class StudentOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: str


class SettingsIn(BaseModel):
    theme: Theme
    default_notebook_id: int | None = None
    compact_view: bool = False


class SettingsOut(BaseModel):
    theme: Theme
    default_notebook_id: int | None
    default_notebook_name: str | None
    compact_view: bool


class NotebookIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NotebookOut(BaseModel):
    id: int
    student_id: int
    name: str
    created_at: str


class NotebookSummary(BaseModel):
    id: int
    name: str
    note_count: int


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # A note may be saved with only a title; the body is written later.
    body: str | None = None
    tag_ids: list[int] = Field(default_factory=list)


class NoteBodyIn(BaseModel):
    body: str


class NoteOut(BaseModel):
    id: int
    notebook_id: int
    title: str
    body: str | None
    created_at: str
    updated_at: str


class NoteListItem(BaseModel):
    id: int
    title: str
    notebook_name: str


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class TagOut(BaseModel):
    id: int
    student_id: int
    name: str


class TagCount(BaseModel):
    id: int
    name: str
    note_count: int


class AttachResult(BaseModel):
    attached: bool


# ---------------------------------------------------------------------------
# Helpers used by several routes
# ---------------------------------------------------------------------------


def _require_student(conn: sqlite3.Connection, student_id: int) -> None:
    """Raise 404 if no student has this id.

    Called before the reads that would otherwise return an empty list for a
    student who does not exist, which is a different answer from "this student
    has nothing yet".
    """
    if queries.get_student(conn, student_id) is None:
        raise HTTPException(status_code=404, detail="No student with that id.")


def _note_or_404(conn: sqlite3.Connection, note_id: int) -> NoteOut:
    row = queries.get_note(conn, note_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No note with that id.")
    return NoteOut(
        id=row[0],
        notebook_id=row[1],
        title=row[2],
        body=row[3],
        created_at=row[4],
        updated_at=row[5],
    )


# ---------------------------------------------------------------------------
# Routes that do not touch the database
# ---------------------------------------------------------------------------


@app.get("/")
def read_root():
    """What this service is. Answers without a database, as /health does."""
    return {
        "name": "Course Notebook",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health_check():
    """Is the process running?

    Deliberately does not open a connection. 10.0 builds an image with no
    database file in it, and this is the endpoint that still answers there.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Students and settings
# ---------------------------------------------------------------------------


@app.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentIn, conn: sqlite3.Connection = Depends(get_conn)):
    """Create an account and its one settings row."""
    try:
        student_id = queries.create_student(
            conn,
            name=payload.name,
            email=payload.email,
            theme=payload.theme,
            compact_view=payload.compact_view,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="That email address already has an account."
        )

    row = queries.get_student(conn, student_id)
    return StudentOut(id=row[0], name=row[1], email=row[2], created_at=row[3])


@app.get("/students/{student_id}", response_model=StudentOut)
def read_student(student_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Read one account."""
    row = queries.get_student(conn, student_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No student with that id.")
    return StudentOut(id=row[0], name=row[1], email=row[2], created_at=row[3])


@app.get("/students/{student_id}/settings", response_model=SettingsOut)
def read_settings(student_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Read a student's theme, default notebook and list density.

    A student with no settings row is a 404. The schema permits that state — a
    `UNIQUE` foreign key allows at most one settings row, never exactly one — and
    the application treats it as an error because `create_student()` is supposed
    to have made the row.
    """
    row = queries.get_student_settings(conn, student_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No settings for that student.")
    return SettingsOut(
        theme=row[0],
        default_notebook_id=row[1],
        default_notebook_name=row[2],
        compact_view=bool(row[3]),
    )


@app.put("/students/{student_id}/settings", response_model=SettingsOut)
def replace_settings(
    student_id: int,
    payload: SettingsIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Replace all three settings values."""
    try:
        changed = queries.update_settings(
            conn,
            student_id=student_id,
            theme=payload.theme,
            default_notebook_id=payload.default_notebook_id,
            compact_view=payload.compact_view,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=400, detail="No notebook with that default_notebook_id."
        )

    if changed == 0:
        raise HTTPException(status_code=404, detail="No settings for that student.")
    return read_settings(student_id, conn)


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


@app.post(
    "/students/{student_id}/notebooks",
    response_model=NotebookOut,
    status_code=status.HTTP_201_CREATED,
)
def create_notebook(
    student_id: int,
    payload: NotebookIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Start a notebook for this student."""
    _require_student(conn, student_id)
    try:
        notebook_id = queries.create_notebook(conn, student_id, payload.name)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="This student already has a notebook with that name."
        )

    row = queries.get_notebook(conn, notebook_id)
    return NotebookOut(id=row[0], student_id=row[1], name=row[2], created_at=row[3])


@app.get("/students/{student_id}/notebooks", response_model=list[NotebookSummary])
def list_notebooks(student_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """List this student's notebooks with the number of notes each one holds.

    A notebook holding no notes appears with a count of 0; it is not left out.
    """
    _require_student(conn, student_id)
    return [
        NotebookSummary(id=row[0], name=row[1], note_count=row[2])
        for row in queries.list_notebooks(conn, student_id)
    ]


@app.delete("/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(notebook_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Delete a notebook.

    409 when the notebook still holds notes. `notes.notebook_id` is declared
    `ON DELETE RESTRICT`, so the database refuses rather than deleting a term of
    notes along with their container.
    """
    try:
        deleted = queries.delete_notebook(conn, notebook_id)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This notebook still holds notes. Move or delete them before "
                "deleting the notebook."
            ),
        )

    if deleted == 0:
        raise HTTPException(status_code=404, detail="No notebook with that id.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@app.post(
    "/notebooks/{notebook_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    notebook_id: int,
    payload: NoteIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Write a note into this notebook, with its tags, as one operation.

    Either the note and all of its tags are stored, or nothing is. A repeated or
    unknown tag id is a 400 and leaves no note behind.
    """
    if queries.get_notebook(conn, notebook_id) is None:
        raise HTTPException(status_code=404, detail="No notebook with that id.")

    try:
        note_id = queries.add_note_with_tags(
            conn,
            notebook_id=notebook_id,
            title=payload.title,
            body=payload.body,
            tag_ids=payload.tag_ids,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="tag_ids must name existing tags, and must not repeat one.",
        )

    return _note_or_404(conn, note_id)


@app.get("/notes/{note_id}", response_model=NoteOut)
def read_note(note_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Read one note. `body` is null for a note whose body is not written yet."""
    return _note_or_404(conn, note_id)


@app.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    payload: NoteBodyIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Replace a note's body. `updated_at` moves; `created_at` does not."""
    if queries.update_note_body(conn, note_id, payload.body) == 0:
        raise HTTPException(status_code=404, detail="No note with that id.")
    return _note_or_404(conn, note_id)


@app.get("/students/{student_id}/notes", response_model=list[NoteListItem])
def list_notes(
    student_id: int,
    tag: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """List this student's notes, or only those associated with `?tag=`.

    A tag that labels no notes, and a tag name that does not exist, both give an
    empty list and a 200. Finding nothing is an answer, not a failure.
    """
    _require_student(conn, student_id)

    if tag is None:
        return [
            NoteListItem(id=row[0], title=row[1], notebook_name=row[2])
            for row in queries.notes_with_notebook_name(conn, student_id)
        ]

    return [
        NoteListItem(id=row[0], title=row[1], notebook_name=row[2])
        for row in queries.notes_with_tag(conn, student_id, tag)
    ]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@app.post(
    "/students/{student_id}/tags",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    student_id: int,
    payload: TagIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Create a label for this student. Another student may use the same name."""
    _require_student(conn, student_id)
    try:
        tag_id = queries.create_tag(conn, student_id, payload.name)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="This student already has a tag with that name."
        )
    return TagOut(id=tag_id, student_id=student_id, name=payload.name)


@app.get("/students/{student_id}/tags", response_model=list[TagCount])
def list_tags(student_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """How many notes is each of this student's tags associated with?

    Tags that label no notes appear with a count of 0.
    """
    _require_student(conn, student_id)
    return [
        TagCount(id=row[0], name=row[1], note_count=row[2])
        for row in queries.note_count_per_tag(conn, student_id)
    ]


@app.post("/notes/{note_id}/tags/{tag_id}", response_model=AttachResult)
def attach_tag(
    note_id: int,
    tag_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Put a tag on a note.

    Applying a tag the note already carries is not an error; `attached` is false
    and nothing changed.
    """
    try:
        attached = queries.attach_tag_to_note(conn, note_id, tag_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=404, detail="No note or no tag with that id.")
    return AttachResult(attached=attached)
