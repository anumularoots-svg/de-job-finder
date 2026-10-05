"""Adzuna aggregator via its official API (free key: https://developer.adzuna.com).

Adzuna returns only a snippet of each description, so W-2 wording is often
missing. Those jobs stay "W-2 Unknown". Adzuna jobs are never marked
"Direct Full-Time", because we cannot verify the poster is the employer.
redirect_url sends the user through Adzuna to the original posting.
"""
from .. import config
from ..normalize import strip_html, iso
from .ats import _title_ok


_ABBR = {v: k for k, v in config.US_STATES.items()}


def _location(loc):
    """Adzuna area looks like ["US", "Texas", "Dallas County", "Dallas"]."""
    area = loc.get("area") or []
    if len(area) >= 2:
        state = _ABBR.get(area[1], area[1])
        return f"{area[-1]}, {state}" if len(area) > 2 else f"{area[1]}, US"
    return (loc.get("display_name") or "United States") + ", US"


def adzuna(http):
    if not (config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY):
        raise PermissionError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
    out, seen = [], set()
    for phrase in config.ADZUNA_PHRASES:
        for page in range(1, config.ADZUNA_MAX_PAGES + 1):
            data = http.get_json(
                f"https://api.adzuna.com/v1/api/jobs/us/search/{page}",
                params={
                    "app_id": config.ADZUNA_APP_ID, "app_key": config.ADZUNA_APP_KEY,
                    "what_phrase": phrase, "max_days_old": config.ADZUNA_MAX_DAYS_OLD,
                    "sort_by": "date", "results_per_page": 50, "content-type": "application/json",
                },
            ) or {}
            results = data.get("results", [])
            for j in results:
                jid = str(j.get("id"))
                if jid in seen or not _title_ok(j.get("title")):
                    continue
                seen.add(jid)
                hints = " ".join(x for x in [j.get("contract_type") or "", j.get("contract_time") or ""] if x)
                out.append(dict(
                    source="Adzuna", source_job_id=f"az:{jid}",
                    company=(j.get("company") or {}).get("display_name", "Unknown company"),
                    title=strip_html(j.get("title", "")),
                    location=_location(j.get("location") or {}),
                    remote_hint="", employment_hint=hints.replace("_", " "),
                    description=strip_html(j.get("description", "")),
                    original_url=j.get("redirect_url"), apply_url=j.get("redirect_url"),
                    posted_at=iso(j.get("created")), posted_approx=False, is_direct=False,
                ))
            if len(results) < 50:
                break
    return out
