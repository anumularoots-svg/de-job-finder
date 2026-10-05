"""Check a company's job board before adding it to companies.csv.

  python -m collector.check greenhouse stripe
  python -m collector.check lever palantir
  python -m collector.check ashby ramp

How to find the token: open the company's careers page and click a job.
  boards.greenhouse.io/<token>/jobs/123   or  job-boards.greenhouse.io/<token>/...
  jobs.lever.co/<token>/...
  jobs.ashbyhq.com/<token>/...
"""
import sys

from .http import HttpClient, RobotsBlocked
from .sources.ats import FETCHERS


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in FETCHERS:
        print(__doc__)
        return 2
    ats, token = sys.argv[1], sys.argv[2]
    try:
        jobs = FETCHERS[ats](HttpClient(), token, token)
    except RobotsBlocked as e:
        print(f"Blocked by robots.txt on {e}. Keep this company as a manual search.")
        return 1
    except Exception as e:
        print(f"Not found or failed: {e}")
        return 1
    print(f"OK: {ats}/{token} works. Data Engineer jobs open right now: {len(jobs)}")
    for j in jobs[:10]:
        print(f"  - {j['title']} | {j['location']}")
    print(f"\nAdd this line to collector/companies.csv:\n{ats},{token},<Company Name>,yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
