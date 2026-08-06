"""Every route in app/main.py, including the paths that do not return 200.

4.3 makes the point that testing only valid requests leaves the validation and
error paths unchecked, so each failure the design document describes has a test
here as well.

SQLITE-SPECIFIC: this file is part of the 10.1 migration.

These tests import ``sqlite3``, catch ``sqlite3.IntegrityError``, and assert on
SQLite behavior such as ``PRAGMA foreign_keys`` and text timestamps. They change
when ``db/`` changes. A migration that edits only ``db/`` and ``app/`` leaves a
test suite that either fails for SQLite reasons or keeps testing behavior the
application no longer has.
"""

from conftest import ANA, ANA_ICS603, ANA_READING_GROUP, MARCUS, NOELANI

# ---------------------------------------------------------------------------
# Routes that answer without a database
# ---------------------------------------------------------------------------


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "Course Notebook"


def test_health(client):
    """The endpoint 10.0 checks a container against, because a container built
    from this Dockerfile has no database file in it."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_docs_are_served(client):
    assert client.get("/openapi.json").status_code == 200


# ---------------------------------------------------------------------------
# Students and settings
# ---------------------------------------------------------------------------


def test_read_student(client):
    response = client.get("/students/{}".format(ANA))
    assert response.status_code == 200
    assert response.json()["email"] == "ana.kealoha@hawaii.edu"


def test_read_student_that_does_not_exist(client):
    assert client.get("/students/9999").status_code == 404


def test_read_student_with_a_path_value_that_is_not_a_number(client):
    """FastAPI converts the path value before the route function runs."""
    assert client.get("/students/ana").status_code == 422


def test_create_student(client):
    response = client.post(
        "/students",
        json={
            "name": "Kai Nakamura",
            "email": "kai.nakamura@hawaii.edu",
            "theme": "light",
            "compact_view": True,
        },
    )
    assert response.status_code == 201
    student_id = response.json()["id"]

    settings = client.get("/students/{}/settings".format(student_id))
    assert settings.status_code == 200
    assert settings.json() == {
        "theme": "light",
        "default_notebook_id": None,
        "default_notebook_name": None,
        "compact_view": True,
    }


def test_create_student_with_an_email_already_in_use(client):
    response = client.post(
        "/students", json={"name": "Someone Else", "email": "ana.kealoha@hawaii.edu"}
    )
    assert response.status_code == 409


def test_create_student_with_an_empty_name(client):
    response = client.post("/students", json={"name": "", "email": "x@hawaii.edu"})
    assert response.status_code == 422


def test_read_settings_names_the_default_notebook(client):
    response = client.get("/students/{}/settings".format(ANA))
    assert response.status_code == 200
    assert response.json() == {
        "theme": "dark",
        "default_notebook_id": ANA_ICS603,
        "default_notebook_name": "ICS 603 Building LLM Applications",
        "compact_view": True,
    }


def test_read_settings_when_no_default_notebook_is_chosen(client):
    response = client.get("/students/{}/settings".format(NOELANI))
    assert response.json()["default_notebook_id"] is None
    assert response.json()["default_notebook_name"] is None


def test_replace_settings(client):
    response = client.put(
        "/students/{}/settings".format(ANA),
        json={"theme": "light", "default_notebook_id": None, "compact_view": False},
    )
    assert response.status_code == 200
    assert response.json()["theme"] == "light"
    assert response.json()["default_notebook_name"] is None


def test_replace_settings_with_a_theme_the_api_does_not_offer(client):
    """The Literal on the request model rejects it before any SQL runs, so this
    is a 422 rather than the 400 a rejected CHECK constraint would give."""
    response = client.put(
        "/students/{}/settings".format(ANA),
        json={"theme": "neon", "default_notebook_id": None, "compact_view": False},
    )
    assert response.status_code == 422


def test_replace_settings_with_a_notebook_that_does_not_exist(client):
    response = client.put(
        "/students/{}/settings".format(ANA),
        json={"theme": "dark", "default_notebook_id": 9999, "compact_view": False},
    )
    assert response.status_code == 400


def test_replace_settings_for_a_student_that_does_not_exist(client):
    response = client.put(
        "/students/9999/settings",
        json={"theme": "dark", "default_notebook_id": None, "compact_view": False},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------


def test_list_notebooks_with_note_counts(client):
    response = client.get("/students/{}/notebooks".format(ANA))
    assert response.status_code == 200
    assert response.json() == [
        {"id": 3, "name": "ICS 601 Applied Industry Seminar", "note_count": 2},
        {"id": 1, "name": "ICS 603 Building LLM Applications", "note_count": 8},
        {"id": 2, "name": "ICS 635 Applied Machine Learning", "note_count": 3},
        {"id": 4, "name": "Reading group", "note_count": 0},
    ]


def test_list_notebooks_for_a_student_that_does_not_exist(client):
    """404, not an empty list. "No such student" and "this student has no
    notebooks" are different answers."""
    assert client.get("/students/9999/notebooks").status_code == 404


def test_create_notebook(client):
    response = client.post(
        "/students/{}/notebooks".format(ANA), json={"name": "ICS 605 Deep Learning"}
    )
    assert response.status_code == 201
    assert response.json()["student_id"] == ANA
    assert response.json()["created_at"].endswith("Z")


def test_create_notebook_with_a_name_this_student_already_uses(client):
    response = client.post(
        "/students/{}/notebooks".format(ANA),
        json={"name": "ICS 603 Building LLM Applications"},
    )
    assert response.status_code == 409


def test_create_notebook_with_a_name_another_student_uses(client):
    """The constraint is UNIQUE (student_id, name), so this is allowed."""
    response = client.post(
        "/students/{}/notebooks".format(NOELANI),
        json={"name": "ICS 603 Building LLM Applications"},
    )
    assert response.status_code == 201


def test_delete_an_empty_notebook(client):
    response = client.delete("/notebooks/{}".format(ANA_READING_GROUP))
    assert response.status_code == 204
    assert len(client.get("/students/{}/notebooks".format(ANA)).json()) == 3


def test_delete_a_notebook_that_still_holds_notes(client):
    """409, and the notebook and its notes are still there."""
    response = client.delete("/notebooks/{}".format(ANA_ICS603))
    assert response.status_code == 409
    assert "still holds notes" in response.json()["detail"]
    assert len(client.get("/students/{}/notebooks".format(ANA)).json()) == 4


def test_delete_a_notebook_that_does_not_exist(client):
    assert client.delete("/notebooks/9999").status_code == 404


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def test_read_note(client):
    response = client.get("/notes/1")
    assert response.status_code == 200
    assert response.json()["title"] == (
        "Parameterized queries are the only safe way to pass user text"
    )


def test_read_a_note_whose_body_is_not_written_yet(client):
    response = client.get("/notes/8")
    assert response.status_code == 200
    assert response.json()["body"] is None


def test_read_a_note_that_does_not_exist(client):
    assert client.get("/notes/9999").status_code == 404


def test_create_note_with_tags(client):
    response = client.post(
        "/notebooks/{}/notes".format(ANA_ICS603),
        json={
            "title": "EXPLAIN QUERY PLAN is evidence, not proof",
            "body": "With a few dozen rows SQLite may correctly scan a table "
            "that an index would cover, so the plan describes this data size.",
            "tag_ids": [6],  # Ana's "sql"
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]
    assert response.json()["created_at"] == response.json()["updated_at"]

    tagged = client.get("/students/{}/notes".format(ANA), params={"tag": "sql"})
    assert note_id in [note["id"] for note in tagged.json()]


def test_create_note_without_a_body(client):
    response = client.post(
        "/notebooks/{}/notes".format(ANA_ICS603), json={"title": "Write this up later"}
    )
    assert response.status_code == 201
    assert response.json()["body"] is None


def test_create_note_in_a_notebook_that_does_not_exist(client):
    response = client.post("/notebooks/9999/notes", json={"title": "Nowhere"})
    assert response.status_code == 404


def test_create_note_with_a_tag_that_does_not_exist(client):
    """400, and no note is stored: the whole operation is one transaction."""
    before = len(client.get("/students/{}/notes".format(ANA)).json())
    response = client.post(
        "/notebooks/{}/notes".format(ANA_ICS603),
        json={"title": "Half a write", "tag_ids": [9999]},
    )
    assert response.status_code == 400
    assert len(client.get("/students/{}/notes".format(ANA)).json()) == before


def test_create_note_with_an_empty_title(client):
    response = client.post("/notebooks/{}/notes".format(ANA_ICS603), json={"title": ""})
    assert response.status_code == 422


def test_update_a_note_body(client):
    before = client.get("/notes/1").json()
    response = client.patch("/notes/1", json={"body": "Rewritten during review."})
    assert response.status_code == 200
    assert response.json()["body"] == "Rewritten during review."
    assert response.json()["created_at"] == before["created_at"]
    # the update statement set updated_at. It is not compared with the seeded value: the sample
    # rows are dated during the Fall 2026 term.
    assert response.json()["updated_at"] != before["updated_at"]


def test_update_a_note_that_does_not_exist(client):
    assert client.patch("/notes/9999", json={"body": "nothing"}).status_code == 404


def test_list_notes(client):
    response = client.get("/students/{}/notes".format(ANA))
    assert response.status_code == 200
    assert len(response.json()) == 13
    assert response.json()[0]["title"] == "Week 12 lecture — write this up"


def test_list_notes_filtered_by_tag(client):
    response = client.get("/students/{}/notes".format(ANA), params={"tag": "sql"})
    assert response.status_code == 200
    assert [note["id"] for note in response.json()] == [3, 2, 1]


def test_list_notes_for_a_tag_no_note_uses(client):
    """200 and an empty list. Finding nothing is an answer, not a failure."""
    response = client.get("/students/{}/notes".format(ANA), params={"tag": "review"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_notes_for_a_tag_that_does_not_exist(client):
    response = client.get("/students/{}/notes".format(ANA), params={"tag": "nothing"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_notes_for_a_student_that_does_not_exist(client):
    assert client.get("/students/9999/notes").status_code == 404


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_list_tags_with_counts(client):
    response = client.get("/students/{}/tags".format(ANA))
    assert response.status_code == 200
    assert response.json() == [
        {"id": 2, "name": "exam", "note_count": 8},
        {"id": 4, "name": "reading", "note_count": 4},
        {"id": 6, "name": "sql", "note_count": 3},
        {"id": 7, "name": "todo", "note_count": 3},
        {"id": 1, "name": "docker", "note_count": 2},
        {"id": 3, "name": "lab", "note_count": 1},
        {"id": 5, "name": "review", "note_count": 0},
    ]


def test_list_tags_counts_only_this_students_notes(client):
    response = client.get("/students/{}/tags".format(MARCUS))
    assert response.json() == [
        {"id": 8, "name": "docker", "note_count": 2},
        {"id": 9, "name": "exam", "note_count": 2},
    ]


def test_create_tag(client):
    response = client.post("/students/{}/tags".format(ANA), json={"name": "project"})
    assert response.status_code == 201
    assert response.json()["student_id"] == ANA


def test_create_tag_with_a_name_this_student_already_uses(client):
    response = client.post("/students/{}/tags".format(ANA), json={"name": "exam"})
    assert response.status_code == 409


def test_create_tag_with_a_name_another_student_uses(client):
    response = client.post("/students/{}/tags".format(NOELANI), json={"name": "exam"})
    assert response.status_code == 201


def test_attach_a_tag_twice(client):
    """Note 11 carries only 'lab'. The second call is not an error and changes
    nothing."""
    exam = 2
    first = client.post("/notes/11/tags/{}".format(exam))
    second = client.post("/notes/11/tags/{}".format(exam))

    assert first.status_code == 200 and first.json() == {"attached": True}
    assert second.status_code == 200 and second.json() == {"attached": False}

    counts = client.get("/students/{}/tags".format(ANA)).json()
    assert counts[0] == {"id": 2, "name": "exam", "note_count": 9}


def test_attach_a_tag_to_a_note_that_does_not_exist(client):
    assert client.post("/notes/9999/tags/2").status_code == 404


def test_attach_a_tag_that_does_not_exist(client):
    assert client.post("/notes/1/tags/9999").status_code == 404
