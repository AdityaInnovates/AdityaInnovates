#!/usr/bin/env python3
"""
Render the profile's two telemetry images from .github/telemetry/data.json

  assets/telemetry/year.svg   the last year as GitHub's familiar grid, with a few quiet effects
  assets/telemetry/pulse.svg  all history as one glowing line that fades into a forecast cone

Every number is computed from the data. The forecast is a damped-Holt model on
weekly counts with bootstrapped residuals (3,000 simulated futures). Pure stdlib.
"""
import datetime as dt, html, json, math, pathlib, random, statistics as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / ".github/telemetry/data.json").read_text())
OUT = ROOT / "assets/telemetry"
OUT.mkdir(parents=True, exist_ok=True)

MONO = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"   # GitHub's UI font stack
BG, INK, MUTED, ACC = "#0d1117", "#e6edf3", "#7d8590", "#39d353"
esc = lambda s: html.escape(str(s), quote=True)
fmt = lambda n: f"{n:,.0f}"

days = {dt.date.fromisoformat(k): v for k, v in DATA["days"].items()}
today = max(days)
series = [(d, days.get(d, 0)) for d in (today - dt.timedelta(i) for i in range((today - min(days)).days, -1, -1))]
first_active = next(d for d, v in series if v > 0)
total = sum(v for _, v in series)
year_total = sum(v for d, v in series if d.year == today.year)
prev_year = sum(v for d, v in series if d.year == today.year - 1)
try:
    year_ago = today.replace(year=today.year - 1)      # GitHub's "last year": same date last year .. today
except ValueError:
    year_ago = today - dt.timedelta(365)
last_year_total = sum(v for d, v in series if d >= year_ago)
best_day = max(series, key=lambda x: x[1])
longest = run = 0
for _, v in series:
    run = run + 1 if v else 0
    longest = max(longest, run)


def svg(w, h, label, body, css):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">
<title>{esc(label)}</title>
<style>
text{{font-family:{MONO}}}
.big{{font-size:26px;font-weight:600;fill:{INK}}} .num{{font:600 26px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{INK}}}
.cap{{font:13px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{MUTED}}} .lab{{font-size:13px;fill:{MUTED}}} .s{{font-size:12px;fill:{MUTED}}}
@keyframes fi{{from{{opacity:0}}to{{opacity:1}}}}
{css}
</style>
<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<rect width="{w}" height="{h}" rx="12" fill="{BG}"/>
{body}
</svg>'''


# ================================================================== 1. year (GitHub-style grid, quiet effects)
SEQ = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]      # GitHub's own dark-mode greens


def year():
    W, H = 1000, 262
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)   # 53 Sunday-first columns, like GitHub
    active = [v for d, v in series if d >= start and v > 0]
    qs = st.quantiles(active, n=4) if len(active) >= 4 else [1, 2, 3]
    glow_cut = sorted(active)[-max(1, len(active) // 40)] if active else 10**9   # top ~2.5% of days
    cs, gap, x0, y0 = 14, 3.3, 64, 104
    step = cs + gap
    cells, clip, d, col, months = [], [], start, 0, {}
    while d <= today:
        row = (d.weekday() + 1) % 7
        if row == 0 and d != start:
            col += 1
        v = days.get(d, 0)
        lvl = 0 if v == 0 else 1 + sum(v > q for q in qs[:3])
        x, y = x0 + col * step, y0 + row * step
        glow = ' filter="url(#glow)"' if v >= glow_cut else ""
        cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cs}" height="{cs}" rx="3" fill="{SEQ[min(lvl, 4)]}"{glow} '
                     f'style="animation:pop .5s {0.012 * (col + row * 2):.2f}s both"><title>{v} on {d:%a %d %b %Y}</title></rect>')
        clip.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cs}" height="{cs}" rx="3"/>')
        if d.day <= 7 and row == 0:
            months[col] = d.strftime("%b")
        d += dt.timedelta(1)
    gw = (col + 1) * step
    b = [f'<defs><clipPath id="cells">{"".join(clip)}</clipPath>'
         '<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
         '<stop offset=".5" stop-color="#fff" stop-opacity=".16"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>']
    stats = [(fmt(last_year_total), "contributions in the last year"), (f"{longest} days", "longest streak"), (str(best_day[1]), "best day")]
    for i, (v, lab) in enumerate(stats):
        x = x0 + i * 250
        b.append(f'<g style="animation:fi .8s {0.1 + 0.15*i:.2f}s both"><text x="{x}" y="46" class="num">{v}</text>'
                 f'<text x="{x}" y="66" class="cap">{lab}</text></g>')
    for c, m in months.items():
        b.append(f'<text x="{x0 + c*step:.1f}" y="{y0-9}" class="s">{m}</text>')
    for r, nm in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        b.append(f'<text x="{x0-10}" y="{y0 + r*step + 11:.1f}" class="s" text-anchor="end">{nm}</text>')
    b.append("".join(cells))
    # a slow band of light that crosses the grid every 9s, clipped to the squares
    b.append(f'<g clip-path="url(#cells)"><rect x="{x0-120}" y="{y0-4}" width="120" height="{7*step+8}" fill="url(#sheen)" '
             f'style="animation:sheen 9s 2s ease-in-out infinite"/></g>')
    trow = (today.weekday() + 1) % 7
    tx, ty = x0 + col * step, y0 + trow * step
    b.append(f'<rect x="{tx-2:.1f}" y="{ty-2:.1f}" width="{cs+4}" height="{cs+4}" rx="4.5" fill="none" stroke="{SEQ[4]}" stroke-width="1.5" '
             f'style="transform-origin:{tx+cs/2:.1f}px {ty+cs/2:.1f}px;animation:breathe 2.8s ease-in-out infinite"/>')
    ly = y0 + 7 * step + 18
    b.append(f'<text x="{x0 + gw - 5*17 - 44:.1f}" y="{ly+10}" class="s" text-anchor="end">Less</text>')
    for i, c in enumerate(SEQ):
        b.append(f'<rect x="{x0 + gw - 5*17 - 38 + i*17:.1f}" y="{ly}" width="12" height="12" rx="3" fill="{c}"/>')
    b.append(f'<text x="{x0 + gw - 40:.1f}" y="{ly+10}" class="s">More</text>')
    css = ("@keyframes pop{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:none}}"
           "rect[style*=pop]{transform-box:fill-box;transform-origin:center}"
           f"@keyframes sheen{{0%{{transform:translateX(0)}}60%,100%{{transform:translateX({gw+140:.0f}px)}}}}"
           "@keyframes breathe{0%,100%{opacity:.25;transform:scale(1)}50%{opacity:1;transform:scale(1.08)}}")
    return svg(W, H, f"{last_year_total} contributions in the last year", "\n".join(b), css)


# ================================================================== 2. pulse (history + forecast)
T = lambda y: math.sqrt(max(y, 0))
IT = lambda z: max(z, 0) ** 2


def weekly(start):
    n = (today - start).days // 7
    return [sum(days.get(today - dt.timedelta(days=7*k + j), 0) for j in range(7)) for k in range(n, -1, -1)]


def holt_best(z):
    best = None
    for a in (.05, .1, .15, .2, .3, .4, .5, .6):
        for b in (.01, .03, .05, .1, .2):
            for phi in (.8, .88, .94, .98):
                l, t, res = z[0], 0.0, []
                for y in z[1:]:
                    res.append(y - (l + phi * t))
                    nl = a * y + (1 - a) * (l + phi * t)
                    t = b * (nl - l) + (1 - b) * phi * t
                    l = nl
                sse = sum(e * e for e in res[4:])
                if best is None or sse < best[0]:
                    best = (sse, a, b, phi, l, t, res)
    return best[1:]


def simulate(z, H, n=3000, seed=7):
    a, b, phi, l0, t0, res = holt_best(z)
    rnd, res, paths = random.Random(seed), res[-104:] or [0.0], []
    for _ in range(n):
        l, t, p = l0, t0, []
        for _h in range(H):
            y = l + phi * t + rnd.choice(res)
            nl = a * y + (1 - a) * (l + phi * t)
            t = b * (nl - l) + (1 - b) * phi * t
            l = nl
            p.append(IT(y))
        paths.append(p)
    return paths


def q(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def smooth(pts):
    """Catmull-Rom -> cubic Bézier, for an organic line."""
    if len(pts) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


def pulse():
    W, H = 1000, 280
    yt = {}
    for d, v in series:
        yt[d.year] = yt.get(d.year, 0) + v
    y_start = min((y for y, t in yt.items() if t >= 50), default=first_active.year)
    wk = weekly(dt.date(y_start, 1, 1))
    # 3-week moving average: keeps the shape, drops the jitter
    sm = [st.mean(wk[max(0, i - 1):i + 2]) for i in range(len(wk))]
    rem = (dt.date(today.year, 12, 31) - today).days
    full, frac = divmod(rem, 7)
    HZN = max(12, full + 1)
    paths = simulate([T(v) for v in weekly(first_active)], HZN)
    ye = [year_total + sum(p[:full]) + p[full] * frac / 7 for p in paths]
    p_beat = 100 * sum(x > prev_year for x in ye) / len(ye)
    SHOW = 12
    lo = [q([p[h] for p in paths], .1) for h in range(SHOW)]
    hi = [q([p[h] for p in paths], .9) for h in range(SHOW)]
    med = [q([p[h] for p in paths], .5) for h in range(SHOW)]

    n, N = len(sm), len(sm) + SHOW
    x0, x1, base, ph = 34, W - 34, H - 44, 150
    top = max(max(sm), max(hi)) * 1.05 or 1
    xn = x1 - 210                                    # the future gets its own stretch of canvas
    X = lambda i: (x0 + (xn - x0) * i / (n - 1)) if i <= n - 1 else xn + (x1 - xn) * (i - n + 1) / SHOW
    Y = lambda v: base - ph * min(v, top) / top
    past = [(X(i), Y(v)) for i, v in enumerate(sm)]
    nx, ny = past[-1]
    line = smooth(past)
    b = []
    b.append('<defs><linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">'
             f'<stop offset="0" stop-color="{ACC}" stop-opacity=".24"/><stop offset="1" stop-color="{ACC}" stop-opacity=".03"/></linearGradient>'
             '<linearGradient id="under" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{ACC}" stop-opacity=".16"/><stop offset="1" stop-color="{ACC}" stop-opacity="0"/></linearGradient></defs>')
    b.append(f'<path d="{line} L{nx:.1f},{base} L{x0},{base} Z" fill="url(#under)"/>')
    b.append(f'<path id="p" d="{line}" fill="none" stroke="{ACC}" stroke-width="2.2" stroke-linejoin="round" filter="url(#glow)" '
             f'pathLength="1" style="stroke-dasharray:1;stroke-dashoffset:1;animation:draw 3s ease-out forwards"/>')
    # a spark that keeps running along the line
    b.append(f'<circle r="3" fill="{INK}" filter="url(#glow)" opacity=".9"><animateMotion dur="6s" begin="3s" repeatCount="indefinite">'
             f'<mpath href="#p"/></animateMotion></circle>')
    # the future: a fading cone (80% range) + faint median
    fut = [(nx, ny)] + [(X(n - 1 + h + 1), Y(v)) for h, v in enumerate(hi)]
    low = [(X(n - 1 + h + 1), Y(v)) for h, v in enumerate(lo)][::-1] + [(nx, ny)]
    cone = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in fut + low) + "Z"
    b.append(f'<path d="{cone}" fill="url(#fade)" style="animation:fi 1.2s 2.8s both"/>')
    mline = smooth([(nx, ny)] + [(X(n - 1 + h + 1), Y(v)) for h, v in enumerate(med)])
    b.append(f'<path d="{mline}" fill="none" stroke="{ACC}" stroke-opacity=".55" stroke-width="1.6" stroke-dasharray="2 5" '
             f'stroke-linecap="round" style="animation:fi 1.2s 3s both"/>')
    b.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="4.5" fill="{INK}" filter="url(#glow)" style="animation:beat 1.6s 3s infinite"/>'
             f'<text x="{nx:.1f}" y="{base+20}" class="s" text-anchor="middle" fill="{INK}">now</text>'
             f'<text x="{x1}" y="{base+20}" class="s" text-anchor="end">+12 wk</text>')
    # year ticks only
    wk_end = [today - dt.timedelta(days=7 * (n - 1 - i)) for i in range(n)]
    b.append(f'<text x="{x0}" y="{base+20}" class="s">{wk_end[0].year}</text>')
    for i, d in enumerate(wk_end):
        if i and d.year != wk_end[i - 1].year and X(i) < nx - 40:
            b.append(f'<text x="{X(i):.1f}" y="{base+20}" class="s">{d.year}</text>')
    b.append(f'<line x1="{x0}" y1="{base}" x2="{x1}" y2="{base}" stroke="{ACC}" stroke-opacity=".12"/>')
    # headline, one sentence each side
    b.append(f'<g style="animation:fi .8s .2s both"><text x="{x0}" y="46" class="big">{fmt(total)}</text>'
             f'<text x="{x0}" y="66" class="lab">contributions since {first_active.year}</text></g>')
    b.append(f'<g style="animation:fi .8s 3.2s both"><text x="{x1}" y="46" class="big" text-anchor="end">~{fmt(q(ye, .5))}</text>'
             f'<text x="{x1}" y="66" class="lab" text-anchor="end">expected by the end of {today.year} · {p_beat:.0f}% chance of beating {today.year-1}</text></g>')
    b.append(f'<text x="{x1}" y="{H-10}" class="s" text-anchor="end" fill-opacity=".7">fog = 80% range of 3,000 simulated futures</text>')
    css = ("@keyframes draw{to{stroke-dashoffset:0}}"
           "@keyframes beat{0%,100%{r:4.5;opacity:1}15%{r:7;opacity:.6}30%{r:4.5;opacity:1}}")
    return svg(W, H, f"{total} contributions since {first_active.year}", "\n".join(b), css), q(ye, .5), p_beat


if __name__ == "__main__":
    (OUT / "year.svg").write_text(year())
    p, ye, pb = pulse()
    (OUT / "pulse.svg").write_text(p)
    for old in ("overview.svg", "history.svg", "forecast.svg", "rain.svg"):
        (OUT / old).unlink(missing_ok=True)
    print(f"last year {last_year_total} · since {first_active.year}: {total} · {today.year} forecast ~{ye:.0f} · P(beat) {pb:.0f}%")
