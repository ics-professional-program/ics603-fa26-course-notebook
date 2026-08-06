-- Course Notebook — database schema, version 1
--
-- SQLite, raw SQL, no ORM.  Loaded by db/seed.py with conn.executescript().
-- The decisions behind every constraint below are recorded in docs/design.md;
-- the D-numbers in the comments refer to that file.
--
-- ---------------------------------------------------------------------------
-- Storage conventions (9.2 Step 7 asks for these to be recorded here)
-- ---------------------------------------------------------------------------
--
--   Dates and times   TEXT in ISO 8601, UTC, to the second, with a Z suffix:
--                     '2026-10-22T14:30:00Z'.  SQLite has no date or time
--                     storage class, so this is an application convention, not
--                     something the database enforces.  One format everywhere,
--                     because text sorting is only date sorting when the field
--                     order, precision and time zone never vary.  (D7)
--
--   True and false    INTEGER holding 0 or 1, with CHECK (col IN (0, 1)).
--                     SQLite has no boolean storage class.
--
--   Generated keys    INTEGER PRIMARY KEY AUTOINCREMENT, read back in Python
--                     with cursor.lastrowid.
--
-- ---------------------------------------------------------------------------
-- Relationship kinds (9.2 Step 7 asks for these to be recorded here)
-- ---------------------------------------------------------------------------
--
--   student  -> notebooks         one-to-many   foreign key on notebooks
--   student  -> tags              one-to-many   foreign key on tags       (D2)
--   notebook -> notes             one-to-many   foreign key on notes
--   notes   <-> tags              many-to-many  junction table note_tags
--   student  -> settings          one-to-one    foreign key + UNIQUE     (D12)
--   settings -> default notebook  many-to-one   foreign key, nullable     (D5)
--
--   The last row is NOT one-to-one, and the difference is the rule 9.2 gives:
--   one-to-one is a foreign key PLUS UNIQUE.  default_notebook_id has no
--   UNIQUE, so nothing stops two students' settings rows naming the same
--   notebook.  Only same-owner enforcement would make that impossible, and
--   version 1 does not have it.
--
-- ---------------------------------------------------------------------------
-- SQLITE-SPECIFIC constructs
-- ---------------------------------------------------------------------------
--
-- Session 10.1 migrates this file to PostgreSQL as a live demonstration.  The
-- statements PostgreSQL rejects are marked "SQLITE-SPECIFIC" below, each with
-- the PostgreSQL form named in the comment.  They are correct SQLite, not
-- defects, and they are the material that migration works on.  Do not replace
-- them with portable SQL.
--
-- In this file:  AUTOINCREMENT (five sites) and strftime() defaults (four
-- sites).  The rest are in db/seed.py and db/queries.py, and README.md lists
-- every one of them with its file.


-- ---------------------------------------------------------------------------
-- students: one row per account.  The spec says accounts are not shared, so
-- every other table in this schema is related to this one.
-- ---------------------------------------------------------------------------
CREATE TABLE students (
    -- 9.0 and 9.2 write this as "INTEGER PRIMARY KEY", which is enough.  The
    -- extra word AUTOINCREMENT tells SQLite never to reuse an id that belonged
    -- to a deleted row; without it, SQLite may hand a new row the id of the
    -- highest deleted one.  It costs a little extra bookkeeping per insert.
    --
    -- SQLITE-SPECIFIC: AUTOINCREMENT.  PostgreSQL writes this column as
    -- "id integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY".
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,          -- one account per address
    -- SQLITE-SPECIFIC: strftime() is a SQLite function and PostgreSQL has no
    -- such function.  There the column becomes
    -- "created_at timestamptz NOT NULL DEFAULT now()".
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);


-- ---------------------------------------------------------------------------
-- notebooks: one row per notebook, usually one per course.
-- Deleting a student deletes their notebooks (D11), but see the note on
-- notes.notebook_id below: that cascade stops at any notebook holding notes.
-- ---------------------------------------------------------------------------
CREATE TABLE notebooks (
    -- SQLITE-SPECIFIC: AUTOINCREMENT.
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    -- SQLITE-SPECIFIC: strftime() default.
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    -- One student cannot have two notebooks with the same name; two different
    -- students can each have one named 'ICS 603 Building LLM Applications'. (D8)
    UNIQUE (student_id, name)
);


-- ---------------------------------------------------------------------------
-- notes: one row per note.  The thing the application exists to store.
--
-- notes has no student_id column.  A note's owner is reached through its
-- notebook, so the value cannot be stored twice and disagree with itself. (D13)
-- ---------------------------------------------------------------------------
CREATE TABLE notes (
    -- SQLITE-SPECIFIC: AUTOINCREMENT.
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- ON DELETE RESTRICT: deleting a notebook that still holds notes is
    -- rejected.  The notes are the data the student typed; the notebook is a
    -- container for them.  The application turns this rejection into HTTP 409
    -- and asks the student to move or delete the notes first. (D1)
    notebook_id INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE RESTRICT,

    title       TEXT NOT NULL,

    -- body permits NULL: a note typed during class often starts as a title with
    -- the body added later.  NULL means "not written yet", which is not the
    -- same as '' — NOT NULL would reject the first and accept the second. (D4)
    body        TEXT,

    -- SQLITE-SPECIFIC: strftime() defaults, twice.  Both columns are ISO 8601
    -- UTC text.  created_at is never changed after the insert; updated_at is
    -- set again by every statement that changes the note. (D6)
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);


-- ---------------------------------------------------------------------------
-- tags: one row per tag name per student.
--
-- Tags belong to a student rather than being one global list, because the spec
-- says no data is shared between accounts: a global list would count another
-- student's notes, rename their tag, and show them names they never chose. (D2)
-- ---------------------------------------------------------------------------
CREATE TABLE tags (
    -- SQLITE-SPECIFIC: AUTOINCREMENT.
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,

    -- One 'exam' per student.  UNIQUE (name) alone would be a global tag list.
    UNIQUE (student_id, name)
);


-- ---------------------------------------------------------------------------
-- note_tags: one row per (note, tag) pair.  This is the many-to-many
-- relationship between notes and tags.  A foreign-key column holds one value,
-- so it cannot hold a list of tags; the pairs are stored in their own table.
--
-- No AUTOINCREMENT here: the identity of a row is the pair, not a new number.
-- No extra columns: version 1 never reads when a tag was applied, so applied_at
-- is not stored.  If it were needed it would belong here, because the value
-- describes the pair and not either side. (D16)
-- ---------------------------------------------------------------------------
CREATE TABLE note_tags (
    -- ON DELETE CASCADE on both sides: this row records that one note carries
    -- one tag.  Without either end it has no meaning and can never be read
    -- again.  Deleting a tag removes its labels and leaves the notes. (D10)
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,

    -- Composite primary key: the same pair cannot be stored twice, which is
    -- what "a student applies the same tag twice to one note" needs. (D9)
    PRIMARY KEY (note_id, tag_id)
);


-- ---------------------------------------------------------------------------
-- student_settings: display theme, default notebook and list density.
-- One row per student — the one-to-one relationship in this schema.
--
-- UNIQUE on student_id enforces AT MOST ONE settings row per student.  It
-- cannot require that the row exists; no relational schema can.  The
-- application creates it, in create_student(), in the same transaction as the
-- student row. (D12)
-- ---------------------------------------------------------------------------
CREATE TABLE student_settings (
    -- SQLITE-SPECIFIC: AUTOINCREMENT.
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    student_id          INTEGER NOT NULL UNIQUE
                            REFERENCES students(id) ON DELETE CASCADE,

    -- The value list is short and does not change per student, so a CHECK holds
    -- it rather than a three-row themes table. (D15)
    theme               TEXT NOT NULL
                            CHECK (theme IN ('light', 'dark', 'system')),

    -- NULL means the student has not chosen a default notebook; the application
    -- then asks which notebook to write into.  ON DELETE SET NULL returns the
    -- student to that state when the chosen notebook is deleted, instead of
    -- blocking the delete or silently choosing a different notebook. (D5)
    default_notebook_id INTEGER REFERENCES notebooks(id) ON DELETE SET NULL,

    -- SQLite has no boolean storage class.  The CHECK is what keeps this column
    -- to two values, because SQLite's declared types are affinities and would
    -- otherwise store 'yes' here.  PostgreSQL writes this column as
    -- "compact_view boolean NOT NULL DEFAULT false" and drops the CHECK.
    compact_view        INTEGER NOT NULL DEFAULT 0
                            CHECK (compact_view IN (0, 1))
);


-- ---------------------------------------------------------------------------
-- Indexes
--
-- Only for columns the application filters or joins on that are not already
-- indexed by a PRIMARY KEY or UNIQUE constraint.  9.2 checklist row 7 says to
-- count those, so the four indexes below are NOT created:
--
--   notebooks(student_id)          covered by UNIQUE (student_id, name)
--   tags(student_id)               covered by UNIQUE (student_id, name)
--   student_settings(student_id)   covered by UNIQUE (student_id)
--   note_tags(note_id)             covered by PRIMARY KEY (note_id, tag_id)
--
-- A composite index helps lookups on its leading column, which is why the first
-- three are already covered.  It does not help lookups on a later column on its
-- own, which is why note_tags(tag_id) below is needed and note_tags(note_id)
-- is not.
--
-- student_settings(default_notebook_id) is also not indexed.  Deleting a
-- notebook has to find the settings rows pointing at it, but that table holds
-- one row per student and the scan is cheaper than maintaining another index.
-- ---------------------------------------------------------------------------

-- Joined by notes_with_notebook_name() and notes_with_tag(); filtered by
-- list_notebooks() and by the foreign-key check on every note insert.
CREATE INDEX idx_notes_notebook_id ON notes(notebook_id);

-- Filtered by notes_with_tag() and joined by note_count_per_tag().  The
-- composite primary key indexes (note_id, tag_id), so a lookup by tag_id alone
-- has nothing to search without this.
CREATE INDEX idx_note_tags_tag_id ON note_tags(tag_id);
