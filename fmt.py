"""Message formatting. Only two fonts: italic-bold headings (𝐻𝑒𝑎𝑑𝑖𝑛𝑔) and small-caps body (ʙᴏᴅʏ)."""
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import core
from core import LEC, SEMOJI, SNAME, SUBJECTS, fdur

_SC = dict(zip("abcdefghijklmnoprstuvwyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘʀsᴛᴜᴠᴡʏᴢ"))
_SC_T = str.maketrans(_SC)
_IT = {}
for _i in range(26):
    _IT[chr(65 + _i)] = chr(0x1D434 + _i)
    _IT[chr(97 + _i)] = chr(0x1D44E + _i)
_IT["h"] = "ℎ"
_IT_T = str.maketrans(_IT)

esc = html.escape


def sb(t):
    """body text: small caps (escaped)"""
    return esc(str(t).lower().translate(_SC_T), quote=False)


def hd(t):
    """heading: bold italic (escaped)"""
    return "<b>" + esc(str(t).translate(_IT_T), quote=False) + "</b>"


def bar(frac, n=10):
    k = round(max(0.0, min(1.0, frac)) * n)
    return "▰" * k + "▱" * (n - k)


def tm(dt):
    return dt.astimezone(core.IST).strftime("%I:%M %p").lstrip("0")


def _lec_block(lid, st, mark):
    l = LEC[lid]
    return f"{mark} {sb(l.name)}\n      ⏱ {sb(fdur(l.dur))}"


# ---------- message 1: today's plan ----------
def plan_text(st, now):
    k, n = core.day_index(st, now.date())
    plan, pend = st["plan"], set(core.pending_ids(st))
    out = [f"{hd(chr(0x1F4CB) + ' Today' + chr(39) + 's Plan')}\n{sb(f'day {k} of {n} · {core.days_left(now.date())} days left')}"]
    prev = st["history"].get((now.date() - core.timedelta(days=1)).isoformat())
    if prev:
        pl, dn = sum(prev["planned"].values()), sum(prev["done"].values())
        out.append(sb(f"yesterday: {dn}/{pl} lectures " + ("✅" if prev["complete"] else "❌")))
    total = 0
    if not plan:
        out.append(sb("syllabus complete 🎉 nothing left to study."))
    for c, nm, em in SUBJECTS:
        ids = [i for i in plan if LEC[i].subj == c]
        if not ids:
            continue
        secs = sum(LEC[i].dur for i in ids)
        total += secs
        body = "\n\n".join(_lec_block(i, st, "🔁" if i in pend else "▫️") for i in ids)
        out.append(f"{em} {hd(nm)} · {sb(f'{len(ids)} lecture' + ('s' if len(ids) > 1 else ''))} · {sb(fdur(secs))}\n<blockquote>{body}</blockquote>")
    if plan:
        foot = f"total: {len(plan)} lectures · {fdur(total)}"
        if pend:
            foot += f"\n🔁 = pending from earlier ({len(pend)})"
        out.append(sb(foot))
    return "\n\n".join(out)


# ---------- message 2: tick checklist ----------
def checklist_text(st):
    done = sum(1 for i in st["plan"] if i in st["done"])
    n = len(st["plan"])
    head = f"{hd('✅ Tick Your Lectures')}\n{sb('tap a lecture after you finish it.')}\n\n{bar(done / n if n else 1)} {sb(f'{done}/{n}')}"
    return head


def checklist_kb(st):
    pend = set(core.pending_ids(st))
    rows = []
    for i in st["plan"]:
        l = LEC[i]
        box = "✅" if i in st["done"] else "☐"
        mark = "🔁 " if i in pend and i not in st["done"] else ""
        rows.append([InlineKeyboardButton(f"{box} {mark}{SEMOJI[l.subj]} {l.short} · {fdur(l.dur)}"[:60], callback_data=f"t:{i}")])
    return InlineKeyboardMarkup(rows)


# ---------- tick result ----------
def tick_text(st, now, lid, res):
    l = LEC[lid]
    done = sum(1 for i in st["plan"] if i in st["done"])
    n = len(st["plan"])
    out = [f"{hd('✅ Lecture Complete')}\n{SEMOJI[l.subj]} {sb(l.name)}\n⏱ {sb(fdur(l.dur))}"]
    out.append(f"{bar(done / n)} {sb(f'{done}/{n} today')}")
    subj_ids = [i for i in st["plan"] if LEC[i].subj == l.subj]
    if all(i in st["done"] for i in subj_ids) and not res["complete"]:
        out.append(sb(f"🎉 {SNAME[l.subj]} is done for today!"))
    if res["complete"]:
        out.append(f"{hd('🏆 Today' + chr(39) + 's Task Complete')}\n{sb('chatting is free until 12:00 am.')}\n{sb(f'🔥 streak: {core.streak(st)} days')}")
    else:
        fu = core.parse(st["free_until"])
        nxt = next((i for i in st["plan"] if i not in st["done"]), None)
        out.append(sb(f"🔓 free chatting until {tm(fu)}"))
        if nxt:
            out.append(sb(f"next: {LEC[nxt].short} (⏱ {fdur(LEC[nxt].dur)})"))
    return "\n\n".join(out)


def reject_text(res):
    l = res["lec"]
    since = fdur(res["since"].total_seconds())
    return (f"❌ Tick rejected\n{l.short} is {fdur(l.dur)} long.\n"
            f"Only {since} passed since your last tick (+{core.FREE_MIN}m free time).\n"
            f"Try again after {tm(res['earliest'])}.")


def chapter_text(st, chapter, nxt, subj):
    t = f"{hd('📚 Chapter Complete')}\n{SEMOJI[subj]} {sb(chapter)}"
    t += f"\n\n➡️ {sb('next chapter: ' + nxt)}" if nxt else f"\n\n🎓 {sb(SNAME[subj] + ' is fully complete!')}"
    return t


# ---------- other commands ----------
def pending_text(st):
    ids = core.pending_ids(st)
    if not ids:
        return f"{hd('🔁 Pending')}\n\n{sb('nothing pending 🎉')}"
    body = "\n\n".join(_lec_block(i, st, "🔁") for i in ids)
    return f"{hd('🔁 Pending')}\n{sb(f'{len(ids)} lectures from earlier days')}\n\n<blockquote>{body}</blockquote>"


def progress_text(st, now):
    plan = st["plan"]
    done = sum(1 for i in plan if i in st["done"])
    rows = [f"{hd('📈 Today' + chr(39) + 's Progress')}\n\n{bar(done / len(plan) if plan else 1)} {sb(f'{done}/{len(plan)}')}"]
    for c, nm, em in SUBJECTS:
        ids = [i for i in plan if LEC[i].subj == c]
        if ids:
            d = sum(1 for i in ids if i in st["done"])
            rows.append(f"{em} {sb(nm)}  {bar(d / len(ids), 8)} {sb(f'{d}/{len(ids)}')}")
    left = [i for i in plan if i not in st["done"]]
    tail = sb(f"time left to watch: {fdur(sum(LEC[i].dur for i in left))}") if left else ""
    return rows[0] + "\n\n" + "\n".join(rows[1:]) + ("\n\n" + tail if tail else "")


def countdown_text(st, now):
    end = core.datetime.combine(core.END_DATE + core.timedelta(days=1), core.time(0), core.IST)
    left = end - now
    d, h = left.days, left.seconds // 3600
    tot = len(core.LECS)
    done = core.total_done(st)
    out = [f"{hd('⏳ Countdown')}\n{sb(f'{d} days {h} hours left until 31 dec')}",
           f"{bar(done / tot, 12)} {sb(f'{done / tot * 100:.1f}% syllabus done')}\n{sb(f'{done}/{tot} lectures')}"]
    for c, nm, em in SUBJECTS:
        t = len(core.BY_SUBJ[c])
        dn = t - len(core.remaining(st, c))
        out.append(f"{em} {sb(nm)}  {bar(dn / t, 8)} {sb(f'{dn}/{t}')}")
    secs_left = sum(l.dur for l in core.LECS if l.id not in st["done"])
    out.append(sb(f"hours of lectures left: {fdur(secs_left)}"))
    b = core.pace(st, now)
    status = "on track ✅" if b <= 1 else (f"a bit behind ⚠️ ({b:.0f} lectures)" if b <= 6 else f"far behind 🚨 ({b:.0f} lectures)")
    out.append(sb(f"status: {status}"))
    return "\n\n".join([out[0], out[1], "\n".join(out[2:6]), "\n".join(out[6:])])


def week_text(st, now):
    rows = []
    for k in range(6, -1, -1):
        d = (now.date() - core.timedelta(days=k)).isoformat()
        h = st["history"].get(d)
        if d == st["day"]:
            pl = len(st["plan"])
            dn = sum(1 for i in st["plan"] if i in st["done"])
            ok = "…" if not core.is_complete(st) else "✅"
        elif h:
            pl, dn, ok = sum(h["planned"].values()), sum(h["done"].values()), "✅" if h["complete"] else "❌"
        else:
            continue
        rows.append(f"{d[5:]}  {dn:>2}/{pl:<2} {ok}")
    body = "\n".join(rows) if rows else "no data yet"
    return f"{hd('🗓 Weekly Report')}\n\n<pre>{esc(body)}</pre>\n{sb(f'🔥 streak: {core.streak(st)} days')}"


def lock_text(st, now):
    if not core.LOCK_ENABLED:
        return f"{hd('🔓 Lock')}\n\n{sb('lock is disabled (LOCK_ENABLED=0).')}"
    if not core.locked(st, now):
        if core.is_complete(st) and st.get("day"):
            return f"{hd('🔓 Unlocked')}\n\n{sb('today' + chr(39) + 's task is complete. groups are free until 12:00 am.')}"
        fu = core.parse(st["free_until"]) if st.get("free_until") else None
        return f"{hd('🔓 Unlocked')}\n\n{sb(f'free chatting until {tm(fu)}' if fu else 'bot not started yet.')}"
    nxt = next((i for i in st["plan"] if i not in st["done"]), None)
    return f"{hd('🔒 Locked')}\n\n{sb('group messages are deleted until you tick the next lecture.')}\n{sb('next: ' + LEC[nxt].short + ' (' + fdur(LEC[nxt].dur) + ')') if nxt else ''}"


HELP = (f"{hd('📖 Commands')}\n\n"
        "/today — tick your lectures\n/plan — today's detailed plan\n/pending — pending lectures\n"
        "/progress — today's progress\n/countdown — days left &amp; syllabus %\n/chart — charts (week, month, maths…)\n"
        "/week — weekly report\n/streak — current streak\n/lockstatus — chat lock status\n/help — this menu")
