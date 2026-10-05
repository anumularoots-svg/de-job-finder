"""Classify a job from its own posting text only. Never guess.

W-2 status (one of):
  W2_CONFIRMED  posting explicitly says W-2 / W2
  DIRECT_FT     posted on the employer's own job board as full-time, no W-2
                wording, no contract / C2C wording (employees get a W-2, but
                the posting does not say so; kept separate from confirmed)
  C2C_1099      posting accepts only C2C / corp-to-corp / 1099 / independent
                contractor (and does not mention W-2)
  UNKNOWN       anything else. Unknown is never treated as W-2.
"""
import re

from . import config

NEG = r"(?:\bno\b|\bnot\b|\bnon\b|n't|\bwithout\b|\bcannot\b|\bcan not\b|\bexclud\w*|\bexcept\b|\bnor\b)"

C2C_TERMS = re.compile(r"\bc2c\b|\bcorp[\s-]*(?:to|2)[\s-]*corp\b|\bcorp[\s-]to[\s-]corp\b|\b1099\b|\bindependent contractor\b|\bthird[\s-]part(?:y|ies)\b", re.I)
W2_TERM = re.compile(r"\bw[\s-]?2\b", re.I)
W2_ONLY = re.compile(r"\bw[\s-]?2\s*(?:only|candidates only|basis only|employees? only)|\bonly\s+(?:on\s+)?w[\s-]?2\b", re.I)


def _snippet(text, start, end, pad=35):
    """Short quote around a match, cut at word and sentence edges."""
    a, b = max(0, start - pad), min(len(text), end + pad)
    for stop in ".\n;":
        i = text.rfind(stop, a, start)
        if i != -1:
            a = max(a, i + 1)
        j = text.find(stop, end, b)
        if j != -1:
            b = min(b, j + (1 if stop == "." else 0))
    if a > 0 and not text[a - 1] in " \n.;":
        a = text.find(" ", a, start) + 1 or a
    if b < len(text) and text[b - 1] not in ".":
        k = text.rfind(" ", end, b)
        b = k if k != -1 else b
    s = " ".join(text[a:b].split())
    return s[:1].upper() + s[1:]


def _mentions(regex, text):
    """Split matches into (positive, negated) phrases, with a short evidence snippet."""
    pos, neg = [], []
    for m in regex.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30]
        snippet = _snippet(text, m.start(), m.end())
        negated = re.search(NEG + r"[^.;:\n]{0,22}$", before, re.I) or \
            re.match(r"\s*(?:is |are )?(?:not|n't)\s+(?:accepted|allowed|considered|available|entertained|possible)", after, re.I)
        (neg if negated else pos).append(snippet)
    return pos, neg


def w2_status(text, employment, is_direct):
    evidence = []
    w2_pos, w2_neg = _mentions(W2_TERM, text)
    c2c_pos, c2c_neg = _mentions(C2C_TERMS, text)
    # "third party" alone is not a C2C signal unless negated ("no third parties" = W2-leaning)
    c2c_pos = [s for s in c2c_pos if not re.search(r"third[\s-]part", s, re.I) or re.search(r"c2c|corp|1099", s, re.I)]
    if W2_ONLY.search(text):
        c2c_pos = []
    c2c_status = "ACCEPTED" if c2c_pos else ("NOT_ACCEPTED" if c2c_neg or W2_ONLY.search(text) else "NOT_STATED")

    if w2_pos:
        evidence.append(w2_pos[0])
        if c2c_pos:
            evidence.append(c2c_pos[0])
        return "W2_CONFIRMED", c2c_status, evidence
    if c2c_pos:
        evidence.append(c2c_pos[0])
        return "C2C_1099", c2c_status, evidence
    if is_direct and employment == "Full-time" and not re.search(r"\bcontract(or)?\b", text[:6000], re.I):
        return "DIRECT_FT", c2c_status, ["Full-time role on the employer's own job board; W-2 not stated"]
    if w2_neg:
        evidence.append(w2_neg[0])
    return "UNKNOWN", c2c_status, evidence


SPONSOR_NO = re.compile(
    r"no (?:visa |h-?1b )?sponsorship|(?:not|n't|unable|cannot|can not|won't|will not|do not|does not|are not able to|is not able to)\s+"
    r"(?:to\s+)?(?:be able to\s+)?(?:offer\s+|provide\s+)?(?:visa\s+|immigration\s+)?sponsor|not eligible for (?:visa |immigration )?sponsorship|"
    r"without (?:the need for |requiring |requirement of )?(?:current or future |now or in the future |future |any )?(?:visa |employer |immigration )?sponsorship|"
    r"sponsorship (?:is |will )?not (?:be )?(?:available|offered|provided)|"
    r"\b(?:us|u\.s\.) citizens? only|must be a (?:us|u\.s\.) citizen|\bgc (?:holders? )?only|\busc only|\busc\s*/\s*gc\b|\bgc\s*/\s*usc\b|"
    r"green card holders? only|citizens? or green card holders? only",
    re.I,
)
SPONSOR_YES = re.compile(
    r"(?:visa |h-?1b )?sponsorship (?:is )?(?:available|provided|offered|possible)|will sponsor|willing to sponsor|open to sponsor|"
    r"we (?:do )?sponsor|h-?1b (?:transfer|sponsorship)s? (?:is |are )?(?:available|accepted|welcome|considered)|opt/?cpt (?:candidates )?(?:welcome|accepted)",
    re.I,
)


def sponsorship(text):
    m = SPONSOR_NO.search(text)
    if m:
        return "NOT_AVAILABLE", m.group(0)
    m = SPONSOR_YES.search(text)
    if m:
        return "AVAILABLE", m.group(0)
    return "UNKNOWN", ""


_WORDNUM = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split())}
_EXP = re.compile(
    r"(?:(?:minimum|at least|min\.?)\s+(?:of\s+)?)?\b(\d{1,2}|" + "|".join(_WORDNUM) + r")\s*(?:\(\d+\)\s*)?\+?\s*"
    r"(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b(?:[^.\n]{0,40}?)\b(?:experience|exp\b)",
    re.I,
)


def experience_min(text):
    m = _EXP.search(text or "")
    if not m:
        m = re.search(r"experience\s*[:\-]?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text or "", re.I)
        if not m:
            return None
    raw = m.group(1).lower()
    n = int(raw) if raw.isdigit() else _WORDNUM.get(raw)
    return n if n is not None and 0 <= n <= 20 else None


_SKILL_RX = {}
for s in config.SKILLS:
    pat = re.escape(s).replace(r"\ ", r"[\s-]?")
    _SKILL_RX[s] = re.compile(rf"(?<![A-Za-z]){pat}(?![A-Za-z])", re.I)
_SKILL_RX["ADF"] = re.compile(r"(?<![A-Za-z])ADF(?![A-Za-z])|azure data factory", re.I)
_SKILL_RX["Glue"] = re.compile(r"aws glue|\bglue (?:jobs?|etl|catalog)", re.I)


def skills(text):
    return [s for s, rx in _SKILL_RX.items() if rx and rx.search(text or "")]


def classify(title, description, employment, is_direct):
    text = f"{title}\n{description or ''}"
    w2, c2c, ev = w2_status(text, employment, is_direct)
    sp, sp_note = sponsorship(text)
    return dict(
        w2_status=w2, c2c_status=c2c, evidence=ev[:2],
        sponsorship=sp, sponsorship_note=sp_note,
        experience_min=experience_min(text), skills=skills(text),
    )
