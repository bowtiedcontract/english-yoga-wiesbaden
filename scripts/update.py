#!/usr/bin/env python3
"""Weekly updater for the English yoga schedule (index.html).

Fetches the next two weeks of sessions from the public Eversports schedule-widget
feeds, keeps only classes whose title marks them as English, and rewrites the
DAY_NOTES + CLASSES data (and LAST_UPDATED) inside the DATA block of index.html.

Python 3.9+ standard library only.

Usage:
  python3 scripts/update.py                  # update index.html in place
  python3 scripts/update.py --dry-run        # print the result, don't write
  python3 scripts/update.py --start 2026-09-28   # override the first date
  python3 scripts/update.py --discover balance-mainz   # list widget ids for a venue slug

Exit codes: 0 = all studios fetched fine. 1 = at least one studio failed (its previous
entries were kept and the file was still written), or nothing usable to publish.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "index.html")
WIDGET_API = "https://graphql-widget-master.production.eversports.cloud/api/graphql"
MARKET_API = "https://www.eversports.de/api/checkout"
UA = "Mozilla/5.0 (compatible; english-yoga-wiesbaden-updater/1.0)"

# ---------------------------------------------------------------------------
# Studios fetched from Eversports. "name" must match a STUDIOS[].name in index.html.
# widget = public "activity schedule" widget id, venue = Eversports venue id
# (a widget can cover several venues of one company, so we filter by venue).
# Find ids for a new studio with:  python3 scripts/update.py --discover <eversports-slug>
# ---------------------------------------------------------------------------
SOURCES = [
    {"name": "Studio 85 Hochheim", "widget": "3a5afe23-23fc-411a-af3d-22e3b116e422",
     "venue": "f5d32ccd-4db9-4a14-9281-d1b9db4e3654"},
    {"name": "Studio 85 Biebrich", "widget": "5fed6e2f-032a-437d-a211-2ad05afaa886",
     "venue": "4c58c9ff-08a0-4f44-89f7-30de302589e6"},
    {"name": "Balance Yoga Mainz", "widget": "4a240b6b-28e3-46e8-a8af-55b156a21bab",
     "venue": "5f3b1acc-69e4-11e8-bdc6-02bd505aa7b2"},
    {"name": "Yogaplus Mainz", "widget": "fbd65457-f905-4c14-ba1d-d49b397cb90c",
     "venue": "40bfbce8-4d02-4b47-a73b-8ed21884f732"},
]

# Studios without a feed: fixed weekly template (weekday 0=Mon ... 6=Sun).
TEMPLATES = [
    {"studio": "PRAXYS", "weekday": 1, "start": "18:30", "end": "19:30", "name": "Vinyasa",
     "level": "", "teacher": "", "lang": "English not confirmed", "type": "Yoga"},
    {"studio": "PRAXYS", "weekday": 3, "start": "18:00", "end": "19:00", "name": "Vinyasa",
     "level": "", "teacher": "", "lang": "English not confirmed", "type": "Yoga"},
]

# Public holidays in Hesse (HE) and Rhineland-Palatinate (RP) through 2027.
HOLIDAYS = {
    "2026-01-01": "New Year's Day", "2026-04-03": "Good Friday", "2026-04-06": "Easter Monday",
    "2026-05-01": "Labour Day", "2026-05-14": "Ascension Day", "2026-05-25": "Whit Monday",
    "2026-06-04": "Corpus Christi", "2026-10-03": "German Unity Day",
    "2026-11-01": "All Saints' Day (Rhineland-Palatinate only)",
    "2026-12-25": "Christmas Day", "2026-12-26": "Boxing Day (2nd Christmas Day)",
    "2027-01-01": "New Year's Day", "2027-03-26": "Good Friday", "2027-03-29": "Easter Monday",
    "2027-05-01": "Labour Day", "2027-05-06": "Ascension Day", "2027-05-17": "Whit Monday",
    "2027-05-27": "Corpus Christi", "2027-10-03": "German Unity Day",
    "2027-11-01": "All Saints' Day (Rhineland-Palatinate only)",
    "2027-12-25": "Christmas Day", "2027-12-26": "Boxing Day (2nd Christmas Day)",
}
HOLIDAY_TEXT = "{name} (public holiday) – classes may not run. Check before you go."

ENGLISH_RE = re.compile(r"\bENG\b|english|\bengl\b\.?|DE\s*/\s*ENG|bilingual", re.I)
BILINGUAL_RE = re.compile(r"DE\s*/\s*ENG|bilingual", re.I)
LEVELS = {"BEGINNER": "Beginner", "INTERMEDIATE": "Intermediate", "ADVANCED": "Advanced",
          "PROFESSIONAL": "Advanced", "ALL": "All levels"}

SCHEDULE_QUERY = """
query ActivityScheduleWidget($widgetId: ID!, $timeRange: TimeRangeInput, $first: Int, $after: Cursor) {
  widget(id: $widgetId) {
    __typename
    ... on WidgetActivitySchedule {
      activities(activityGroupPublicationStates: [ACTIVE, VIEW_ONLY], timeRange: $timeRange,
                 first: $first, after: $after, isArchived: false) {
        nodes {
          id name start end isCancelled
          activityGroup { name level category { name } sport { name } venue { id name } }
          teacher { name }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}"""


def post(url, payload, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Origin": "https://www.eversports.de",
        "Referer": "https://www.eversports.de/", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"])[:500])
    return data["data"]


def date_range(today, override=None):
    """Mon-Sat: today .. Sunday of next week. Sunday: tomorrow (Monday) .. the Sunday after next."""
    start = override or (today + dt.timedelta(days=1) if today.weekday() == 6 else today)
    end = start + dt.timedelta(days=6 - start.weekday() + 7)
    return start, end


def fetch_sessions(src, start, end):
    t0 = dt.datetime.combine(start, dt.time(0), BERLIN).astimezone(dt.timezone.utc)
    t1 = dt.datetime.combine(end + dt.timedelta(days=1), dt.time(0), BERLIN).astimezone(dt.timezone.utc)
    fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    nodes, after = [], None
    for _ in range(20):
        v = {"widgetId": src["widget"], "timeRange": {"start": fmt(t0), "end": fmt(t1)}, "first": 500}
        if after:
            v["after"] = after
        w = post(WIDGET_API, {"query": SCHEDULE_QUERY, "variables": v})["widget"]
        if not w or w.get("__typename") != "WidgetActivitySchedule":
            raise RuntimeError("widget not found or not a schedule widget")
        acts = w["activities"]
        nodes += acts["nodes"]
        if not acts["pageInfo"]["hasNextPage"]:
            break
        after = acts["pageInfo"]["endCursor"]
    return [n for n in nodes if n["activityGroup"]["venue"]["id"] == src["venue"]]


def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^Yoga\+\s*", "", t)
    m = re.match(r"^(YOGA|PILATES|REFORM(?:ER)?|STRENGTH)(?:\s*85)?\s*:\s*", t, re.I)
    if m:
        prefix = {"YOGA": "", "PILATES": "Pilates: ", "REFORM": "Reformer: ",
                  "REFORMER": "Reformer: ", "STRENGTH": "Strength: "}[m.group(1).upper()]
        t = prefix + t[m.end():]
    # repair a missing "(" e.g. "Fit Flow ENG)"
    if t.count(")") > t.count("("):
        t = re.sub(r"\s(\w[\w/]*\))$", r" (\1", t)
    # "FULL BODY REFORMER (engl.)" -> "Full Body Reformer (engl.)"
    base = re.split(r"\s\(", t, maxsplit=1)[0]
    if len(base) > 4 and base.upper() == base and re.search(r"[A-Z]{3}", base):
        t = base.title() + t[len(base):]
    return t


def class_type(raw_title, group):
    t = raw_title.upper()
    sport = (group.get("sport") or {}).get("name", "") + " " + (group.get("category") or {}).get("name", "")
    prefix = re.match(r"^\s*(YOGA|PILATES|REFORM(?:ER)?|STRENGTH)(?:\s*85)?\s*:", t)
    p = prefix.group(1) if prefix else ""
    if p.startswith("REFORM") or "REFORMER" in sport.upper():
        return "Reformer Pilates"
    if p == "STRENGTH":
        return "Strength"
    if p == "YOGA" or t.startswith("YOGA+"):
        return "Yoga"
    if p == "PILATES":
        return "Pilates"
    if "PILATES" in sport.upper() and "YOGA" not in t:
        return "Pilates"
    if "STRENGTH" in sport.upper() and "YOGA" not in t:
        return "Strength"
    return "Yoga"


def to_entry(n, studio):
    g = n["activityGroup"]
    raw = (n.get("name") or g.get("name") or "").strip()
    s = dt.datetime.fromisoformat(n["start"]).astimezone(BERLIN)
    e = dt.datetime.fromisoformat(n["end"]).astimezone(BERLIN) if n.get("end") else None
    entry = {
        "date": s.strftime("%Y-%m-%d"), "start": s.strftime("%H:%M"), "end": e.strftime("%H:%M") if e else "",
        "studio": studio, "name": clean_title(raw), "level": LEVELS.get(g.get("level") or "", ""),
        "teacher": ((n.get("teacher") or {}).get("name") or "").strip(),
        "lang": "DE/ENG" if BILINGUAL_RE.search(raw) else "ENG", "type": class_type(raw, g),
    }
    if n.get("isCancelled"):
        entry["cancelled"] = True
    return entry, raw


# ---------------------------------------------------------------------------
# index.html reading / writing
# ---------------------------------------------------------------------------
def js_object_list(src):
    """Parse the simple JS object-literal array used for CLASSES (unquoted keys, JSON values)."""
    out, i, n = [], 0, len(src)
    while True:
        i = src.find("{", i)
        if i < 0:
            break
        j, depth, in_str, buf = i, 0, False, []
        while j < n:
            c = src[j]
            if in_str:
                buf.append(c)
                if c == "\\":
                    buf.append(src[j + 1]); j += 1
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True; buf.append(c)
                elif c == "{":
                    depth += 1; buf.append(c)
                elif c == "}":
                    depth -= 1; buf.append(c)
                    if depth == 0:
                        break
                else:
                    buf.append(c)
            j += 1
        text = "".join(buf)
        # quote bare keys (only outside strings: keys follow "{" or "," )
        parts, k, quoted = re.split(r'("(?:\\.|[^"\\])*")', text), 0, []
        for idx, p in enumerate(parts):
            quoted.append(p if idx % 2 else re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', p))
        out.append(json.loads("".join(quoted)))
        i = j + 1
    return out


def read_previous(html):
    m = re.search(r"const CLASSES = \[(.*?)\n\];", html, re.S)
    if not m:
        raise SystemExit("CLASSES array not found in index.html")
    body = re.sub(r"^\s*//.*$", "", m.group(1), flags=re.M)
    return js_object_list(body)


def render_classes(classes):
    keys = ["date", "start", "end", "studio", "name", "level", "teacher", "lang", "type"]
    lines = []
    for c in classes:
        parts = ["%s:%s" % (k, json.dumps(c.get(k, ""), ensure_ascii=False)) for k in keys]
        if c.get("cancelled"):
            parts.append("cancelled:true")
        lines.append("  { " + ", ".join(parts) + " }")
    return "const CLASSES = [\n" + ",\n".join(lines) + "\n];"


def render_notes(start, end):
    notes = {d: HOLIDAY_TEXT.format(name=name) for d, name in sorted(HOLIDAYS.items())
             if start.isoformat() <= d <= end.isoformat()}
    if not notes:
        return "const DAY_NOTES = {};"
    return "const DAY_NOTES = {\n" + ",\n".join(
        "  %s: %s" % (json.dumps(d), json.dumps(t, ensure_ascii=False)) for d, t in notes.items()) + "\n};"


def discover(slug):
    import html as _h
    req = urllib.request.Request("https://www.eversports.de/s/" + slug, headers={"User-Agent": UA})
    page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    m = re.search(r'"__typename":"Venue","id":"([0-9a-f-]{36})","name":"([^"]*)","slug":"%s"' % re.escape(slug), page)
    if not m:
        raise SystemExit("venue id not found on the page")
    vid = m.group(1)
    print("venue", vid, _h.unescape(m.group(2)))
    q = ('query($v: ID!){ venue(venueId:$v){ company { id name widgets { __typename '
         '... on WidgetActivitySchedule { id } } } } }')
    comp = post(MARKET_API, {"query": q, "variables": {"v": vid}})["venue"]["company"]
    print("company", comp["id"], comp["name"])
    vq = "query W($id: ID!){ widget(id:$id){ ... on WidgetActivitySchedule { venues { nodes { id name } } } } }"
    for w in comp["widgets"]:
        if w.get("id"):
            vs = post(WIDGET_API, {"query": vq, "variables": {"id": w["id"]}})["widget"]["venues"]["nodes"]
            names = [x["name"] for x in vs]
            if any(x["id"] == vid for x in vs):
                print("widget", w["id"], "venues:", ", ".join(names))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", help="YYYY-MM-DD first date (default: today, or tomorrow on Sundays)")
    ap.add_argument("--file", default=INDEX)
    ap.add_argument("--discover", metavar="SLUG")
    a = ap.parse_args()
    if a.discover:
        return discover(a.discover)

    now = dt.datetime.now(BERLIN)
    start, end = date_range(now.date(), dt.date.fromisoformat(a.start) if a.start else None)
    print(f"Range: {start} .. {end}")
    html = open(a.file, encoding="utf-8").read()
    previous = read_previous(html)

    failed, classes = [], []
    for src in SOURCES:
        prev = [c for c in previous if c["studio"] == src["name"]]
        try:
            sessions = fetch_sessions(src, start, end)
            if not sessions and prev:
                raise RuntimeError("feed returned 0 sessions (previously had entries)")
            got = []
            for n in sessions:
                entry, raw = to_entry(n, src["name"])
                if ENGLISH_RE.search(raw):
                    got.append(entry)
            print(f"  {src['name']}: {len(sessions)} sessions, {len(got)} English")
            classes += got
        except Exception as e:  # keep previous data for this studio
            failed.append(src["name"])
            keep = [c for c in prev if c["date"] >= start.isoformat()] or prev
            print(f"  ERROR {src['name']}: {e} -> keeping {len(keep)} previous entries", file=sys.stderr)
            classes += keep

    d = start
    while d <= end:
        for t in TEMPLATES:
            if d.weekday() == t["weekday"]:
                classes.append({"date": d.isoformat(), **{k: v for k, v in t.items() if k != "weekday"}})
        d += dt.timedelta(days=1)

    classes.sort(key=lambda c: (c["date"], c["start"], c["studio"], c["name"]))
    fed = [c for c in classes if c["studio"] in {s["name"] for s in SOURCES}]
    if not fed:
        print("Refusing to publish: no classes from any studio.", file=sys.stderr)
        return 1

    new = re.sub(r"const CLASSES = \[.*?\n\];", lambda m: render_classes(classes), html, count=1, flags=re.S)
    new = re.sub(r"const DAY_NOTES = \{.*?\};", lambda m: render_notes(start, end), new, count=1, flags=re.S)
    stamp = now.strftime("%a ") + str(now.day) + now.strftime(" %b %Y, %H:%M") + " (Berlin time)"
    new = re.sub(r'const LAST_UPDATED = "[^"]*";', lambda m: 'const LAST_UPDATED = "%s";' % stamp, new, count=1)

    if a.dry_run:
        print(render_notes(start, end)); print(render_classes(classes))
    else:
        with open(a.file, "w", encoding="utf-8") as f:
            f.write(new)
        print(f"Wrote {len(classes)} classes to {os.path.relpath(a.file)}")
    if failed:
        print("FAILED studios (previous data kept): " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
