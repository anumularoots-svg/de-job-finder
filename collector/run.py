"""Run one collection: fetch permitted sources -> normalize -> classify -> dedupe -> SQLite -> JSON.

Usage:
  python -m collector.run                      # real run (GitHub Actions)
  python -m collector.run --fixtures collector/tests/fixtures   # offline test run
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from . import config, db
from .classify import classify
from .http import HttpClient, RobotsBlocked
from .normalize import dup_key, employment_type, remote_type, us_location
from .sources.adzuna import adzuna
from .sources.ats import FETCHERS, LABELS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def now():
    return datetime.now(timezone.utc)


def load_companies(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not (r.get("ats") or "").startswith("#")]
    return [r for r in rows if (r.get("enabled") or "yes").strip().lower() != "no"]


def collect(http, companies, started):
    """Returns (records, source_report, run_rows)."""
    records, runs = [], []
    report = {label: {"type": "ats", "companies": 0, "ok": 0, "failed": [], "jobs": 0,
                      "robotsBlocked": False, "error": ""} for label in LABELS.values()}
    report["Adzuna"] = {"type": "aggregator", "ok": 0, "jobs": 0, "robotsBlocked": False, "error": ""}

    for c in companies:
        ats = c["ats"].strip().lower()
        if ats not in FETCHERS:
            continue
        label = LABELS[ats]
        rep = report[label]
        rep["companies"] += 1
        if rep["robotsBlocked"]:
            continue
        try:
            got = FETCHERS[ats](http, c["token"].strip(), c["company"].strip())
            records += got
            rep["ok"] += 1
            rep["jobs"] += len(got)
            runs.append((label, c["token"], 1, len(got), ""))
        except RobotsBlocked as e:
            rep["robotsBlocked"] = True
            rep["error"] = f"robots.txt on {e} disallows automated access"
            runs.append((label, c["token"], 0, 0, rep["error"]))
        except Exception as e:  # one bad company must not stop the run
            rep["failed"].append(c["token"])
            runs.append((label, c["token"], 0, 0, f"{type(e).__name__}: {e}"[:300]))

    rep = report["Adzuna"]
    try:
        got = adzuna(http)
        records += got
        rep["ok"], rep["jobs"] = 1, len(got)
        runs.append(("Adzuna", "search", 1, len(got), ""))
    except PermissionError as e:
        rep["error"] = str(e)
        rep["notConfigured"] = True
    except RobotsBlocked as e:
        rep["robotsBlocked"], rep["error"] = True, f"robots.txt on {e} disallows automated access"
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"[:300]
        runs.append(("Adzuna", "search", 0, 0, rep["error"]))
    return records, report, runs


def _pref_key(s):
    # Prefer the employer's own board, then the longest description.
    return (1 if s["is_direct"] else 0, len(s["description"] or ""))


def store(con, records, started):
    ts = started.isoformat()
    touched = set()
    for r in records:
        if us_location(r["location"]) is False:
            continue
        existing = con.execute("SELECT job_id FROM sightings WHERE source_job_id=?", (r["source_job_id"],)).fetchone()
        rtype = remote_type(r["remote_hint"], r["location"], r["title"], r["description"])
        key = dup_key(r["company"], r["title"], r["location"], rtype)
        job_id = existing["job_id"] if existing else None
        if not job_id:
            row = con.execute("SELECT id FROM jobs WHERE dup_key=?", (key,)).fetchone() or \
                con.execute("SELECT job_id AS id FROM sightings WHERE original_url=? AND original_url IS NOT NULL",
                            (r["original_url"],)).fetchone()
            job_id = row["id"] if row else None
        if not job_id:
            job_id = hashlib.sha1(key.encode()).hexdigest()[:12]
            con.execute("INSERT INTO jobs (id, dup_key, discovered_at, last_seen_at) VALUES (?,?,?,?)",
                        (job_id, key, ts, ts))
        con.execute("""
          INSERT INTO sightings (source_job_id, job_id, source, is_direct, title, company, location, remote_hint,
                                 employment_hint, description, original_url, apply_url, posted_at, posted_approx,
                                 first_seen_at, last_seen_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(source_job_id) DO UPDATE SET
            title=excluded.title, company=excluded.company, location=excluded.location,
            remote_hint=excluded.remote_hint, employment_hint=excluded.employment_hint,
            description=excluded.description, original_url=excluded.original_url, apply_url=excluded.apply_url,
            posted_at=COALESCE(sightings.posted_at, excluded.posted_at), posted_approx=excluded.posted_approx,
            last_seen_at=excluded.last_seen_at
        """, (r["source_job_id"], job_id, r["source"], int(r["is_direct"]), r["title"], r["company"], r["location"],
              r["remote_hint"], r["employment_hint"], (r["description"] or "")[:12000], r["original_url"],
              r["apply_url"], r["posted_at"], int(bool(r["posted_approx"])), ts, ts))
        touched.add(job_id)

    for job_id in touched:
        rebuild_job(con, job_id, ts)
    con.commit()
    return touched


def rebuild_job(con, job_id, ts):
    sights = [dict(s) for s in con.execute("SELECT * FROM sightings WHERE job_id=?", (job_id,))]
    best = max(sights, key=_pref_key)
    text = "\n".join(s["description"] or "" for s in sorted(sights, key=_pref_key, reverse=True))
    rtype = remote_type(best["remote_hint"], best["location"], best["title"], text)
    etype = employment_type(best["employment_hint"], best["title"], best["description"])
    cls = classify(best["title"], text, etype, bool(best["is_direct"]))
    dated = [s for s in sights if s["posted_at"]]
    first = min(dated, key=lambda s: s["posted_at"]) if dated else None
    found_on = sorted({s["source"] for s in sights})
    con.execute("""
      UPDATE jobs SET title=?, company=?, location=?, us_location=?, remote_type=?, employment_type=?,
        w2_status=?, c2c_status=?, evidence=?, sponsorship=?, sponsorship_note=?, experience_min=?, skills=?,
        posted_at=?, posted_approx=?, last_seen_at=?, apply_url=?, original_url=?, preferred_source=?, found_on=?
      WHERE id=?""", (
        best["title"], best["company"], best["location"],
        {True: 1, False: 0, None: None}[us_location(best["location"])], rtype, etype,
        cls["w2_status"], cls["c2c_status"], json.dumps(cls["evidence"]), cls["sponsorship"],
        cls["sponsorship_note"], cls["experience_min"], json.dumps(cls["skills"]),
        first["posted_at"] if first else None, int(first["posted_approx"]) if first else 1,
        max(s["last_seen_at"] for s in sights), best["apply_url"], best["original_url"], best["source"],
        json.dumps(found_on), job_id))


def export(con, out_dir, started, report, total_records):
    cutoff_seen = (started - timedelta(hours=config.STALE_AFTER_HOURS)).isoformat()
    cutoff_posted = (started - timedelta(days=config.MAX_AGE_DAYS)).isoformat()
    rows = con.execute("""
      SELECT * FROM jobs WHERE last_seen_at >= ? AND COALESCE(posted_at, discovered_at) >= ?
        AND COALESCE(us_location, 1) != 0
      ORDER BY COALESCE(posted_at, discovered_at) DESC""", (cutoff_seen, cutoff_posted)).fetchall()
    jobs = [{
        "id": r["id"], "title": r["title"], "company": r["company"], "location": r["location"],
        "usLocation": None if r["us_location"] is None else bool(r["us_location"]),
        "remoteType": r["remote_type"], "employmentType": r["employment_type"],
        "w2Status": r["w2_status"], "c2cStatus": r["c2c_status"], "evidence": json.loads(r["evidence"] or "[]"),
        "sponsorship": r["sponsorship"], "sponsorshipNote": r["sponsorship_note"],
        "experienceMin": r["experience_min"], "skills": json.loads(r["skills"] or "[]"),
        "postedAt": r["posted_at"], "postedApprox": bool(r["posted_approx"]),
        "discoveredAt": r["discovered_at"], "lastSeenAt": r["last_seen_at"],
        "applyUrl": r["apply_url"], "originalUrl": r["original_url"],
        "source": r["preferred_source"], "foundOn": json.loads(r["found_on"] or "[]"),
    } for r in rows]
    os.makedirs(out_dir, exist_ok=True)
    meta = {"generatedAt": now().isoformat(), "runStartedAt": started.isoformat(),
            "refreshEveryHours": 2, "recordsFetched": total_records, "jobCount": len(jobs)}
    with open(os.path.join(out_dir, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "jobs": jobs}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "sources": report}, f, ensure_ascii=False, indent=1)
    return len(jobs)


def prune(con, started):
    old = (started - timedelta(days=30)).isoformat()
    con.execute("DELETE FROM sightings WHERE job_id IN (SELECT id FROM jobs WHERE last_seen_at < ?)", (old,))
    con.execute("DELETE FROM jobs WHERE last_seen_at < ?", (old,))
    con.execute("DELETE FROM source_runs WHERE started_at < ?", (old,))
    con.commit()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "jobs.db"))
    ap.add_argument("--out", default=os.path.join(ROOT, "public", "dataenginer", "data"))
    ap.add_argument("--companies", default=os.path.join(ROOT, "collector", "companies.csv"))
    ap.add_argument("--fixtures", help="offline test mode: read API responses from this folder")
    a = ap.parse_args(argv)

    if a.fixtures:
        from .tests.fake_http import FakeHttp
        http = FakeHttp(a.fixtures)
        if not config.ADZUNA_APP_ID:
            config.ADZUNA_APP_ID = config.ADZUNA_APP_KEY = "fixture"
    else:
        http = HttpClient()

    started = now()
    companies = load_companies(a.companies)
    records, report, runs = collect(http, companies, started)
    os.makedirs(os.path.dirname(a.db), exist_ok=True)
    con = db.connect(a.db)
    con.executemany("INSERT INTO source_runs (started_at, finished_at, source, target, ok, fetched, error) VALUES (?,?,?,?,?,?,?)",
                    [(started.isoformat(), now().isoformat(), *r) for r in runs])
    store(con, records, started)
    prune(con, started)
    n = export(con, a.out, started, report, len(records))

    print(f"Fetched {len(records)} matching postings; dashboard now lists {n} jobs.")
    for name, r in report.items():
        extra = f" failed={','.join(r['failed'])}" if r.get("failed") else ""
        print(f"  {name:16} ok={r.get('ok')} jobs={r.get('jobs')}{extra} {r.get('error','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
