# Course Notebook — design document

This is the design document that session 9.2 hands to students who do not have a
usable spec of their own. Version 1 of it is reproduced below exactly as 9.2
prints it. Everything after it is the work 9.2 asks the student to do: read the
spec, find the questions it does not answer, decide each one, and write the
decision down with its reason.

Session 9.2, Step 1 says "read `docs/design.md`". This file is that file.

## Contents

1. [The spec (version 1, from 9.2)](#the-spec-version-1-from-92)
2. [Brainstorm: questions the spec does not answer](#brainstorm-questions-the-spec-does-not-answer)
3. [Entities (Step 1)](#entities-step-1)
4. [Relationships (Step 2)](#relationships-step-2)
5. [Storage conventions](#storage-conventions)
6. [Schema review against the Step 4 checklist](#schema-review-against-the-step-4-checklist)
7. [Operations the application runs (Step 6)](#operations-the-application-runs-step-6)
8. [Known limits of version 1](#known-limits-of-version-1)
9. [What 10.0, 10.1 and 11.1 need from this schema](#what-100-101-and-111-need-from-this-schema)

---

## The spec (version 1, from 9.2)

```text
Course Notebook — design document (version 1)

Purpose
  A study tool that lets a student collect class notes, organize them, and find
  them again later.

Users
  Each account represents one student. Accounts are not shared.

Features
  - A student writes notes. Every note has a title and a body.
  - Notes are collected in notebooks, usually one notebook per course. A note
    belongs to one notebook. A notebook holds many notes.
  - A student labels notes with tags such as "exam", "lab", or "reading". A note
    can be associated with several tags, and the same tag is used for many notes.
  - Each student sets a display theme and a default notebook. These settings
    exist once per student.
  - Every note records when it was created and when it was last changed.
  - The student can list all notes associated with a chosen tag, and can see how
    many notes each tag is associated with.

Data
  Notes are typed by the student. Nothing is imported from another system, and
  no data is shared between accounts.

What can go wrong
  A student deletes a notebook that still holds notes. A student applies the same
  tag twice to one note. A student searches for a tag that no note uses.

Out of scope for version 1
  Sharing between students, file attachments, comments, and search by meaning.
```

---

## Brainstorm: questions the spec does not answer

The spec states behavior and leaves the storage decisions open. Below is every
question that had to be settled before any SQL could be written, each with the
decision taken and the reason for it. A decision recorded here is a decision the
schema then enforces, so this section and `db/schema.sql` have to agree.

### D1. What happens when a notebook that still holds notes is deleted?

The spec names this as a thing that goes wrong but does not say what should
happen. There are three possible answers: reject the delete, delete the notes
with the notebook (`ON DELETE CASCADE`), or leave the notes without a notebook
(`ON DELETE SET NULL`).

**Decision: reject the delete.** `notes.notebook_id` is declared
`REFERENCES notebooks(id) ON DELETE RESTRICT`.

**Reason:** the notes are the data the student typed; the notebook is only a
container for them. A delete that silently destroys a term of notes is a worse
outcome than a delete that fails and says why. The application must first move
or delete the notes, which is an action the student takes on purpose. The third
option is ruled out by D3.

The application turns the rejection into an HTTP `409 Conflict` with a message
that says the notebook still holds notes.

### D2. Are tag names global, or does each student have their own tags?

The example schema in 9.2, Step 2 shows `tags(id, name TEXT NOT NULL UNIQUE)` —
one global list of tag names shared by everyone. The spec says the opposite about
the data: "no data is shared between accounts."

**Decision: tags belong to a student.** `tags` has a `student_id` foreign key and
`UNIQUE (student_id, name)` instead of `UNIQUE (name)`.

**Reason:** three things go wrong with one global tag list. The count query
("how many notes does each tag have") would count other students' notes unless
every query filters by student anyway. Renaming a tag would rename it for
everyone. And the tag list a student sees would grow with every name any other
student ever invented. `UNIQUE (student_id, name)` gives each student one tag
named `exam` and permits a different student to have their own row also named
`exam`.

The cost is that the tag table has more rows than a global list would, and that
every tag query carries a `student_id` filter. Both are acceptable at this size.

### D3. Can a note exist with no notebook?

**Decision: no.** `notes.notebook_id` is `NOT NULL`.

**Reason:** the spec sentence is unconditional — "A note belongs to one
notebook." Nothing in version 1 describes a note that is not in a notebook, and
`NOT NULL` is what makes "belongs to one" a rule the database keeps rather than a
sentence in a document. A consequence worth stating: creating the first note
requires creating a notebook first, so the application creates a notebook when it
creates the account.

### D4. Is a note's body required?

**Decision: no.** `notes.title` is `NOT NULL`; `notes.body` permits `NULL`.

**Reason:** this is the one place where the literal spec sentence ("Every note
has a title and a body") is not followed, so the reason has to be good. A note
typed during class often starts as a title with the body added later, and that
half-written state is a real one the application has to store. `NULL` records
that the body is absent, which is different from an empty body — 9.0 makes that
distinction and `NOT NULL` does not reject `''`. It also gives the sample data a
genuinely absent optional value, which 9.2 Step 5 asks for.

If a later version decides that a note must be finished before it is saved, that
rule belongs in the application, not in the column, because "finished" is not
"present".

### D5. What happens to the default notebook when that notebook is deleted?

**Decision:** `student_settings.default_notebook_id` permits `NULL` and is
declared `REFERENCES notebooks(id) ON DELETE SET NULL`. `NULL` means the student
has not chosen a default; the application then asks which notebook to write into
instead of choosing one.

**Reason:** a notebook holding no notes can be deleted (D1 only blocks a notebook
that holds notes), and that notebook may be somebody's default. Blocking the
delete because of a settings row would be a surprising failure, and picking a
replacement notebook automatically would silently send the next note somewhere
the student did not choose. `SET NULL` returns the student to the state they were
in before they chose a default, which is a state the application already handles.

### D6. How is "last changed" maintained?

**Decision:** the application maintains it. `notes.updated_at` is `NOT NULL` with
a column `DEFAULT` that fills in the current UTC time on insert, and every
statement that changes a note also sets `updated_at`. There is no trigger.

**Reason:** three mechanisms were available — a database trigger, a column
default, or application code. A trigger works but hides the behavior in a place
students do not read, and 9.0 and 9.1 never introduce triggers. A default alone
covers the insert but not the update. So the default covers the insert and each
`UPDATE` statement sets the column, which keeps the whole rule visible in the two
files that a reader of this project opens: `db/schema.sql` and `db/queries.py`.

`created_at` is set the same way and never changed after insert.

### D7. Which time format, and which time zone?

**Decision:** ISO 8601 text in UTC, to the second, with the `Z` suffix:
`2026-10-22T14:30:00Z`. One format in every column in every table.

**Reason:** SQLite has no date or time storage class, so a format is an
application convention rather than something the database provides. Text in this
format sorts correctly as text, which is only true if every value uses the same
field order, the same precision, and the same time zone — hence UTC and hence a
fixed number of digits. This is checklist row 9 from 9.2, Step 4, and the choice
is recorded in a comment at the top of `db/schema.sql` as that row requires.

### D8. Are two notebooks allowed to have the same name?

**Decision:** not for the same student. `notebooks` has `UNIQUE (student_id,
name)`. Two different students may each have a notebook named `ICS 603 Building
LLM Applications`.

**Reason:** the student picks a notebook by name, so two notebooks with the same
name for one student is a mistake rather than a feature — the student cannot tell
them apart. Nothing prevents two different students from choosing the same name,
and nothing should.

### D9. What happens when the same tag is applied to one note twice?

The spec names this as a thing that goes wrong. Two answers are reasonable and
the application uses both, in different places.

**Decision:** the schema always rejects the duplicate — `note_tags` has
`PRIMARY KEY (note_id, tag_id)`, so the pair cannot be stored twice. On top of
that:

- `attach_tag_to_note()`, which is what the "add this tag" button calls, uses
  `INSERT OR IGNORE`. Applying a tag that is already applied changes nothing and
  is not an error. The function returns whether a new pair was stored.
- `add_note_with_tags()`, which creates a note and its tags as one operation,
  uses a plain `INSERT`. A repeated pair in that call is a mistake in the call,
  and the whole operation — the note included — is rolled back.

**Reason:** pressing a button twice is not an error the student should have to
read about. A malformed list of tag ids sent to the create-note operation is a
different situation: 9.2 requires that operation to complete fully or make no
change at all, and quietly discarding part of its input would break that.

### D10. What happens when a note is deleted, or a tag is deleted?

**Decision:** both `note_tags.note_id` and `note_tags.tag_id` are declared
`ON DELETE CASCADE`.

**Reason:** a row in `note_tags` records that one note carries one tag. It is not
data in its own right; without either end it has no meaning and could never be
read again. Deleting a tag removes the labels it applied and leaves every note in
place, which is what deleting a tag means.

### D11. What happens when a student account is deleted?

Deleting an account is not a version 1 feature — the spec does not list it. The
foreign-key action still has to be declared, because checklist row 11 requires
every relationship to state one.

**Decision:** `notebooks.student_id`, `tags.student_id` and
`student_settings.student_id` are all `ON DELETE CASCADE`.

**Reason:** nothing a student owns is shared with another account, so nothing
owned by a deleted account should survive it.

**Stated consequence:** this cascade does not reach the notes. Deleting a student
cascades to their notebooks, and each of those notebooks is protected by D1's
`ON DELETE RESTRICT` on `notes.notebook_id`. So deleting a student who has
written any note fails. That is deliberate and it is tested in
`tests/test_schema.py`. When account deletion is added, it will be one
transaction that deletes the notes, then the notebooks, then the student.

### D12. Does the settings row exist for every student?

**Decision:** the application creates it. `create_student()` inserts the student
row and the settings row in one transaction, and a student without a settings row
is treated as an error by the application (`404` from the settings endpoint).

**Reason:** the schema cannot require it. `UNIQUE` on
`student_settings.student_id` enforces *at most one* settings row per student; a
relational schema has no way to require that a child row exists. 9.2 states this
exactly, and this is where the application takes the rule over.

The one-to-one values live in their own table rather than as extra columns on
`students` because the settings are read on their own — the settings screen — and
are not needed by any query that lists notes.

### D13. Does a note record which student wrote it?

**Decision:** no. `notes` has no `student_id` column. A note's owner is reached
through `notes.notebook_id -> notebooks.student_id`.

**Reason:** storing the owner twice permits the two copies to disagree — a note
whose `student_id` says one student while its notebook belongs to another. The
value is derivable, so it is derived. The cost is that "list this student's
notes" is a join rather than a single-table read, which is the join required by
9.2 Step 6 anyway.

### D14. What does a search for a tag with no notes return?

**Decision:** an empty list, and HTTP `200`. The same applies to a tag name the
student has never created.

**Reason:** finding nothing is a correct answer to a well-formed question, not a
failure. `404` is for a resource that does not exist, and the *search* exists.
The count query is separate and deliberately keeps tags with zero notes in its
result (a `LEFT JOIN` and `COUNT(note_tags.note_id)`), because a student looking
at their tag list wants to see the unused ones.

### D15. Which theme values are allowed?

**Decision:** `'light'`, `'dark'`, `'system'`, enforced with
`CHECK (theme IN ('light', 'dark', 'system'))`.

**Reason:** the spec says a student "sets a display theme" without listing the
values. A free-text column would accept `darkk`. The list is short and stable, so
a `CHECK` is enough and no separate `themes` table is needed — a table with three
never-changing rows would fail checklist row 8.

### D16. Does the junction table need any columns of its own?

**Decision:** no. `note_tags` holds `note_id` and `tag_id` and nothing else.

**Reason:** 9.2 points out that a junction table may carry attributes describing
the pair, and gives `applied_at` as the example. Nothing in version 1 reads or
displays when a tag was applied, and checklist row 8 rules out columns that no
operation needs. If a later version wants "tags I used this week", `applied_at`
goes in `note_tags`, because the value describes the pair and not either side.

---

## Entities (Step 1)

Six tables. 9.2 calls three to six a reasonable size for version 1.

| Table | What it stores | Why version 1 needs it |
|---|---|---|
| `students` | one row per account | every other table hangs off it; the spec says accounts are separate |
| `notebooks` | one row per notebook | notes are collected in notebooks, usually one per course |
| `notes` | one row per note | the thing the application exists to store |
| `tags` | one row per tag name per student | the labels the student searches by |
| `note_tags` | one row per (note, tag) pair | the many-to-many relationship between the two above |
| `student_settings` | one row per student | display theme and default notebook |

Candidates that were considered and left out:

- **`themes`** — a table of three fixed values that never changes per student. A
  `CHECK` constraint holds the same information (D15).
- **`courses`** — the spec says "usually one notebook per course", which
  describes how a student uses notebooks, not a second thing the application
  stores. There is no operation in version 1 that reads a course.

## Relationships (Step 2)

Taken from the sentences in the spec that connect two things, not from comparing
every pair of tables.

| Pair | Kind | How it is stored | Optional? |
|---|---|---|---|
| notebook — notes | one-to-many | `notes.notebook_id` foreign key | no; `NOT NULL` (D3) |
| student — notebooks | one-to-many | `notebooks.student_id` foreign key | no; `NOT NULL` |
| student — tags | one-to-many | `tags.student_id` foreign key | no; `NOT NULL` (D2) |
| notes — tags | many-to-many | junction table `note_tags`, composite primary key | yes; a note may carry no tags |
| student — settings | one-to-one | `student_settings.student_id` foreign key **plus `UNIQUE`** | at most one; the application creates it (D12) |
| settings — default notebook | one-to-one, optional | `student_settings.default_notebook_id` foreign key | yes; `NULL` means not chosen (D5) |

The line 9.2 warns about — "A note can be associated with several tags" — is the
one that produces a `tags TEXT` column holding `'exam,sql'` if it is read
carelessly. It is stored as `note_tags` instead, because the application has to
find notes by tag, count notes per tag, and index the lookup, and a comma-joined
string supports none of those.

## Storage conventions

| Kind of value | Stored as | Note |
|---|---|---|
| generated key | `INTEGER PRIMARY KEY AUTOINCREMENT` | SQLite assigns it; read it back with `cursor.lastrowid` |
| date and time | `TEXT`, ISO 8601, UTC, seconds, `Z` suffix | D7; SQLite has no date type |
| true / false | `INTEGER` 0 or 1 with `CHECK (col IN (0, 1))` | SQLite has no boolean storage class |
| absent value | `NULL` | different from `''`; `NOT NULL` does not reject `''` |

## Schema review against the Step 4 checklist

Run against `db/schema.sql` before any data was loaded, using the checklist from
9.2 Step 4 as written.

| # | Check | Result |
|---|---|---|
| 1 | Every table has a primary key | Pass. Five tables use `INTEGER PRIMARY KEY AUTOINCREMENT`; `note_tags` uses the composite `PRIMARY KEY (note_id, tag_id)`. |
| 2 | Every relationship is a foreign key | Pass. No table stores a parent's name as text. `notes` stores `notebook_id`, not a notebook name; `note_tags` stores `tag_id`, not a tag name. |
| 3 | No column stores a list | Pass. Tags are rows in `note_tags`, not a comma-joined string on `notes` (D2, Step 2). |
| 4 | Required columns are `NOT NULL` | Pass. Every foreign key except `default_notebook_id` is `NOT NULL`; `notes.body` and `default_notebook_id` are the two nullable columns and both are deliberate (D4, D5). |
| 5 | Values that must not repeat use `UNIQUE` | Pass. `students.email`, `notebooks (student_id, name)`, `tags (student_id, name)`, `student_settings.student_id`. |
| 6 | A junction table cannot hold a pair twice | Pass. `PRIMARY KEY (note_id, tag_id)`. |
| 7 | Filtered and joined columns have an index | Pass, after a correction. The first pass listed an index for every foreign-key column: six of them. Four were removed, because a `PRIMARY KEY` or `UNIQUE` constraint already indexes those columns and the checklist row says to count those. Two remain: `notes(notebook_id)` and `note_tags(tag_id)`. The reasoning for each, including the four that are absent, is a comment in `db/schema.sql`. |
| 8 | Every table is needed by version 1 | Pass. `themes` and `courses` were considered and left out; `note_tags.applied_at` was left out for the same reason (D16). |
| 9 | Dates and times use one recorded format | Pass. One format, recorded in a comment at the top of `db/schema.sql` (D7). |
| 10 | Declared types match the values stored | Pass, with one thing to know. `compact_view` is declared `INTEGER` and holds 0 or 1, because SQLite has no boolean type. SQLite applies type affinity rather than rejecting a value of another type, so the `CHECK` constraint is what actually keeps the column to two values. |
| 11 | Each relationship states what a parent deletion does | Pass. Every `REFERENCES` clause carries an explicit `ON DELETE` action: `RESTRICT` (D1), `CASCADE` (D10, D11), `SET NULL` (D5). |

The only defect the review found was row 7, and it was corrected before
`db/seed.py` was run for the first time.

## Operations the application runs (Step 6)

Each of these is one function in `db/queries.py` with a docstring naming the
question it answers. The four rows 9.2 requires are marked.

| Function | Question it answers | 9.2 requirement |
|---|---|---|
| `create_student` | a student signs up — what rows does that create? | write across two tables in one transaction |
| `get_student` | who is this account? | one read |
| `create_notebook` | start a notebook for a course | |
| `get_notebook` | which notebook is this, and whose is it? | |
| `list_notebooks` | which notebooks does this student have, and how many notes is each holding? | |
| `delete_notebook` | remove a notebook the student no longer wants | |
| `add_note` | write down one note | one insert |
| `get_note` | show me this note | one read |
| `update_note_body` | I edited the note — save it and record that it changed | |
| `notes_with_notebook_name` | which notes has this student written, and which notebook is each in? | a `JOIN` over a declared relationship |
| `notes_with_tag` | list every note associated with this tag | |
| `note_count_per_tag` | how many notes does each tag have? | an aggregate with `GROUP BY` |
| `tags_used_at_least` | which tags have at least *n* notes? | |
| `create_tag` | add a new label | |
| `add_note_with_tags` | write a note and label it, as one action | write across two tables in one transaction |
| `attach_tag_to_note` | add one label to an existing note | |
| `get_student_settings` | what are this student's settings? | |
| `update_settings` | change the theme, default notebook, or list density | |

## Known limits of version 1

Stated here so a reader does not mistake them for oversights.

- **A tag can be attached to another student's note.** `note_tags` joins a note
  to a tag. The note's owner is reached through its notebook and the tag's owner
  is on the tag row, and no single-table constraint compares the two. The
  application only ever offers a student their own tags and their own notes, and
  `notes_with_tag()` filters on both sides, so the wrong pair is never created by
  the application. Enforcing it in the schema would need a `CHECK` across tables,
  which SQLite does not support in this form.
- **No authentication.** `student_id` arrives as a path parameter and is
  trusted. The spec's users section describes separate accounts, not a login;
  adding one is out of scope for version 1 and would change every endpoint.
- **No note deletion endpoint.** The `ON DELETE CASCADE` on `note_tags` is
  declared and tested, but version 1's spec lists no delete-a-note feature.
- **No full-text search.** "Search by meaning" is out of scope for version 1 by
  the spec, and search by word is not listed as a feature either. Session 11.1
  adds the first of these as a vector column on `notes`.

## What 10.0, 10.1 and 11.1 need from this schema

| Session | What it does with this |
|---|---|
| 10.0 | packages the application in a container image. `*.db` is excluded by `.dockerignore`, so the container starts with no database and `GET /health` is the endpoint that answers without one. |
| 10.1 | runs this schema and these queries against PostgreSQL and corrects what fails. |
| 11.1 | adds a vector column to `notes`, so that "search by meaning" — out of scope in version 1 — can be built on the same rows. |

The code is written the way SQLite writes it, not in a form both databases
accept. That is a deliberate choice for this application and not the advice 9.2
gives students, because 10.1's demonstration is the instructor migrating this
code live. Every construct that PostgreSQL rejects is marked with a
`SQLITE-SPECIFIC` comment at the place it appears. `README.md` lists all of them
with their file and reason.
