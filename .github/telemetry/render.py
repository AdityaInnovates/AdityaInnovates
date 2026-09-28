#!/usr/bin/env python3
"""
Render telemetry SVGs from .github/telemetry/data.json

  assets/telemetry/overview.svg  stat tiles + 53-week heatmap
  assets/telemetry/history.svg   monthly history since first activity + languages
  assets/telemetry/forecast.svg  12-week forecast (damped Holt, bootstrap bands)

Pure stdlib. The forecast is a real statistical model fitted to the data,
back-tested on held-out weeks; the numbers it prints are its actual output.
"""
import datetime as dt, html, json, math, pathlib, random, statistics as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / ".github/telemetry/data.json").read_text())
OUT = ROOT / "assets/telemetry"
OUT.mkdir(parents=True, exist_ok=True)

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
BG, LINE = "#050807", "#1c2b20"
INK, INK2, MUTED = "#e6ffe9", "#9fb3a4", "#6e7d72"
ACC, FC = "#00ff41", "#e346c9"                    # actual / forecast (validated pair, + dashed + labels)
SEQ = ["#0d1a11", "#0b4d1f", "#08802f", "#04b83c", "#00ff41"]   # one hue, dark -> bright
esc = lambda s: html.escape(str(s), quote=True)
fmt = lambda n: f"{n:,.0f}"

# ------------------------------------------------------------------ data
days = {dt.date.fromisoformat(k): v for k, v in DATA["days"].items()}
today = max(days)
series = [(d, days.get(d, 0)) for d in (today - dt.timedelta(i) for i in range((today - min(days)).days, -1, -1))]
first_active = next(d for d, v in series if v > 0)
total = sum(v for _, v in series)
year_total = sum(v for d, v in series if d.year == today.year)
last365 = [v for d, v in series if (today - d).days < 365]
active_pct = 100 * sum(1 for v in last365 if v) / len(last365)
best_day = max(series, key=lambda x: x[1])

def streaks():
    longest = cur = run = 0
    for _, v in series:
        run = run + 1 if v else 0
        longest = max(longest, run)
    i = len(series) - 1
    if series[i][1] == 0:
        i -= 1                      # today not done yet
    while i >= 0 and series[i][1]:
        cur += 1; i -= 1
    return cur, longest
cur_streak, long_streak = streaks()

def frame(w, h, title, sub, body, extra_css=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<style>
text{{font-family:{MONO};}}
.h{{font-size:12px;letter-spacing:2px;fill:{MUTED}}} .s{{font-size:11px;fill:{MUTED}}}
.v{{font-size:24px;font-weight:700;fill:{INK}}} .l{{font-size:10px;letter-spacing:1.5px;fill:{MUTED}}}
.t{{font-size:11px;fill:{INK2}}} .b{{font-size:12px;fill:{INK}}}
.cur{{animation:bk 1s steps(1) infinite}} @keyframes bk{{50%{{opacity:0}}}}
.scan{{animation:sc 6s linear infinite}} @keyframes sc{{from{{transform:translateY(-30px)}}to{{transform:translateY({h}px)}}}}
{extra_css}
</style>
<defs><pattern id="sl" width="3" height="3" patternUnits="userSpaceOnUse"><rect width="3" height="1" fill="#000" fill-opacity=".35"/></pattern></defs>
<rect width="{w}" height="{h}" rx="10" fill="{BG}" stroke="{ACC}" stroke-opacity=".25"/>
<text x="24" y="30" class="h">{esc(title)}<tspan class="cur" fill="{ACC}"> _</tspan></text>
<text x="{w-24}" y="30" class="s" text-anchor="end">{esc(sub)}</text>
<line x1="24" y1="42" x2="{w-24}" y2="42" stroke="{LINE}"/>
{body}
<rect class="scan" width="{w}" height="30" fill="{ACC}" fill-opacity=".025"/>
<rect width="{w}" height="{h}" rx="10" fill="url(#sl)"/>
</svg>'''

stamp = f"@{DATA['user']} · updated {DATA['generated'][:10]}"

# ------------------------------------------------------------------ 1. overview
def overview():
    W, H = 1000, 330
    tiles = [("ALL-TIME", fmt(total)), (f"{today.year}", fmt(year_total)), ("CURRENT STREAK", f"{cur_streak}d"),
             ("LONGEST STREAK", f"{long_streak}d"), ("BEST DAY", f"{best_day[1]}"), ("ACTIVE · 365D", f"{active_pct:.0f}%")]
    tw = (W - 48) / len(tiles)
    body = []
    for i, (lab, val) in enumerate(tiles):
        x = 24 + i * tw
        body.append(f'<g style="animation:fi .6s {0.1*i:.1f}s both"><text x="{x}" y="78" class="v">{esc(val)}</text>'
                    f'<text x="{x}" y="96" class="l">{esc(lab)}</text></g>')
    # heatmap: 53 weeks ending today, Sunday-first like GitHub
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)
    vals = [v for d, v in series if d >= start and v > 0]
    qs = [0] + ([st.quantiles(vals, n=4)[i] for i in range(3)] if len(vals) >= 4 else [1, 2, 3])
    def lvl(v):
        if v == 0: return 0
        return 1 + sum(v > q for q in qs[1:])
    cs, gap, x0, y0 = 14, 3, 64, 128
    months = {}
    d = start; col = 0
    while d <= today:
        row = (d.weekday() + 1) % 7
        if row == 0 and d != start: col += 1
        v = days.get(d, 0); L = lvl(v)
        x, y = x0 + col * (cs + gap), y0 + row * (cs + gap)
        body.append(f'<rect x="{x}" y="{y}" width="{cs}" height="{cs}" rx="3" fill="{SEQ[L]}" '
                    f'style="animation:fi .4s {0.012*col:.2f}s both"><title>{v} on {d.isoformat()}</title></rect>')
        if d.day <= 7 and row == 0: months[col] = d.strftime("%b").lower()
        d += dt.timedelta(1)
    for c, m in months.items():
        body.append(f'<text x="{x0 + c*(cs+gap)}" y="{y0-10}" class="s">{m}</text>')
    for r, n in ((1, "mon"), (3, "wed"), (5, "fri")):
        body.append(f'<text x="{x0-10}" y="{y0 + r*(cs+gap) + 11}" class="s" text-anchor="end">{n}</text>')
    # today marker
    trow = (today.weekday() + 1) % 7
    body.append(f'<rect x="{x0 + col*(cs+gap) - 2}" y="{y0 + trow*(cs+gap) - 2}" width="{cs+4}" height="{cs+4}" rx="4" fill="none" stroke="{INK}" stroke-width="1.5" class="cur"/>')
    # legend
    ly = y0 + 7 * (cs + gap) + 16
    body.append(f'<text x="{x0}" y="{ly+10}" class="s">less</text>')
    for i, c in enumerate(SEQ):
        body.append(f'<rect x="{x0 + 38 + i*17}" y="{ly}" width="13" height="13" rx="3" fill="{c}"/>')
    body.append(f'<text x="{x0 + 38 + 5*17 + 4}" y="{ly+10}" class="s">more</text>')
    body.append(f'<text x="{W-24}" y="{ly+10}" class="s" text-anchor="end">53 weeks · {fmt(sum(last365))} contributions in the last 365 days</text>')
    css = "@keyframes fi{from{opacity:0}to{opacity:1}}"
    return frame(W, H, "// TELEMETRY", stamp, "\n".join(body), css)

# ------------------------------------------------------------------ 2. history
def history():
    W, H = 1000, 320
    yt_all = {}
    for dd, v in series: yt_all[dd.year] = yt_all.get(dd.year, 0) + v
    y_start = min((y for y, t in yt_all.items() if t >= 50), default=first_active.year)
    m0 = dt.date(y_start, 1, 1)
    months, d = [], m0
    while d <= today:
        months.append(d); d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    mv = {m: 0 for m in months}
    for dd, v in series:
        k = dt.date(dd.year, dd.month, 1)
        if k in mv: mv[k] += v
    vmax = max(mv.values()) or 1
    x0, y0, pw, ph = 56, 70, 700, 190
    bw = pw / len(months)
    nice = 10 ** math.floor(math.log10(vmax)); top = math.ceil(vmax / nice) * nice
    body = []
    for f in (0, .5, 1):
        y = y0 + ph - ph * f
        body.append(f'<line x1="{x0}" y1="{y}" x2="{x0+pw}" y2="{y}" stroke="{LINE}"/>'
                    f'<text x="{x0-8}" y="{y+4}" class="s" text-anchor="end">{fmt(top*f)}</text>')
    peak = max(mv, key=mv.get)
    for i, m in enumerate(months):
        v = mv[m]; h = ph * v / top
        x = x0 + i * bw
        if h > 0:
            r = min(3, bw / 2 - 1, h)
            body.append(f'<path d="M{x+1:.1f},{y0+ph} v{-(h-r):.1f} q0,{-r:.1f} {r:.1f},{-r:.1f} h{bw-2-2*r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} v{h-r:.1f}z" '
                        f'fill="{ACC if m == peak else SEQ[3]}" style="transform-origin:{x:.1f}px {y0+ph}px;animation:gr .7s {0.008*i:.2f}s both"><title>{m:%b %Y}: {v}</title></path>')
        if m.month == 1:
            yt = sum(mv[k] for k in months if k.year == m.year)
            body.append(f'<line x1="{x:.1f}" y1="{y0-6}" x2="{x:.1f}" y2="{y0+ph}" stroke="{LINE}" stroke-dasharray="2 3"/>'
                        f'<text x="{x+4:.1f}" y="{y0+ph+16}" class="t">{m.year}</text>'
                        f'<text x="{x+4:.1f}" y="{y0+ph+30}" class="s">{fmt(yt)}</text>')
    pi = months.index(peak); px = x0 + pi * bw + bw / 2; py = y0 + ph - ph * mv[peak] / top
    anc = "end" if px > x0 + pw - 90 else "middle"
    body.append(f'<text x="{px + (4 if anc == "end" else 0):.1f}" y="{py-8:.1f}" class="b" text-anchor="{anc}">peak {peak:%b %y} · {mv[peak]}</text>')
    # languages (magnitude, single hue, name-labelled)
    langs = sorted(DATA["languages"].items(), key=lambda kv: -kv[1]["size"])[:6]
    ls = sum(v["size"] for _, v in langs) or 1
    lx = 800; body.append(f'<text x="{lx}" y="{y0}" class="l">LANGUAGES</text>')
    for i, (name, v) in enumerate(langs):
        p = v["size"] / ls; y = y0 + 22 + i * 30
        body.append(f'<text x="{lx}" y="{y}" class="t">{esc(name)}</text><text x="{W-24}" y="{y}" class="s" text-anchor="end">{"&lt;1" if p < .01 else f"{p*100:.0f}"}%</text>'
                    f'<rect x="{lx}" y="{y+6}" width="{W-24-lx}" height="4" rx="2" fill="{LINE}"/>'
                    f'<rect x="{lx}" y="{y+6}" width="{max(3,(W-24-lx)*p):.1f}" height="4" rx="2" fill="{SEQ[3]}" style="transform-origin:{lx}px 0;animation:gx 1s {0.3+0.1*i:.1f}s both"/>')
    css = ("@keyframes gr{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
           "@keyframes gx{from{transform:scaleX(0)}to{transform:scaleX(1)}}")
    return frame(W, H, "// HISTORY", f"monthly contributions since {m0:%Y}", "\n".join(body), css)

# ------------------------------------------------------------------ 3. forecast
def weekly():
    """7-day buckets ending today (no partial week)."""
    n = (today - first_active).days // 7
    return [sum(days.get(today - dt.timedelta(days=7*k + j), 0) for j in range(7)) for k in range(n, -1, -1)]

T = lambda y: math.sqrt(max(y, 0))      # variance-stabilising transform for counts
IT = lambda z: max(z, 0) ** 2

def holt_fit(z, a, b, phi):
    l, t = z[0], 0.0; res = []
    for y in z[1:]:
        f = l + phi * t; res.append(y - f)
        nl = a * y + (1 - a) * (l + phi * t)
        t = b * (nl - l) + (1 - b) * phi * t; l = nl
    return l, t, res

def holt_best(z):
    best = None
    for a in (.05, .1, .15, .2, .3, .4, .5, .6):
        for b in (.01, .03, .05, .1, .2):
            for phi in (.8, .88, .94, .98):
                l, t, r = holt_fit(z, a, b, phi)
                sse = sum(e * e for e in r[4:])
                if best is None or sse < best[0]: best = (sse, a, b, phi, l, t, r)
    return best[1:]

def simulate(z, H, n=3000, seed=7):
    a, b, phi, l0, t0, res = holt_best(z)
    rnd = random.Random(seed); res = res[-104:] or [0.0]
    paths = []
    for _ in range(n):
        l, t, p = l0, t0, []
        for h in range(H):
            y = l + phi * t + rnd.choice(res)
            nl = a * y + (1 - a) * (l + phi * t); t = b * (nl - l) + (1 - b) * phi * t; l = nl
            p.append(IT(y))
        paths.append(p)
    return paths, (a, b, phi)

def q(xs, p):
    s = sorted(xs); return s[min(len(s) - 1, int(p * len(s)))]

def forecast():
    W, H = 1000, 372
    wk = weekly(); z = [T(v) for v in wk]
    HZN = 12
    eoy = dt.date(today.year, 12, 31); rem = (eoy - today).days
    full, frac = divmod(rem, 7)
    SIM = max(HZN, full + 1)
    paths, (a, b, phi) = simulate(z, SIM)
    med = [q([p[h] for p in paths], .5) for h in range(HZN)]
    lo = [q([p[h] for p in paths], .1) for h in range(HZN)]
    hi = [q([p[h] for p in paths], .9) for h in range(HZN)]
    # back-test: fit on data minus last 8 weeks, compare median to actual vs naive
    bt = 8
    bp, _ = simulate(z[:-bt], bt, n=800, seed=11)
    bmed = [q([p[h] for p in bp], .5) for h in range(bt)]
    act = wk[-bt:]
    mae = sum(abs(x - y) for x, y in zip(bmed, act)) / bt
    naive = sum(abs(wk[-bt - 1] - y) for y in act) / bt
    cover = sum(q([p[h] for p in bp], .1) <= act[h] <= q([p[h] for p in bp], .9) for h in range(bt))
    # predictions
    next30 = [sum(p[:4]) + p[4] * 2 / 7 for p in paths]
    def rest(p):
        return sum(p[:full]) + p[full] * frac / 7
    ye = [year_total + rest(p) for p in paths]
    prev = sum(v for d, v in series if d.year == today.year - 1)
    p_beat = 100 * sum(x > prev for x in ye) / len(ye)
    dow = [0] * 7
    for d, v in series:
        if (today - d).days < 182: dow[d.weekday()] += v
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    busiest = names[max(range(7), key=dow.__getitem__)]
    trend = (st.mean(wk[-8:]) - st.mean(wk[-16:-8])) / (st.mean(wk[-16:-8]) or 1) * 100

    # ---- chart
    hist_n = 40
    hw = wk[-hist_n:]
    x0, y0, pw, ph = 56, 70, 600, 200
    N = hist_n + HZN
    top = max(max(hw), max(hi)) * 1.1 or 1
    X = lambda i: x0 + pw * i / (N - 1)
    Y = lambda v: y0 + ph - ph * v / top
    body = []
    for f in (0, .5, 1):
        y = y0 + ph - ph * f
        body.append(f'<line x1="{x0}" y1="{y}" x2="{x0+pw}" y2="{y}" stroke="{LINE}"/>'
                    f'<text x="{x0-8}" y="{y+4}" class="s" text-anchor="end">{fmt(top*f)}</text>')
    now = X(hist_n - 1)
    body.append(f'<rect x="{now}" y="{y0}" width="{x0+pw-now}" height="{ph}" fill="{FC}" fill-opacity=".04"/>'
                f'<line x1="{now}" y1="{y0-8}" x2="{now}" y2="{y0+ph}" stroke="{INK2}" stroke-dasharray="3 3"/>'
                f'<text x="{now+6}" y="{y0-10}" class="s">now → forecast</text>')
    area = f"M{X(0)},{y0+ph} " + " ".join(f"L{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(hw)) + f" L{X(hist_n-1)},{y0+ph}Z"
    body.append(f'<path d="{area}" fill="{ACC}" fill-opacity=".08"/>')
    act_line = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(hw))
    body.append(f'<path d="{act_line}" fill="none" stroke="{ACC}" stroke-width="2" stroke-linejoin="round" pathLength="1" '
                f'style="stroke-dasharray:1;animation:dr 2.2s ease-out both"/>')
    fi = list(range(hist_n - 1, N))
    band = (" ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for k, (i, v) in enumerate(zip(fi, [hw[-1]] + hi)))
            + " " + " ".join(f"L{X(i):.1f},{Y(v):.1f}" for i, v in reversed(list(zip(fi, [hw[-1]] + lo)))) + "Z")
    body.append(f'<path d="{band}" fill="{FC}" fill-opacity=".16" style="animation:fi 1s 2s both"/>')
    fl = " ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for k, (i, v) in enumerate(zip(fi, [hw[-1]] + med)))
    body.append(f'<path d="{fl}" fill="none" stroke="{FC}" stroke-width="2" stroke-dasharray="6 4" style="animation:fi .8s 2.2s both"/>')
    body.append(f'<circle cx="{X(hist_n-1)}" cy="{Y(hw[-1])}" r="4" fill="{ACC}" stroke="{BG}" stroke-width="2"/>')
    # direct labels
    body.append(f'<text x="{X(2)}" y="{y0+ph+18}" class="t"><tspan fill="{ACC}">━</tspan> actual (weekly)</text>'
                f'<text x="{X(hist_n+1)}" y="{y0+ph+18}" class="t"><tspan fill="{FC}">╌</tspan> median  <tspan fill="{FC}" fill-opacity=".5">█</tspan> 80% band</text>')
    body.append(f'<text x="{x0}" y="{y0+ph+40}" class="s">last {hist_n} weeks · next {HZN} weeks</text>')
    # prediction panel
    px = 700
    rows = [
        ("NEXT 30 DAYS", f"{fmt(q(next30,.5))}", f"80%: {fmt(q(next30,.1))}–{fmt(q(next30,.9))}"),
        (f"{today.year} PROJECTED", f"{fmt(q(ye,.5))}", f"80%: {fmt(q(ye,.1))}–{fmt(q(ye,.9))}"),
        (f"BEATS {today.year-1} ({fmt(prev)})", f"{p_beat:.0f}%", "probability, 3,000 simulations"),
        ("MOMENTUM · 8W vs PRIOR 8W", f"{trend:+.0f}%", f"busiest day lately: {busiest}"),
    ]
    for i, (lab, val, sub) in enumerate(rows):
        y = y0 + 6 + i * 66
        body.append(f'<g style="animation:fi .5s {2.4+0.25*i:.2f}s both"><text x="{px}" y="{y}" class="l">{esc(lab)}</text>'
                    f'<text x="{px}" y="{y+26}" class="v">{esc(val)}</text><text x="{px}" y="{y+42}" class="s">{esc(sub)}</text></g>')
    model = (f"model: damped Holt on √counts (α={a} β={b} φ={phi}) + bootstrap residuals · "
             f"backtest {bt}w: MAE {mae:.1f}/wk vs naive {naive:.1f} · {cover}/{bt} inside band")
    body.append(f'<text x="24" y="{H-16}" class="s">{esc(model)}</text>')
    css = ("@keyframes fi{from{opacity:0}to{opacity:1}}"
           "@keyframes dr{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}")
    info = dict(next30=q(next30, .5), ye=q(ye, .5), p_beat=p_beat, mae=mae, naive=naive, cover=cover)
    return frame(W, H, "// FORECAST", "statistical model · not a promise", "\n".join(body), css), info

if __name__ == "__main__":
    (OUT / "overview.svg").write_text(overview())
    (OUT / "history.svg").write_text(history())
    svg, info = forecast()
    (OUT / "forecast.svg").write_text(svg)
    print("rendered.", {k: round(v, 1) for k, v in info.items()})
