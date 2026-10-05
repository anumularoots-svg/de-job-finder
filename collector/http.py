"""Polite HTTP client: checks robots.txt, rate-limits per host, backs off on 429.

It never logs in, never solves CAPTCHAs and never retries around a block.
If robots.txt disallows a URL, the call raises RobotsBlocked and the source
is reported as "Manual" on the dashboard.
"""
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from . import config


class RobotsBlocked(Exception):
    pass


class HttpClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
        self._robots = {}
        self._last = {}

    def allowed(self, url):
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(base + "/robots.txt", timeout=config.TIMEOUT_SECONDS)
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True          # no robots.txt = no restriction
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp.allow_all = True
            self._robots[base] = rp
        return self._robots[base].can_fetch(config.USER_AGENT, url)

    def get_json(self, url, params=None):
        full = requests.Request("GET", url, params=params).prepare().url
        if not self.allowed(full):
            raise RobotsBlocked(urlparse(full).netloc)
        host = urlparse(url).netloc
        wait = config.REQUEST_DELAY_SECONDS - (time.time() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self._last[host] = time.time()
            r = self.s.get(url, params=params, timeout=config.TIMEOUT_SECONDS)
            if r.status_code == 429:
                time.sleep(min(int(r.headers.get("Retry-After", "10") or 10), 60))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        raise requests.HTTPError(f"429 rate limited: {host}")
