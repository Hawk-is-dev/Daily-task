"""Pure logic (no Telegram / DB). State is a plain JSON-able dict."""
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
START_DATE = date(2026, 11, 1)  # first plan is sent at 12:00 AM on this day
END_DATE = date(2026, 12, 31)
FREE_MIN = 15
LOCK_ENABLED = os.getenv("LOCK_ENABLED", "1") != "0"
SUBJECTS = [("M", "Maths", "📘"), ("P", "Physics", "⚡"), ("C", "Chemistry", "🧪"), ("E", "English", "📖")]
SNAME = {c: n for c, n, _ in SUBJECTS}
SEMOJI = {c: e for c, _, e in SUBJECTS}
PER_DAY = {"M": 2, "P": 2, "C": 2, "E": 1}  # fixed new lectures per day (Plan B)
PREDONE = ["E001"]  # English Lec 1 already finished before the bot


@dataclass(frozen=True)
class Lec:
    id: str
    subj: str
    chapter: str
    name: str
    short: str
    dur: int  # seconds


def _sec(s):
    h, m, x = (int(p) for p in s.split(":"))
    return h * 3600 + m * 60 + x


def _load():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lectures.txt")
    lecs, subj, chap, n, punch, gal, idx = [], None, None, 0, 0, 0, 0
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line[0] == "@":
            subj, idx, gal = line[1:].strip(), 0, 0
            continue
        if line[0] == "#":
            chap, n, punch = line[1:].strip(), 0, 0
            continue
        body, dur = line.rsplit("|", 1)
        tag, text = line[0], body[1:].strip()
        if tag == "~":
            punch += 1
            name, short = f"NCERT Punch {punch:02d} : {text}", f"{chap} · Punch {punch:02d}"
        elif tag == "^":
            gal += 1
            name, short = f"Shourya's Galaxy {gal:02d} : {text}", f"Galaxy {gal:02d}"
        elif tag == "=":
            name, short = text, text.split(" : ")[0]
        else:
            n += 1
            name, short = f"{chap} {n:02d} : {body.strip()}", f"{chap} {n:02d}"
        idx += 1
        lecs.append(Lec(f"{subj}{idx:03d}", subj, chap, name, short, _sec(dur)))
    return lecs


LECS = _load()
LEC = {l.id: l for l in LECS}
BY_SUBJ = {c: [l for l in LECS if l.subj == c] for c, _, _ in SUBJECTS}
CHAPTERS = {}
for _l in LECS:
    CHAPTERS.setdefault(_l.subj, {}).setdefault(_l.chapter, []).append(_l.id)


# ---------- time helpers ----------
def now_ist():
    return datetime.now(IST)


def iso(dt):
    return dt.isoformat()


def parse(s):
    return datetime.fromisoformat(s)


def next_midnight(dt):
    return datetime.combine(dt.date() + timedelta(days=1), time(0), IST)


def days_left(today):
    return max(1, (END_DATE - today).days + 1)


# ---------- state ----------
def new_state():
    return {"v": 1, "owner": None, "start": None, "day": None, "plan": [], "assigned": {},
            "done": {}, "open": {}, "start_remaining": {}, "free_until": None, "last_tick": None,
            "history": {}, "alerted": []}


def remaining(st, subj):
    return [l for l in BY_SUBJ[subj] if l.id not in st["done"]]


def remaining_counts(st):
    return {c: len(remaining(st, c)) for c, _, _ in SUBJECTS}


def build_plan(st, today):
    """Fixed daily target (PER_DAY) of new lectures + ALL pending lectures (planned earlier, not done).
    Extra lectures never change how many new lectures arrive tomorrow; they only finish the syllabus sooner."""
    plan = []
    for c, _, _ in SUBJECTS:
        rem = remaining(st, c)
        pend = [l for l in rem if l.id in st["assigned"]]
        fresh = [l for l in rem if l.id not in st["assigned"]]
        plan += [l.id for l in pend] + [l.id for l in fresh[:PER_DAY[c]]]
    return plan


def is_complete(st):
    return all(i in st["done"] for i in st["plan"])


def _close_day(st):
    d, plan = st["day"], st["plan"]
    planned = {c: sum(1 for i in plan if LEC[i].subj == c) for c, _, _ in SUBJECTS}
    done = {c: sum(1 for i in plan if LEC[i].subj == c and i in st["done"]) for c, _, _ in SUBJECTS}
    st["history"][d] = {"open": st["open"], "close": remaining_counts(st), "planned": planned,
                        "done": done, "complete": is_complete(st)}


def rollover(st, now):
    """Start a new day if needed. Returns True when a new plan was created."""
    today = now.date()
    if st["day"] == today.isoformat():
        return False
    if not st["day"] and today < START_DATE:
        return False  # not started yet
    if st["day"]:
        _close_day(st)
        d = date.fromisoformat(st["day"]) + timedelta(days=1)
        rc = remaining_counts(st)
        while d < today:  # days the bot was off / nothing happened
            z = {c: 0 for c in rc}
            st["history"][d.isoformat()] = {"open": rc, "close": rc, "planned": z, "done": z, "complete": False}
            d += timedelta(days=1)
    else:
        for i in PREDONE:
            st["done"][i] = iso(now)
        st["start"] = today.isoformat()
        st["start_remaining"] = remaining_counts(st)
    st["day"] = today.isoformat()
    st["plan"] = build_plan(st, today)
    for i in st["plan"]:
        st["assigned"].setdefault(i, today.isoformat())
    st["open"] = remaining_counts(st)
    st["free_until"] = None
    return True


def preview_state(now):
    """Throw-away state (never saved) used to show what Day 1 will look like before the bot starts."""
    st = new_state()
    for i in PREDONE:
        st["done"][i] = iso(now)
    st["start"] = now.date().isoformat()
    st["start_remaining"] = remaining_counts(st)
    st["day"] = st["start"]
    st["plan"] = build_plan(st, now.date())
    st["open"] = remaining_counts(st)
    return st


def pending_ids(st):
    return [i for i in st["plan"] if i not in st["done"] and st["assigned"].get(i, st["day"]) < st["day"]]


# ---------- lock / tick ----------
def locked(st, now):
    if not LOCK_ENABLED or not st.get("day"):
        return False
    if st["day"] != now.date().isoformat():
        return True  # new day, plan not generated yet
    if is_complete(st):
        return False
    fu = st.get("free_until")
    return not (fu and now < parse(fu))


def _too_soon(st, lec, now):
    lt = st.get("last_tick")
    if lt:
        lt = parse(lt)
        if lt.date() == now.date():  # first tick of the day is never checked
            earliest = lt + timedelta(minutes=FREE_MIN, seconds=lec.dur)
            if now < earliest:
                return {"ok": False, "why": "too_soon", "earliest": earliest, "since": now - lt, "lec": lec}
    return None


def try_tick(st, lid, now):
    if lid not in st["plan"]:
        return {"ok": False, "why": "not_in_plan"}
    if lid in st["done"]:
        return {"ok": False, "why": "already"}
    lec = LEC[lid]
    bad = _too_soon(st, lec, now)
    if bad:
        return bad
    st["done"][lid] = iso(now)
    st["last_tick"] = iso(now)
    if is_complete(st):
        st["free_until"] = iso(next_midnight(now))
    else:
        fu = st.get("free_until")
        base = max(now, parse(fu)) if fu else now
        st["free_until"] = iso(base + timedelta(minutes=FREE_MIN))
    return {"ok": True, "complete": is_complete(st), "lec": lec}


def next_fresh(st, subj):
    """Next lecture of a subject that is neither done nor planned yet."""
    return next((l for l in BY_SUBJ[subj] if l.id not in st["done"] and l.id not in st["assigned"]), None)


def try_extra(st, lid, now):
    """Extra lecture beyond the plan: only after today's task is complete. Never changes future counts."""
    if not st.get("day") or not is_complete(st):
        return {"ok": False, "why": "plan_first"}
    lec = LEC.get(lid)
    nxt = next_fresh(st, lec.subj) if lec else None
    if not nxt or nxt.id != lid:
        return {"ok": False, "why": "not_next"}
    bad = _too_soon(st, lec, now)
    if bad:
        return bad
    st["done"][lid] = iso(now)
    st["last_tick"] = iso(now)
    return {"ok": True, "lec": lec}


# ---------- chapters ----------
def chapter_finished(st, lid):
    """If this tick completed a chapter, return (chapter, next_chapter or None)."""
    lec = LEC[lid]
    if lec.chapter == SNAME[lec.subj]:
        return None
    chs = CHAPTERS[lec.subj]
    if not all(i in st["done"] for i in chs[lec.chapter]):
        return None
    key = f"{lec.subj}:{lec.chapter}"
    if key in st["alerted"]:
        return None
    st["alerted"].append(key)
    names = list(chs)
    nxt = names[names.index(lec.chapter) + 1] if names.index(lec.chapter) + 1 < len(names) else None
    return lec.chapter, nxt


# ---------- stats ----------
def total_done(st):
    return len(st["done"])


def streak(st):
    s, d = 0, date.fromisoformat(st["day"]) - timedelta(days=1) if st.get("day") else None
    while d and st["history"].get(d.isoformat(), {}).get("complete"):
        s += 1
        d -= timedelta(days=1)
    if st.get("day") and st["plan"] and is_complete(st):
        s += 1
    return s


def day_index(st, today):
    return (today - date.fromisoformat(st["start"])).days + 1


def pace(st, now):
    """Lectures behind (+) / ahead (-) of the fixed schedule, counted up to the end of yesterday."""
    start = date.fromisoformat(st["start"])
    days = max(0, (now.date() - start).days)
    expected = sum(min(st["start_remaining"][c], PER_DAY[c] * days) for c in PER_DAY)
    done_since = sum(st["start_remaining"].values()) - sum(remaining_counts(st).values())
    return expected - done_since


def projected_finish(st, today):
    """Date the syllabus ends if you keep doing the daily target."""
    d = max(math.ceil(len(remaining(st, c)) / PER_DAY[c]) for c in PER_DAY)
    return today + timedelta(days=max(d - 1, 0))


def fdur(sec):
    sec = int(round(sec / 60)) * 60
    h, m = divmod(sec // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"
