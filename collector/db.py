"""SQLite storage. One file: data/jobs.db (committed back to the repo by GitHub Actions)."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id               TEXT PRIMARY KEY,
  dup_key          TEXT UNIQUE NOT NULL,
  title            TEXT, company TEXT, location TEXT, us_location INTEGER,
  remote_type      TEXT, employment_type TEXT,
  w2_status        TEXT, c2c_status TEXT, evidence TEXT,
  sponsorship      TEXT, sponsorship_note TEXT,
  experience_min   INTEGER, skills TEXT,
  posted_at        TEXT, posted_approx INTEGER,
  discovered_at    TEXT, last_seen_at TEXT,
  apply_url        TEXT, original_url TEXT, preferred_source TEXT, found_on TEXT
);
CREATE TABLE IF NOT EXISTS sightings (
  source_job_id    TEXT PRIMARY KEY,          -- e.g. gh:stripe:12345, az:4411
  job_id           TEXT NOT NULL REFERENCES jobs(id),
  source           TEXT, is_direct INTEGER,
  title TEXT, company TEXT, location TEXT, remote_hint TEXT, employment_hint TEXT,
  description      TEXT,
  original_url     TEXT, apply_url TEXT,
  posted_at        TEXT, posted_approx INTEGER,
  first_seen_at    TEXT, last_seen_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_sight_job ON sightings(job_id);
CREATE INDEX IF NOT EXISTS ix_sight_url ON sightings(original_url);
CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT, source TEXT, target TEXT,
  ok INTEGER, fetched INTEGER, error TEXT
);
"""


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
