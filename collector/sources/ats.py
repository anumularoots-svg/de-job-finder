"""Company job boards with official public APIs (no login, no key).

Greenhouse: https://developers.greenhouse.io/job-board.html
Lever:      https://github.com/lever/postings-api
Ashby:      https://developers.ashbyhq.com/docs/public-job-posting-api
SmartRecruiters: https://developers.smartrecruiters.com/docs/posting-api
"""
from datetime import datetime, timezone

from ..normalize import strip_html, iso, us_location
from .. import config


def _title_ok(title):
    return bool(config.TITLE_INCLUDE.search(title or "")) and not config.TITLE_EXCLUDE.search(title or "")


def greenhouse(http, token, company):
    data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
    if data is None:
        raise LookupError(f"greenhouse board '{token}' not found")
    out = []
    for j in data.get("jobs", []):
        if not _title_ok(j.get("title")):
            continue
        first = j.get("first_published")
        meta = " ".join(f"{m.get('name')}: {m.get('value')}" for m in (j.get("metadata") or []) if m.get("value"))
        out.append(dict(
            source="Greenhouse", source_job_id=f"gh:{token}:{j['id']}",
            company=j.get("company_name") or company, title=j["title"],
            location=(j.get("location") or {}).get("name", ""),
            remote_hint="", employment_hint=meta,
            description=strip_html(j.get("content", "")),
            original_url=j.get("absolute_url"), apply_url=j.get("absolute_url"),
            posted_at=iso(first or j.get("updated_at")),
            posted_approx=not first,   # updated_at is not the posting date
            is_direct=True,
        ))
    return out


def lever(http, token, company):
    data = http.get_json(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    if data is None:
        raise LookupError(f"lever site '{token}' not found")
    out = []
    for j in data:
        if not _title_ok(j.get("text")):
            continue
        cat = j.get("categories") or {}
        lists = "\n".join(f"{l.get('text','')}\n{strip_html(l.get('content',''))}" for l in (j.get("lists") or []))
        desc = "\n".join(x for x in [j.get("descriptionPlain", ""), lists, j.get("additionalPlain", "")] if x)
        created = j.get("createdAt")
        out.append(dict(
            source="Lever", source_job_id=f"lv:{token}:{j['id']}",
            company=company, title=j["text"],
            location=cat.get("location") or ", ".join(cat.get("allLocations") or []),
            remote_hint=j.get("workplaceType") or "", employment_hint=cat.get("commitment") or "",
            description=desc,
            original_url=j.get("hostedUrl"), apply_url=j.get("applyUrl") or j.get("hostedUrl"),
            posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if created else None,
            posted_approx=False, is_direct=True,
        ))
    return out


def ashby(http, token, company):
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    if data is None:
        raise LookupError(f"ashby board '{token}' not found")
    out = []
    for j in data.get("jobs", []):
        if not _title_ok(j.get("title")) or j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in (j.get("secondaryLocations") or [])]
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or "")
        loc = "; ".join(x for x in locs if x)
        if country and country not in loc and us_location(loc) is None:
            loc = f"{loc} ({country})" if loc else country
        out.append(dict(
            source="Ashby", source_job_id=f"ab:{token}:{j['id']}",
            company=company, title=j["title"], location=loc,
            remote_hint=j.get("workplaceType") or ("Remote" if j.get("isRemote") else ""),
            employment_hint=j.get("employmentType") or "",
            description=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")),
            original_url=j.get("jobUrl"), apply_url=j.get("applyUrl") or j.get("jobUrl"),
            posted_at=iso(j.get("publishedAt")), posted_approx=False, is_direct=True,
        ))
    return out


def smartrecruiters(http, token, company):
    base = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
    out, offset = [], 0
    while True:
        data = http.get_json(base, params={"q": "data engineer", "country": "us", "limit": 100, "offset": offset})
        if data is None:
            raise LookupError(f"smartrecruiters company '{token}' not found")
        for j in data.get("content", []):
            if not _title_ok(j.get("name")):
                continue
            d = http.get_json(f"{base}/{j['id']}") or {}
            secs = ((d.get("jobAd") or {}).get("sections") or {})
            desc = "\n".join(strip_html((secs.get(k) or {}).get("text", "")) for k in
                             ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
            loc = j.get("location") or {}
            url = d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{token}/{j['id']}"
            out.append(dict(
                source="SmartRecruiters", source_job_id=f"sr:{token}:{j['id']}",
                company=(j.get("company") or {}).get("name") or company, title=j["name"],
                location=", ".join(x for x in [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()] if x),
                remote_hint="Remote" if loc.get("remote") else "",
                employment_hint=(j.get("typeOfEmployment") or {}).get("label", ""),
                description=desc, original_url=url, apply_url=d.get("applyUrl") or url,
                posted_at=iso(j.get("releasedDate")), posted_approx=False, is_direct=True,
            ))
        offset += 100
        if offset >= data.get("totalFound", 0):
            break
    return out


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters}
LABELS = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters"}
