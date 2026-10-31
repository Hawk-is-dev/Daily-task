"""Trading-style charts: daily candles (lectures remaining) + volume bars (lectures done)."""
import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import core  # noqa: E402

BG, GRID, TXT, UP, DOWN = "#131722", "#2a2e39", "#d1d4dc", "#26a69a", "#ef5350"


def _rows(st, subj):
    codes = [subj] if subj else [c for c, _, _ in core.SUBJECTS]
    rows = []
    for d in sorted(st["history"]):
        h = st["history"][d]
        rows.append((date.fromisoformat(d), sum(h["open"][c] for c in codes), sum(h["close"][c] for c in codes),
                     sum(h["planned"][c] for c in codes), sum(h["done"][c] for c in codes), h["complete"]))
    if st.get("day"):
        plan = [core.LEC[i] for i in st["plan"] if core.LEC[i].subj in codes]
        rows.append((date.fromisoformat(st["day"]), sum(st["open"][c] for c in codes),
                     sum(len(core.remaining(st, c)) for c in codes), len(plan),
                     sum(1 for l in plan if l.id in st["done"]), core.is_complete(st)))
    return rows


def make_chart(st, subj=None, last=None):
    rows = _rows(st, subj)
    if last:
        rows = rows[-last:]
    if not rows:
        return None
    codes = [subj] if subj else [c for c, _, _ in core.SUBJECTS]
    s0 = sum(st["start_remaining"][c] for c in codes)
    start = date.fromisoformat(st["start"])
    n = (core.END_DATE - start).days + 1
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    fig.patch.set_facecolor(BG)
    for a in (a1, a2):
        a.set_facecolor(BG)
        a.grid(color=GRID, linewidth=0.6)
        a.tick_params(colors=TXT, labelsize=8)
        for sp in a.spines.values():
            sp.set_color(GRID)
    xs = list(range(len(rows)))
    for x, (d, o, c, pl, dn, ok) in zip(xs, rows):
        col = UP if ok else DOWN
        a1.plot([x, x], [min(c, o - pl), o], color=col, linewidth=1)
        a1.bar(x, max(o - c, 0.15), bottom=min(c, o) if o != c else c - 0.075, width=0.6, color=col)
        a2.bar(x, dn, width=0.6, color=col)
        a2.plot([x - 0.3, x + 0.3], [pl, pl], color=TXT, linewidth=1, linestyle=":")
    ideal = [s0 * (core.END_DATE - r[0]).days / n for r in rows]
    a1.plot(xs, ideal, color="#f5a623", linestyle="--", linewidth=1.2, label="ideal pace")
    a1.plot(xs, [r[2] for r in rows], color="#4fc3f7", linewidth=1, label="remaining")
    a1.legend(facecolor=BG, edgecolor=GRID, labelcolor=TXT, fontsize=8)
    a1.set_ylabel("lectures remaining", color=TXT, fontsize=8)
    a2.set_ylabel("done / day", color=TXT, fontsize=8)
    step = max(1, len(rows) // 10)
    a2.set_xticks(xs[::step])
    a2.set_xticklabels([r[0].strftime("%d %b") for r in rows][::step], rotation=45)
    title = (core.SNAME[subj] if subj else "All subjects") + " · candle = remaining lectures (green = day complete)"
    a1.set_title(title, color=TXT, fontsize=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return buf
