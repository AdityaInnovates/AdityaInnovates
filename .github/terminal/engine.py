#!/usr/bin/env python3
"""
void terminal — a README shell driven by GitHub Issues.

A visitor opens an issue titled `term: <command>`. The workflow runs this
script, which executes the (fake) command, replies on the issue, re-renders
assets/terminal.svg, updates the README, and closes the issue.

Inputs come from env vars only (never interpolated into shell):
  ISSUE_TITLE, ISSUE_USER
Outputs:
  .github/terminal/state.json, assets/terminal.svg, README.md, reply.md
"""
import hashlib, html, json, os, random, re, datetime, pathlib

ROOT   = pathlib.Path(__file__).resolve().parents[2]
STATE  = ROOT / ".github/terminal/state.json"
SVG    = ROOT / "assets/terminal.svg"
README = ROOT / "README.md"
REPLY  = ROOT / "reply.md"

REPO      = "AdityaInnovates/AdityaInnovates"
SALT      = "void-7c1e"
FLAG_SHA  = "8dc7be45456324453bff74c4b7eeee4deb283815c5eacc4bb728a257300b6842"
MAX_LEN   = 100
PROOF_CMD = ('F=$(printf %s "flag{...}" | sha256sum | cut -d" " -f1); '
             'printf %s "$F:your-github-username" | sha256sum')
HISTORY   = 4
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

INTERCEPTED = "NzM3OTZlNzQ3YjY1MzE2MTc0NWYzMDVmMzE2NjVmNmE3NTMzNjUzMzVmMzE1Zjc5MzE2OTMzN2Q="

FORTUNES = [
    "the only secure computer is one that's off. and even then.",
    "every abstraction leaks. find where.",
    "trust the hardware? the hardware has firmware.",
    "undefined behaviour is where the fun lives.",
    "anonymity is not hiding. it is choosing what to show.",
    "read the source. then read the assembly. then doubt both.",
]


# ------------------------------------------------------------------ helpers
def ghost(user: str) -> str:
    return "ghost_" + hashlib.sha256((SALT + user.lower()).encode()).hexdigest()[:4]


def clean(s: str) -> str:
    s = "".join(ch for ch in s if ch.isprintable() and ch not in "`<>")
    return re.sub(r"\s+", " ", s).strip()[:MAX_LEN]


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"sessions": 0, "history": [], "solvers": [], "ghosts": []}


# ------------------------------------------------------------------ commands
# each returns (svg_lines, markdown_reply). svg_lines are short (<=4 lines).
def run(cmd: str, user: str, st: dict):
    me = ghost(user)
    argv = cmd.split(" ")
    c = argv[0].lower() if argv and argv[0] else ""
    arg = " ".join(argv[1:])
    solved = me in [s["who"] for s in st["solvers"]]

    if c in ("help", "?", "man"):
        lines = ["whoami  ls  cat <file>  nmap  fortune  uname",
                 "hint <1-3>  decrypt <proof>  sudo  ping"]
        return lines, "```\n" + "\n".join(lines) + "\n```"

    if c == "whoami":
        lines = [f"{me}", "you are no one here. that's a compliment."]
        return lines, "```\n" + "\n".join(lines) + "\n```\nYour handle is derived from a salted hash. Nobody sees your username in the terminal."

    if c in ("ls", "dir"):
        files = "about.txt  arsenal.txt  intercepted.bin  .secret"
        return [files], f"```\n$ ls -a\n{files}\n```"

    if c == "cat":
        f = arg.strip()
        if f == "about.txt":
            txt = ("systems · security · full-stack.\n"
                   "reverse engineering, memory corruption, kernel internals,\n"
                   "network protocols — and shipping real web & mobile products.")
            return ["systems · security · full-stack.", "breaks things to understand them."], "```\n" + txt + "\n```"
        if f == "arsenal.txt":
            txt = ("low-level : C  C++  Rust  x86_64/ARM asm  Python  Go\n"
                   "reversing : Ghidra  GDB+pwndbg  radare2  QEMU\n"
                   "offense   : Burp  Wireshark  Nmap  Kali\n"
                   "cover     : TypeScript  Node  React  Next.js  React Native")
            return ["C · Rust · asm · Ghidra · GDB · Burp · Wireshark", "(full list sent to your issue)"], "```\n" + txt + "\n```"
        if f == "intercepted.bin":
            return [INTERCEPTED[:44] + "…"], f"```\n{INTERCEPTED}\n```\nThree layers. Peel them. Stuck? `hint 1`"
        if f == ".secret":
            if solved:
                return ["access granted.", "you already know where I live."], (
                    "```\naccess granted.\n```\n"
                    "You earned this: most people scroll past. You didn't. "
                    "Open a channel (links at the bottom of the profile) and say the word **ring0**.")
            return ["cat: .secret: Permission denied"], "```\ncat: .secret: Permission denied\n```\nProve yourself first. `cat intercepted.bin`"
        return [f"cat: {f or '?'}: No such file"], f"```\ncat: {f}: No such file or directory\n```\nTry `ls`."

    if c == "hint":
        hints = {"1": "ends in '='. you've seen this padding before.",
                 "2": "only 0-9a-f, in pairs. two nibbles, one byte.",
                 "3": "caesar would be proud. half the alphabet."}
        h = hints.get(arg.strip(), "usage: hint <1|2|3>")
        return [h], f"```\n{h}\n```"

    if c in ("decrypt", "submit"):
        guess = (arg.split() or [""])[0].lower()
        proofs = {hashlib.sha256(f"{FLAG_SHA}:{u}".encode()).hexdigest() for u in (user, user.lower())}
        howto = "```bash\n" + PROOF_CMD + "\n```"
        if hashlib.sha256(arg.strip().encode()).hexdigest() == FLAG_SHA:
            return ["OPSEC FAIL: plaintext flag on a public issue.", "no credit. hash it. see the reply."], (
                "```\nOPSEC FAIL\n```\nYou just posted the flag in plaintext on a **public** issue. "
                "Real operators never ship secrets in the clear.\n\n"
                "Submit a proof bound to your identity instead:\n\n" + howto +
                "\n\nThen open `term: decrypt <that hash>`.")
        if guess in proofs:
            if not solved:
                st["solvers"].append({"who": me, "at": datetime.date.today().isoformat()})
            n = [s["who"] for s in st["solvers"]].index(me) + 1
            return ["proof verified. root obtained.", f"{me} joins the hall of shadows (#{n})."], (
                f"```\nproof verified. root obtained.\n```\nYou're **#{n}** in the Hall of Shadows. "
                "Now try `cat .secret`.")
        return ["proof rejected. try harder."], (
            "```\nproof rejected.\n```\nDon't send the flag itself. Send a proof bound to your username:\n\n" + howto)

    if c == "sudo":
        return [f"{me} is not in the sudoers file.", "this incident will be reported."], \
               "```\nThis incident will be reported.\n```\n(it won't. but it felt real, right?)"

    if c == "nmap":
        lines = ["22/tcp   filtered ssh", "443/tcp  open     you", "1337/tcp open     ???"]
        return lines, "```\nPORT     STATE    SERVICE\n" + "\n".join(lines) + "\n```"

    if c == "ping":
        ms = random.randint(3, 42)
        return [f"64 bytes from void: icmp_seq=1 ttl=64 time={ms} ms"], f"```\npong. {ms} ms. I see you.\n```"

    if c == "uname":
        s = "Linux void 6.x-hardened #1 SMP PREEMPT x86_64 GNU/Linux"
        return [s], f"```\n{s}\n```"

    if c == "fortune":
        f = random.choice(FORTUNES)
        return [f], f"> {f}"

    if c == "rm":
        return ["nice try."], "```\nnice try.\n```"

    if c in ("exit", "logout"):
        return ["there is no exit. only other terminals."], "```\nthere is no exit.\n```"

    return [f"{c or '?'}: command not found. try 'help'"], f"```\n{c}: command not found\n```\nTry `term: help`."


# ------------------------------------------------------------------ rendering
def esc(s):
    return html.escape(s, quote=True)


def render_svg(st):
    W = 1000
    LH = 22
    hist = st["history"][-HISTORY:]
    rows = []  # (kind, text, entry_index)
    for i, h in enumerate(hist):
        rows.append(("cmd", h, i))
        for ln in h["out"]:
            rows.append(("out", ln, i))
        rows.append(("gap", "", i))
    H = 70 + LH * max(len(rows), 6) + 30

    per = 2.6  # seconds per entry
    total = per * max(len(hist), 1) + 5
    css, body, clips = [], [], []
    y = 66
    for r, (kind, val, i) in enumerate(rows):
        t0 = i * per / total * 100
        if kind == "cmd":
            t1 = (i * per + 1.1) / total * 100
            css.append(f"@keyframes w{r}{{0%,{t0:.2f}%{{width:0}}{t1:.2f}%,100%{{width:{W}px}}}}")
            clips.append(f'<clipPath id="c{r}"><rect x="0" y="{y-16}" height="{LH}" '
                         f'style="animation:w{r} {total:.1f}s linear infinite"/></clipPath>')
            body.append(
                f'<g clip-path="url(#c{r})"><text x="24" y="{y}">'
                f'<tspan fill="#00ff41">{esc(val["who"])}@void</tspan><tspan fill="#8b949e">:~$ </tspan>'
                f'<tspan fill="#e6ffe9">{esc(val["cmd"])}</tspan></text></g>')
        elif kind == "out":
            t1 = (i * per + 1.4) / total * 100
            css.append(f"@keyframes o{r}{{0%,{t1:.2f}%{{opacity:0}}{t1+0.01:.2f}%,100%{{opacity:1}}}}")
            body.append(f'<text x="24" y="{y}" fill="#9fb3a4" style="animation:o{r} {total:.1f}s steps(1) infinite">{esc(val)}</text>')
        y += LH if kind != "gap" else LH // 2
    # blinking cursor prompt at end
    t_end = (len(hist) * per) / total * 100
    css.append(f"@keyframes pe{{0%,{t_end:.2f}%{{opacity:0}}{t_end+0.01:.2f}%,100%{{opacity:1}}}}")
    body.append(f'<g style="animation:pe {total:.1f}s steps(1) infinite"><text x="24" y="{y+6}">'
                f'<tspan fill="#00ff41">you@void</tspan><tspan fill="#8b949e">:~$ </tspan>'
                f'<tspan class="cur" fill="#00ff41">█</tspan></text></g>')

    stat = f'sessions: {st["sessions"]}  ·  ghosts: {len(st["ghosts"])}  ·  root obtained: {len(st["solvers"])}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text {{ font: 14px {MONO}; white-space: pre; }}
.cur {{ animation: b 1s steps(1) infinite; }} @keyframes b {{ 50% {{ opacity: 0 }} }}
.live {{ animation: lv 1.6s ease-in-out infinite; }} @keyframes lv {{ 50% {{ opacity: .25 }} }}
{"".join(css)}
</style>
<defs>{"".join(clips)}
<pattern id="l" width="3" height="3" patternUnits="userSpaceOnUse"><rect width="3" height="1" fill="#000" fill-opacity=".4"/></pattern>
</defs>
<rect width="{W}" height="{H}" rx="8" fill="#050807" stroke="#00ff41" stroke-opacity=".3"/>
<circle cx="18" cy="16" r="4" fill="#ff0055"/><circle cx="32" cy="16" r="4" fill="#ffb000"/><circle cx="46" cy="16" r="4" fill="#00ff41"/>
<text x="{W//2}" y="20" text-anchor="middle" fill="#8b949e" style="font-size:11px">void — public shell — last {len(hist)} sessions</text>
<circle class="live" cx="{W-70}" cy="16" r="4" fill="#ff0055"/><text x="{W-60}" y="20" fill="#ff0055" style="font-size:11px">LIVE</text>
<line x1="0" y1="32" x2="{W}" y2="32" stroke="#00ff41" stroke-opacity=".15"/>
{"".join(body)}
<text x="24" y="{H-12}" fill="#8b949e" style="font-size:11px">{esc(stat)}</text>
<rect width="{W}" height="{H}" rx="8" fill="url(#l)"/>
</svg>'''


def render_hall(st):
    if not st["solvers"]:
        return ("```console\n$ cat /var/log/hall_of_shadows\n"
                "(empty) — nobody has cracked intercepted.bin yet. be the first.\n```")
    rows = "\n".join(f"#{i+1:<3} {s['who']:<12} {s['at']}" for i, s in enumerate(st["solvers"][-10:]))
    return f"```console\n$ cat /var/log/hall_of_shadows\n{rows}\n```"


def patch_readme(st):
    t = README.read_text()
    new = f"<!--HALL:START-->\n{render_hall(st)}\n<!--HALL:END-->"
    t = re.sub(r"<!--HALL:START-->.*?<!--HALL:END-->", new, t, flags=re.S)
    README.write_text(t)


# ------------------------------------------------------------------ main
def main():
    title = os.environ.get("ISSUE_TITLE", "")
    user = os.environ.get("ISSUE_USER", "anon")
    st = load()
    if os.environ.get("RENDER_ONLY"):
        SVG.write_text(render_svg(st)); patch_readme(st); return

    m = re.match(r"^\s*term\s*:\s*(.*)$", title, re.I)
    if not m:
        return
    cmd = clean(m.group(1)) or "help"
    out, reply = run(cmd, user, st)
    me = ghost(user)

    st["sessions"] += 1
    if me not in st["ghosts"]:
        st["ghosts"].append(me)
    # never store the flag guess itself in public history
    shown = "decrypt ********" if cmd.lower().startswith("decrypt") else cmd
    st["history"] = (st["history"] + [{"who": me, "cmd": shown, "out": [clean(o) for o in out][:4]}])[-HISTORY:]

    STATE.write_text(json.dumps(st, indent=1))
    SVG.write_text(render_svg(st))
    patch_readme(st)
    REPLY.write_text(
        f"**`{me}@void:~$ {shown}`**\n\n{reply}\n\n"
        f"<sub>Your session is now on the [profile](https://github.com/{REPO}) "
        f"(may take a minute to show — GitHub caches images). This issue closes itself.</sub>")


if __name__ == "__main__":
    main()
