#!/usr/bin/env python3
"""
Render telemetry SVGs from .github/telemetry/data.json

  assets/telemetry/overview.svg  htop-style meters + contribution memory dump (xxd)
  assets/telemetry/history.svg   oscilloscope trace since first real activity + weekday sonar
  assets/telemetry/forecast.svg  Monte-Carlo futures (damped Holt + bootstrap), back-tested

Every number drawn is computed from the data. Pure stdlib.
"""
import datetime as dt, html, json, math, pathlib, random, statistics as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / ".github/telemetry/data.json").read_text())
OUT = ROOT / "assets/telemetry"
OUT.mkdir(parents=True, exist_ok=True)

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
BG, PANEL, LINE, GRID = "#050807", "#07100a", "#1c2b20", "#12301b"
INK, INK2, MUTED = "#e6ffe9", "#9fb3a4", "#6e7d72"
ACC, FC = "#00ff41", "#e346c9"
SEQ = ["#1f3325", "#0b5c22", "#08902f", "#04c43c", "#00ff41"]   # one hue, dim -> bright
SHORT = {"JavaScript": "js", "TypeScript": "ts", "Python": "py", "HTML": "html", "CSS": "css", "Kotlin": "kt",
         "C++": "c++", "Rust": "rs", "Go": "go", "Shell": "sh", "Java": "java", "Swift": "swift", "Dart": "dart"}
esc = lambda s: html.escape(str(s), quote=True)
fmt = lambda n: f"{n:,.0f}"

# ================================================================== data
days = {dt.date.fromisoformat(k): v for k, v in DATA["days"].items()}
today = max(days)
series = [(d, days.get(d, 0)) for d in (today - dt.timedelta(i) for i in range((today - min(days)).days, -1, -1))]
first_active = next(d for d, v in series if v > 0)
total = sum(v for _, v in series)
year_total = sum(v for d, v in series if d.year == today.year)
prev_year = sum(v for d, v in series if d.year == today.year - 1)
# GitHub's "in the last year": same date one year ago .. today, inclusive
try:
    year_ago = today.replace(year=today.year - 1)
except ValueError:
    year_ago = today - dt.timedelta(365)
last_year = [(d, v) for d, v in series if d >= year_ago]
last_year_total = sum(v for _, v in last_year)
active_pct = 100 * sum(1 for _, v in last_year if v) / len(last_year)
best_day = max(series, key=lambda x: x[1])
load = [sum(v for d, v in series if (today - d).days < n) / n for n in (7, 30, 90)]


def streaks():
    longest = run = 0
    for _, v in series:
        run = run + 1 if v else 0
        longest = max(longest, run)
    i, cur = len(series) - 1, 0
    if series[i][1] == 0:
        i -= 1                      # today isn't over yet
    while i >= 0 and series[i][1]:
        cur += 1; i -= 1
    return cur, longest


cur_streak, long_streak = streaks()


def uptime():
    m = (today.year - first_active.year) * 12 + today.month - first_active.month
    return f"{m // 12}y {m % 12}m"


stamp = f"@{DATA['user']} · synced {DATA['generated'][:10]}"


def frame(w, h, title, cmd, body, css=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">
<title>{esc(title)} — {esc(cmd)}</title>
<style>
text{{font-family:{MONO}}}
.h{{font-size:12px;letter-spacing:2px;fill:{MUTED}}} .s{{font-size:11px;fill:{MUTED}}} .c{{font-size:12px;fill:{INK2}}}
.v{{font-size:24px;font-weight:700;fill:{INK}}} .l{{font-size:10px;letter-spacing:1.5px;fill:{MUTED}}}
.t{{font-size:12px;fill:{INK2}}} .b{{font-size:12px;fill:{INK}}}
.cur{{animation:bk 1s steps(1) infinite}} @keyframes bk{{50%{{opacity:0}}}}
@keyframes fi{{from{{opacity:0}}to{{opacity:1}}}}
.fl{{animation:fl 7s infinite}} @keyframes fl{{0%,96%,100%{{opacity:1}}97%{{opacity:.75}}98.5%{{opacity:.95}}}}
{css}
</style>
<defs>
<pattern id="sl" width="3" height="3" patternUnits="userSpaceOnUse"><rect width="3" height="1" fill="#000" fill-opacity=".35"/></pattern>
<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<g class="fl">
<rect width="{w}" height="{h}" rx="10" fill="{BG}" stroke="{ACC}" stroke-opacity=".25"/>
<text x="24" y="30" class="h">{esc(title)}</text>
<text x="{24 + 9.3*len(title) + 12:.0f}" y="30" class="c"><tspan fill="{ACC}">root@void</tspan>:~# {esc(cmd)}<tspan class="cur" fill="{ACC}"> █</tspan></text>
<text x="{w-24}" y="30" class="s" text-anchor="end">{esc(stamp)}</text>
<line x1="24" y1="42" x2="{w-24}" y2="42" stroke="{LINE}"/>
{body}
</g>
<rect width="{w}" height="{h}" rx="10" fill="url(#sl)"/>
</svg>'''


# ================================================================== 1. overview: htop + xxd
def overview():
    W, H = 1000, 404
    b = []
    CW = 7.22                                 # monospace advance at 12px
    bx = 24 + 8 * CW                          # meter "[" column

    def meter(y, label, frac, right, i):
        n = 34
        fill = max(0, min(n, round(frac * n)))
        b.append(f'<text x="24" y="{y}" class="b" fill="{INK2}">{esc(label)}</text>'
                 f'<text x="{bx:.1f}" y="{y}" class="b">[</text>'
                 f'<text x="{bx + CW:.1f}" y="{y}" class="b" fill="{ACC}" style="clip-path:inset(0 100% 0 0);animation:mt 1.2s {0.15*i:.2f}s ease-out forwards">{"|" * fill}</text>'
                 f'<text x="{bx + (n + 1) * CW:.1f}" y="{y}" class="b">]</text>'
                 f'<text x="{bx + (n + 3) * CW:.1f}" y="{y}" class="b">{esc(right)}</text>')

    meter(72, "year", last_year_total / max(last_year_total, prev_year, 1), f"{fmt(last_year_total)} in the last year", 0)
    meter(94, "streak", cur_streak / max(long_streak, 1), f"{cur_streak}d now · {long_streak}d record", 1)
    meter(116, "active", active_pct / 100, f"{active_pct:.0f}% of days, last year", 2)
    meter(138, str(today.year), year_total / max(prev_year, 1), f"{fmt(year_total)} of {fmt(prev_year)} ({today.year-1})", 3)

    langs = sorted(DATA["languages"].items(), key=lambda kv: -kv[1]["size"])[:3]
    ls = sum(v["size"] for v in DATA["languages"].values()) or 1
    rx = 642
    rows = [
        ("Load average:", f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}", "per day · 7/30/90d"),
        ("Uptime:", uptime(), f"since {first_active:%b %Y}"),
        ("Total:", fmt(total), f"best day {best_day[1]} · {best_day[0]:%d %b %y}"),
        ("Langs:", " ".join(f"{SHORT.get(k, k.lower())} {v['size']/ls*100:.0f}%" for k, v in langs), f"{DATA['repos']} repos" if DATA.get("repos") else ""),
    ]
    for i, (k, v, sub) in enumerate(rows):
        y = 72 + i * 22
        b.append(f'<text x="{rx}" y="{y}" class="b" style="animation:fi .4s {0.6+0.15*i:.2f}s both"><tspan fill="{INK2}">{k}</tspan> '
                 f'<tspan fill="{ACC}" font-weight="700">{esc(v)}</tspan> <tspan fill="{MUTED}" font-size="11">{esc(sub)}</tspan></text>')
    b.append(f'<line x1="24" y1="158" x2="{W-24}" y2="158" stroke="{LINE}" stroke-dasharray="2 4"/>')

    # ---- xxd-style contribution dump: 53 weeks x 7 days, like GitHub's grid
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)
    vals = [v for d, v in series if d >= start and v > 0]
    qs = [st.quantiles(vals, n=4)[i] for i in range(3)] if len(vals) >= 4 else [1, 2, 3]
    lvl = lambda v: 0 if v == 0 else 1 + sum(v > q for q in qs)
    cw, ch, x0, y0 = 16.3, 22, 88, 206
    b.append(f'<text x="24" y="182" class="s"><tspan fill="{INK2}">$ xxd -c 53 /dev/contributions</tspan>'
             f'   # 1 byte = 1 day · value = contributions in hex · brighter = busier</text>')
    d, col, months, cells = start, 0, {}, []
    while d <= today:
        row = (d.weekday() + 1) % 7
        if row == 0 and d != start:
            col += 1
        v = days.get(d, 0)
        L = lvl(v)
        wt = ' font-weight="700"' if L >= 3 else ""
        cells.append(f'<text x="{x0 + col*cw:.1f}" y="{y0 + row*ch + 15}" fill="{SEQ[L]}"{wt} '
                     f'style="animation:fi .25s {0.015*col:.2f}s both">{min(v, 255):02x}<title>{v} on {d:%a %d %b %Y}</title></text>')
        if d.day <= 7 and row == 0:
            months[col] = d.strftime("%b").lower()
        d += dt.timedelta(1)
    b.append(f'<g font-size="10.5">{"".join(cells)}</g>')
    for c, m in months.items():
        b.append(f'<text x="{x0 + c*cw:.1f}" y="{y0-2}" class="s">{m}</text>')
    for r, n in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat")):
        b.append(f'<text x="24" y="{y0 + r*ch + 15}" class="s">{r:04x}: <tspan fill="{INK2}">{n}</tspan></text>')
    trow = (today.weekday() + 1) % 7
    b.append(f'<rect x="{x0 + col*cw - 3:.1f}" y="{y0 + trow*ch + 1}" width="{cw+1:.1f}" height="{ch-2}" rx="3" fill="none" stroke="{INK}" class="cur"/>')
    b.append(f'<rect x="{x0-4}" y="{y0+2}" width="{cw+2:.1f}" height="{7*ch}" rx="3" fill="{ACC}" fill-opacity=".10" stroke="{ACC}" stroke-opacity=".35" '
             f'style="animation:rh 9s linear infinite"/>')
    fy = y0 + 7 * ch + 24
    b.append(f'<text x="24" y="{fy}" class="s">less <tspan fill="{SEQ[0]}">00</tspan> <tspan fill="{SEQ[1]}">01</tspan> '
             f'<tspan fill="{SEQ[2]}">04</tspan> <tspan fill="{SEQ[3]}" font-weight="700">09</tspan> <tspan fill="{SEQ[4]}" font-weight="700">1f</tspan> more</text>'
             f'<text x="{W-24}" y="{fy}" class="s" text-anchor="end">{fmt(last_year_total)} contributions in the last year · '
             f'best day 0x{min(best_day[1], 255):02x} = {best_day[1]}</text>')
    css = (f"@keyframes mt{{to{{clip-path:inset(0 0 0 0)}}}}"
           f"@keyframes rh{{from{{transform:translateX(0)}}to{{transform:translateX({(col+1)*cw:.0f}px)}}}}")
    return frame(W, H, "// TELEMETRY", "htop -u me", "\n".join(b), css)


# ================================================================== 2. history: oscilloscope + sonar
def weekly(start=None):
    """7-day buckets ending today (no partial week), oldest first."""
    start = start or first_active
    n = (today - start).days // 7
    return [sum(days.get(today - dt.timedelta(days=7*k + j), 0) for j in range(7)) for k in range(n, -1, -1)]


def history():
    W, H = 1000, 368
    yt = {}
    for d, v in series:
        yt[d.year] = yt.get(d.year, 0) + v
    y_start = min((y for y, t in yt.items() if t >= 50), default=first_active.year)
    wk = weekly(dt.date(y_start, 1, 1))
    n = len(wk)
    wk_end = [today - dt.timedelta(days=7 * (n - 1 - i)) for i in range(n)]
    sx, sy, sw, sh = 24, 58, 660, 232
    b = [f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="8" fill="{PANEL}" stroke="{LINE}"/>']
    for i in range(1, 10):
        x = sx + sw * i / 10
        b.append(f'<line x1="{x:.1f}" y1="{sy}" x2="{x:.1f}" y2="{sy+sh}" stroke="{GRID}" stroke-dasharray="1 3"/>')
    for i in range(1, 8):
        y = sy + sh * i / 8
        b.append(f'<line x1="{sx}" y1="{y:.1f}" x2="{sx+sw}" y2="{y:.1f}" stroke="{GRID}" stroke-dasharray="1 3"/>')
    top = max(wk) * 1.15 or 1
    pad = 10
    X = lambda i: sx + pad + (sw - 2 * pad) * i / (n - 1)
    Y = lambda v: sy + sh - 8 - (sh - 26) * v / top
    pts = [(X(i), Y(v)) for i, v in enumerate(wk)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    b.append(f'<path d="{path}" fill="none" stroke="{ACC}" stroke-opacity=".16" stroke-width="1.5"/>')       # phosphor ghost
    b.append(f'<path id="tr" d="{path}" fill="none" stroke="{ACC}" stroke-width="1.8" stroke-linejoin="round" filter="url(#glow)" '
             f'pathLength="1" style="stroke-dasharray:1;animation:sweep 7s linear infinite"/>')
    b.append(f'<circle r="3.5" fill="{INK}" filter="url(#glow)"><animateMotion dur="7s" repeatCount="indefinite" '
             f'keyPoints="0;1;1" keyTimes="0;.8;1" calcMode="linear"><mpath href="#tr"/></animateMotion></circle>')
    for i, d in enumerate(wk_end):
        if i and d.year != wk_end[i-1].year:
            x = X(i)
            b.append(f'<line x1="{x:.1f}" y1="{sy+sh}" x2="{x:.1f}" y2="{sy+sh+6}" stroke="{INK2}"/>'
                     f'<text x="{x+3:.1f}" y="{sy+sh+18}" class="s"><tspan fill="{INK2}">{d.year}</tspan> {fmt(yt.get(d.year, 0))}</text>')
    pi = max(range(n), key=wk.__getitem__)
    px, py = pts[pi]
    if px > sx + sw - 200:
        b.append(f'<text x="{px-8:.1f}" y="{py+4:.1f}" class="b" text-anchor="end">peak {wk[pi]}/wk · {wk_end[pi]:%b %Y} ▸</text>')
    else:
        b.append(f'<text x="{px+8:.1f}" y="{py+4:.1f}" class="b">◂ peak {wk[pi]}/wk · {wk_end[pi]:%b %Y}</text>')
    b.append(f'<text x="{sx+10}" y="{sy+16}" class="s"><tspan fill="{ACC}">CH1</tspan> contributions/week · {n} samples</text>'
             f'<text x="{sx+sw-10}" y="{sy+16}" class="s" text-anchor="end">{top/8:.0f}/div · {n/10:.0f} wk/div</text>')
    # measurements
    mean = st.mean(wk)
    den = sum((v - mean) ** 2 for v in wk) or 1
    acf = lambda k: sum((wk[i] - mean) * (wk[i + k] - mean) for i in range(n - k)) / den
    lags = [(k, acf(k)) for k in range(3, min(60, n // 2))]
    k_best, r_best = max(lags, key=lambda t: t[1]) if lags else (0, 0)
    rhythm = f"~{k_best}wk (r={r_best:.2f})" if r_best >= .2 else "none dominant"
    meas = [("Vpp", f"{max(wk)}"), ("Vavg", f"{mean:.1f}"), ("duty", f"{100*sum(1 for v in wk if v)/n:.0f}%"), ("burst period", rhythm)]
    mx = sx
    for k, v in meas:
        b.append(f'<text x="{mx}" y="{sy+sh+44}" class="t"><tspan fill="{MUTED}">{k}</tspan> <tspan fill="{INK}">{esc(v)}</tspan></text>')
        mx += 30 + 7.3 * (len(k) + len(v) + 1)
    b.append(f'<text x="{sx}" y="{sy+sh+62}" class="s">duty = weeks with any activity · burst period = strongest repeating rhythm (autocorrelation)</text>')
    # sonar: weekday distribution, last year
    cx, cy, R = 846, 168, 96
    dow = [0] * 7
    for d, v in last_year:
        dow[(d.weekday() + 1) % 7] += v
    dm = max(dow) or 1
    names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
    b.append(f'<defs><linearGradient id="sw" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ACC}" stop-opacity=".35"/>'
             f'<stop offset="1" stop-color="{ACC}" stop-opacity="0"/></linearGradient></defs>')
    for r in (.33, .66, 1):
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{R*r:.1f}" fill="none" stroke="{GRID}"/>')
    ang = lambda i: -math.pi / 2 + 2 * math.pi * i / 7
    for i in range(7):
        b.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + R*math.cos(ang(i)):.1f}" y2="{cy + R*math.sin(ang(i)):.1f}" stroke="{GRID}"/>')
        lx, ly = cx + (R + 17) * math.cos(ang(i)), cy + (R + 17) * math.sin(ang(i)) + 4
        hot = f' fill="{INK}" font-weight="700"' if dow[i] == dm else ""
        b.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="s" text-anchor="middle"{hot}>{names[i]}</text>')
    P = [(cx + R*(dow[i]/dm)*math.cos(ang(i)), cy + R*(dow[i]/dm)*math.sin(ang(i))) for i in range(7)]
    b.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in P)}" fill="{ACC}" fill-opacity=".14" stroke="{ACC}" '
             f'stroke-width="1.8" stroke-linejoin="round" filter="url(#glow)"/>')
    for i, (x, y) in enumerate(P):
        b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{ACC}" style="animation:ping 4s {i*4/7:.2f}s infinite"/>')
    ex, ey = cx + R * math.sin(math.radians(40)), cy - R * math.cos(math.radians(40))
    b.append(f'<g style="transform-origin:{cx}px {cy}px;animation:spin 4s linear infinite">'
             f'<path d="M{cx},{cy} L{cx},{cy-R} A{R},{R} 0 0,1 {ex:.1f},{ey:.1f} Z" fill="url(#sw)"/>'
             f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy-R}" stroke="{ACC}" stroke-width="1.5" filter="url(#glow)"/></g>')
    hot_i = dow.index(dm)
    b.append(f'<text x="{cx}" y="{sy+sh+44}" class="t" text-anchor="middle"><tspan fill="{MUTED}">SONAR</tspan> peak day '
             f'<tspan fill="{INK}">{names[hot_i]}</tspan> · {100*dm/(sum(dow) or 1):.0f}% of last year</text>')
    css = ("@keyframes sweep{0%{stroke-dashoffset:1}80%{stroke-dashoffset:0}100%{stroke-dashoffset:0}}"
           "@keyframes spin{to{transform:rotate(360deg)}}"
           "@keyframes ping{0%,100%{opacity:.5}6%{opacity:1}}")
    return frame(W, H, "// HISTORY", f"scope --since {y_start} --ch1 contributions", "\n".join(b), css)


# ================================================================== 3. forecast: Monte-Carlo futures
T = lambda y: math.sqrt(max(y, 0))      # variance-stabilising transform for counts
IT = lambda z: max(z, 0) ** 2


def holt_fit(z, a, b, phi):
    l, t = z[0], 0.0
    res = []
    for y in z[1:]:
        f = l + phi * t
        res.append(y - f)
        nl = a * y + (1 - a) * (l + phi * t)
        t = b * (nl - l) + (1 - b) * phi * t
        l = nl
    return l, t, res


def holt_best(z):
    best = None
    for a in (.05, .1, .15, .2, .3, .4, .5, .6):
        for b in (.01, .03, .05, .1, .2):
            for phi in (.8, .88, .94, .98):
                l, t, r = holt_fit(z, a, b, phi)
                sse = sum(e * e for e in r[4:])
                if best is None or sse < best[0]:
                    best = (sse, a, b, phi, l, t, r)
    return best[1:]


def simulate(z, H, n=3000, seed=7):
    a, b, phi, l0, t0, res = holt_best(z)
    rnd = random.Random(seed)
    res = res[-104:] or [0.0]
    paths = []
    for _ in range(n):
        l, t, p = l0, t0, []
        for _h in range(H):
            y = l + phi * t + rnd.choice(res)
            nl = a * y + (1 - a) * (l + phi * t)
            t = b * (nl - l) + (1 - b) * phi * t
            l = nl
            p.append(IT(y))
        paths.append(p)
    return paths, (a, b, phi)


def q(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(p * len(s)))]


def forecast():
    W, H = 1000, 396
    wk = weekly()
    z = [T(v) for v in wk]
    HZN = 12
    rem = (dt.date(today.year, 12, 31) - today).days
    full, frac = divmod(rem, 7)
    paths, (a, b_, phi) = simulate(z, max(HZN, full + 1))
    med = [q([p[h] for p in paths], .5) for h in range(HZN)]
    lo = [q([p[h] for p in paths], .1) for h in range(HZN)]
    hi = [q([p[h] for p in paths], .9) for h in range(HZN)]
    bt = 8
    bp, _ = simulate(z[:-bt], bt, n=800, seed=11)
    bmed = [q([p[h] for p in bp], .5) for h in range(bt)]
    act = wk[-bt:]
    mae = sum(abs(x - y) for x, y in zip(bmed, act)) / bt
    naive = sum(abs(wk[-bt - 1] - y) for y in act) / bt
    cover = sum(q([p[h] for p in bp], .1) <= act[h] <= q([p[h] for p in bp], .9) for h in range(bt))
    next30 = [sum(p[:4]) + p[4] * 2 / 7 for p in paths]
    ye = [year_total + sum(p[:full]) + p[full] * frac / 7 for p in paths]
    p_beat = 100 * sum(x > prev_year for x in ye) / len(ye)
    trend = (st.mean(wk[-8:]) - st.mean(wk[-16:-8])) / (st.mean(wk[-16:-8]) or 1) * 100

    hist_n = 40
    hw = wk[-hist_n:]
    x0, y0, pw, ph = 56, 66, 590, 196
    N = hist_n + HZN
    # 40 futures spread evenly across the distribution of 12-week totals (5th..95th pct)
    ranked = sorted(paths, key=lambda p: sum(p[:HZN]))
    show = [ranked[int(len(ranked) * (0.05 + 0.9 * k / 39))] for k in range(40)]
    top = max(max(hw), max(hi)) * 1.1 or 1
    X = lambda i: x0 + pw * i / (N - 1)
    Y = lambda v: y0 + ph - ph * min(v, top) / top
    b = [f'<clipPath id="pa"><rect x="{x0}" y="{y0-2}" width="{pw+2}" height="{ph+4}"/></clipPath>']
    for f in (0, .5, 1):
        y = y0 + ph - ph * f
        b.append(f'<line x1="{x0}" y1="{y}" x2="{x0+pw}" y2="{y}" stroke="{LINE}"/><text x="{x0-8}" y="{y+4}" class="s" text-anchor="end">{fmt(top*f)}</text>')
    now = X(hist_n - 1)
    b.append(f'<rect x="{now}" y="{y0}" width="{x0+pw-now}" height="{ph}" fill="{FC}" fill-opacity=".035"/>'
             f'<line x1="{now}" y1="{y0-8}" x2="{now}" y2="{y0+ph}" stroke="{INK2}" stroke-dasharray="3 3"/>'
             f'<text x="{now+6}" y="{y0-10}" class="s">now → +{HZN} weeks</text>')
    b.append(f'<path d="M{X(0)},{y0+ph} ' + " ".join(f"L{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(hw)) +
             f' L{X(hist_n-1)},{y0+ph}Z" fill="{ACC}" fill-opacity=".07"/>')
    b.append('<path d="' + " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(hw)) +
             f'" fill="none" stroke="{ACC}" stroke-width="2" stroke-linejoin="round" pathLength="1" '
             f'style="stroke-dasharray:1;stroke-dashoffset:1;animation:dr 2s ease-out forwards"/>')
    fi = list(range(hist_n - 1, N))
    g = []
    for k, p in enumerate(show):
        d_ = " ".join(f"{'M' if j == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for j, (i, v) in enumerate(zip(fi, [hw[-1]] + p[:HZN])))
        g.append(f'<path d="{d_}" fill="none" stroke="{FC}" stroke-width="1" stroke-opacity=".3" pathLength="1" '
                 f'style="stroke-dasharray:1;stroke-dashoffset:1;animation:dr .6s {2 + k*0.05:.2f}s ease-out forwards"/>')
    b.append(f'<g clip-path="url(#pa)">{"".join(g)}</g>')
    band = (" ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for k, (i, v) in enumerate(zip(fi, [hw[-1]] + hi)))
            + " " + " ".join(f"L{X(i):.1f},{Y(v):.1f}" for i, v in reversed(list(zip(fi, [hw[-1]] + lo)))) + "Z")
    b.append(f'<path d="{band}" fill="{FC}" fill-opacity=".08" stroke="{FC}" stroke-opacity=".7" stroke-dasharray="2 3" style="animation:fi .6s 4.2s both"/>')
    b.append('<path d="' + " ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for k, (i, v) in enumerate(zip(fi, [hw[-1]] + med))) +
             f'" fill="none" stroke="{INK}" stroke-width="2.2" stroke-dasharray="6 4" filter="url(#glow)" style="animation:fi .6s 4.4s both"/>')
    b.append(f'<circle cx="{X(hist_n-1)}" cy="{Y(hw[-1])}" r="4" fill="{ACC}" stroke="{BG}" stroke-width="2"/>')
    b.append(f'<text x="{x0}" y="{y0+ph+18}" class="t"><tspan fill="{ACC}">━</tspan> actual weekly   '
             f'<tspan fill="{FC}">╱</tspan> 40 of 3,000 simulated futures   <tspan fill="{FC}">┄</tspan> 80% range   <tspan fill="{INK}">╌</tspan> median</text>')
    log = [
        "$ ./forecast --model damped-holt --transform sqrt --sims 3000",
        f"> fit    α={a} β={b_} φ={phi} on {len(wk)} weeks of history",
        f"> test   last {bt}w held out: MAE {mae:.1f}/wk vs naive {naive:.1f} · {cover}/{bt} inside the 80% range",
        "> run    3,000 futures from bootstrapped residuals ......... done",
    ]
    for i, line in enumerate(log):
        y = y0 + ph + 46 + i * 17
        b.append(f'<text x="24" y="{y}" class="s" fill="{INK2 if i == 0 else MUTED}" '
                 f'style="clip-path:inset(0 100% 0 0);animation:ty .9s steps(40) {0.3+0.9*i:.1f}s forwards">{esc(line)}</text>')
    px = 690
    rows = [("NEXT 30 DAYS", fmt(q(next30, .5)), f"80%: {fmt(q(next30,.1))}–{fmt(q(next30,.9))}"),
            (f"{today.year} PROJECTED", fmt(q(ye, .5)), f"80%: {fmt(q(ye,.1))}–{fmt(q(ye,.9))}"),
            ("MOMENTUM", f"{trend:+.0f}%", "last 8 weeks vs the 8 before")]
    for i, (lab, val, sub) in enumerate(rows):
        y = y0 + 4 + i * 66
        b.append(f'<g style="animation:fi .5s {4.4+0.2*i:.1f}s both"><text x="{px}" y="{y}" class="l">{esc(lab)}</text>'
                 f'<text x="{px}" y="{y+26}" class="v">{esc(val)}</text><text x="{px}" y="{y+42}" class="s">{esc(sub)}</text></g>')
    gx, gy, gr = 906, y0 + 62, 44
    circ = 2 * math.pi * gr
    arc = circ * p_beat / 100
    b.append(f'<circle cx="{gx}" cy="{gy}" r="{gr}" fill="none" stroke="{LINE}" stroke-width="7"/>'
             f'<circle cx="{gx}" cy="{gy}" r="{gr}" fill="none" stroke="{ACC}" stroke-width="7" stroke-linecap="round" '
             f'transform="rotate(-90 {gx} {gy})" stroke-dasharray="{arc:.1f} {circ:.1f}" filter="url(#glow)" '
             f'style="stroke-dashoffset:{arc:.1f};animation:gz 1.6s 4.6s ease-out forwards"/>'
             f'<text x="{gx}" y="{gy+8}" text-anchor="middle" class="v">{p_beat:.0f}%</text>'
             f'<text x="{gx}" y="{gy+gr+22}" text-anchor="middle" class="l">P(BEAT {today.year-1})</text>'
             f'<text x="{gx}" y="{gy+gr+37}" text-anchor="middle" class="s">{fmt(prev_year)} to beat</text>')
    css = "@keyframes dr{to{stroke-dashoffset:0}} @keyframes ty{to{clip-path:inset(0 0 0 0)}} @keyframes gz{to{stroke-dashoffset:0}}"
    info = dict(next30=q(next30, .5), ye=q(ye, .5), p_beat=p_beat, mae=mae, naive=naive, cover=cover)
    return frame(W, H, "// FORECAST", "./forecast --horizon 12w", "\n".join(b), css), info


if __name__ == "__main__":
    (OUT / "overview.svg").write_text(overview())
    (OUT / "history.svg").write_text(history())
    svg, info = forecast()
    (OUT / "forecast.svg").write_text(svg)
    print(f"last year: {last_year_total} · rendered.", {k: round(v, 1) for k, v in info.items()})
