"""Offline stand-in for HttpClient. Serves JSON fixtures shaped like the real APIs.

Timestamps in fixtures are written relative to now: "@-3h", "@-2d" (ISO string)
or "@ms-20h" (epoch milliseconds, as Lever returns).
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from ..http import RobotsBlocked

_REL = re.compile(r"^@(ms)?-(\d+)([hd])$")


def _resolve(o):
    if isinstance(o, dict):
        return {k: _resolve(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_resolve(v) for v in o]
    if isinstance(o, str):
        m = _REL.match(o)
        if m:
            delta = timedelta(hours=int(m.group(2))) if m.group(3) == "h" else timedelta(days=int(m.group(2)))
            dt = datetime.now(timezone.utc) - delta
            return int(dt.timestamp() * 1000) if m.group(1) else dt.isoformat()
    return o


class FakeHttp:
    BLOCKED_HOSTS = {"api.smartrecruiters.com"}   # mirrors the real robots.txt

    def __init__(self, folder):
        self.folder = folder

    def _load(self, name):
        p = os.path.join(self.folder, name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return _resolve(json.load(f))

    def get_json(self, url, params=None):
        u = urlparse(url)
        if u.netloc in self.BLOCKED_HOSTS:
            raise RobotsBlocked(u.netloc)
        parts = u.path.strip("/").split("/")
        if u.netloc == "boards-api.greenhouse.io":
            return self._load(f"greenhouse_{parts[2]}.json")
        if u.netloc == "api.lever.co":
            return self._load(f"lever_{parts[2]}.json")
        if u.netloc == "api.ashbyhq.com":
            return self._load(f"ashby_{parts[2]}.json")
        if u.netloc == "api.adzuna.com":
            phrase = (params or {}).get("what_phrase", "").replace(" ", "_")
            return self._load(f"adzuna_{phrase}_{parts[-1]}.json") or {"results": []}
        return None
