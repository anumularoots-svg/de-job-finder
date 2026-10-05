"""Turn raw source records into consistent fields: text, dates, location, work type."""
import html
import re
from datetime import datetime, timezone

from . import config

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")


def strip_html(s):
    if not s:
        return ""
    s = html.unescape(html.unescape(s))          # Greenhouse content is escaped twice
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s)
    s = _TAG.sub(" ", s)
    s = _WS.sub(" ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def iso(value):
    """Parse many timestamp shapes into an ISO-8601 UTC string."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), timezone.utc).isoformat()
    v = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        try:
            dt = datetime.strptime(v[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# ---------- Location ----------
_STATE_ABBR = "|".join(config.US_STATES)
_STATE_NAMES = "|".join(re.escape(n) for n in config.US_STATES.values())
_US_WORDS = re.compile(r"\bunited states\b|\bu\.?s\.?a\.?\b|\bU\.S\.|\bUS\b|\bamericas?\b(?!.*latam)|\bnationwide\b", re.I)
_US_STATE = re.compile(rf",\s*({_STATE_ABBR})\b|\b({_STATE_NAMES})\b")
_NON_US = re.compile(
    r"\b(canada|toronto|vancouver|montreal|ontario|united kingdom|\buk\b|england|london|ireland|dublin|"
    r"germany|berlin|munich|france|paris|netherlands|amsterdam|spain|madrid|barcelona|portugal|lisbon|"
    r"poland|warsaw|krakow|romania|india|bengaluru|bangalore|hyderabad|pune|chennai|gurgaon|noida|"
    r"singapore|australia|sydney|melbourne|japan|tokyo|china|brazil|sao paulo|mexico|argentina|"
    r"colombia|costa rica|israel|tel aviv|philippines|emea|apac|latam|europe|switzerland|zurich|sweden|"
    r"stockholm|denmark|copenhagen|italy|milan|serbia|ukraine|estonia|czech|prague|hungary|budapest|"
    r"south africa|nigeria|kenya|egypt|uae|dubai|saudi|korea|seoul|taiwan|vietnam|indonesia|malaysia|"
    r"new zealand)\b",
    re.I,
)


def us_location(loc):
    """True = clearly US, False = clearly outside US, None = not stated (e.g. just 'Remote')."""
    loc = loc or ""
    if _US_STATE.search(loc) or _US_WORDS.search(loc):
        return True
    if _NON_US.search(loc):
        return False
    return None


def city_state(loc):
    m = re.search(rf"([A-Za-z .'-]+),\s*({_STATE_ABBR})\b", loc or "")
    if m:
        return f"{m.group(1).strip()}, {m.group(2)}"
    return None


# ---------- Work type ----------
def remote_type(hint, location, title, text):
    h = f"{hint} {location} {title}".lower()
    t = (text or "")[:6000].lower()
    if "hybrid" in h:
        return "Hybrid"
    if re.search(r"\bremote\b", h):
        return "Remote"
    if re.search(r"on-?site|in[- ]office", h):
        return "On-site"
    if re.search(r"\bhybrid\b", t):
        return "Hybrid"
    if re.search(r"fully remote|100% remote|remote (position|role|opportunity)|work from home|remote-first", t):
        return "Remote"
    if re.search(r"\b(on-?site|in[- ]office|in person)\b", t):
        return "On-site"
    return "Not stated"


def employment_type(hint, title, text):
    h = f"{hint} {title}".lower()
    t = (text or "")[:6000].lower()
    both = f"{h} {t}"
    if re.search(r"contract[- ]to[- ]hire|\bc2h\b|temp[- ]to[- ]perm|right[- ]to[- ]hire", both):
        return "Contract-to-hire"
    if re.search(r"\bcontract|\btemporary\b|\btemp\b|\bfreelance", h):
        return "Contract"
    if re.search(r"\bpart[- ]?time\b", h):
        return "Part-time"
    if re.search(r"full[- ]?time|fulltime|\bpermanent\b|\bregular\b", h):
        return "Full-time"
    if re.search(r"\b\d{1,2}\+?\s*(months?|mos?)\b[^.\n]{0,20}\bcontract|\bcontract (role|position|assignment|opportunity)|\bduration\s*:", t):
        return "Contract"
    if re.search(r"full[- ]time (position|role|employee|opportunity)|this is a full[- ]time", t):
        return "Full-time"
    return "Not stated"


# ---------- Dedupe keys ----------
_CO_SUFFIX = re.compile(r"\b(inc|llc|ltd|l\.l\.c|corp|corporation|co|company|plc|the|usa|us)\b\.?", re.I)


def norm_company(c):
    c = _CO_SUFFIX.sub(" ", (c or "").lower())
    return re.sub(r"[^a-z0-9]+", "", c)


def norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.sub(r"\s[-–|]\s.*(remote|hybrid|onsite|on-site|contract|w2|w-2|\b[a-z]{2}\b).*$", " ", t)
    t = re.sub(r"\bsr\b\.?", "senior", t)
    t = re.sub(r"\bjr\b\.?", "junior", t)
    t = re.sub(r"\b(iii|3)\b", "iii", t)
    t = re.sub(r"\b(ii|2)\b", "ii", t)
    t = re.sub(r"\b(w-?2|c2c|remote|hybrid|onsite|contract|job|position|opening)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


_NAME_TO_ABBR = {v.lower(): k for k, v in config.US_STATES.items()}


def norm_location(loc, remote):
    """State-level key: sources disagree on city names (Manhattan vs New York),
    so dedupe on the state. Same company + same title + same state = same job."""
    if remote == "Remote":
        return "remote"
    cs = city_state(loc)
    if cs:
        return cs[-2:].lower()
    m = re.search(rf"\b({_STATE_NAMES})\b", loc or "")
    if m:
        return _NAME_TO_ABBR[m.group(1).lower()].lower()
    return re.sub(r"[^a-z0-9]+", "", (loc or "").lower())[:40]


def dup_key(company, title, location, remote):
    return f"{norm_company(company)}|{norm_title(title)}|{norm_location(location, remote)}"
