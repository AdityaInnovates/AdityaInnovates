#!/usr/bin/env python3
"""
Collect contribution + language data for the telemetry charts.

Primary: GitHub GraphQL API (needs GITHUB_TOKEN; add a PAT as TELEMETRY_TOKEN
to include private-repo contribution counts).
Fallback: the public contribution calendar HTML (no token needed).

Writes .github/telemetry/data.json
"""
import datetime as dt, json, os, pathlib, re, urllib.request

USER = os.environ.get("TELEMETRY_USER", "AdityaInnovates")
OUT = pathlib.Path(__file__).resolve().parent / "data.json"
TOKEN = os.environ.get("TELEMETRY_TOKEN") or os.environ.get("GITHUB_TOKEN")
UA = {"User-Agent": "void-telemetry"}


def http(url, data=None, headers=None):
    h = {**UA, **(headers or {})}
    if TOKEN and url.startswith("https://api.github.com/") and "Authorization" not in h:
        h["Authorization"] = f"bearer {TOKEN}"       # 1,000+ req/h instead of 60
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def gql(query, **vars):
    body = json.dumps({"query": query, "variables": vars}).encode()
    r = json.loads(http("https://api.github.com/graphql", body,
                        {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"}))
    if "errors" in r:
        raise RuntimeError(r["errors"])
    return r["data"]


def via_graphql(days_too=True):
    created = gql("query($u:String!){user(login:$u){createdAt}}", u=USER)["user"]["createdAt"][:4]
    days = {}
    today = dt.date.today()
    for y in (range(int(created), today.year + 1) if days_too else ()):
        frm = f"{y}-01-01T00:00:00Z"
        to = f"{y}-12-31T23:59:59Z" if y < today.year else today.isoformat() + "T23:59:59Z"
        d = gql("""query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
                 contributionsCollection(from:$f,to:$t){contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
                u=USER, f=frm, t=to)
        for w in d["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for c in w["contributionDays"]:
                days[c["date"]] = c["contributionCount"]
    langs = {}
    cur = None
    while True:
        d = gql("""query($u:String!,$c:String){user(login:$u){repositories(first:100,after:$c,ownerAffiliations:OWNER,isFork:false){
                 pageInfo{hasNextPage endCursor} nodes{languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}""",
                u=USER, c=cur)["user"]["repositories"]
        for n in d["nodes"]:
            for e in n["languages"]["edges"]:
                k = e["node"]["name"]
                langs.setdefault(k, {"size": 0, "color": e["node"]["color"] or "#8b949e"})["size"] += e["size"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        cur = d["pageInfo"]["endCursor"]
    repos = gql("query($u:String!){user(login:$u){repositories(ownerAffiliations:OWNER,privacy:PUBLIC){totalCount}}}", u=USER)["user"]["repositories"]["totalCount"]
    return created, days, langs, "graphql", repos


def via_html():
    prev = json.loads(OUT.read_text()) if OUT.exists() else {}
    try:
        u = json.loads(http(f"https://api.github.com/users/{USER}"))
        created, n_repos = u["created_at"][:4], u.get("public_repos", 0)
    except Exception as e:                           # anonymous REST is rate-limited; the calendar page is not
        print("REST profile unavailable:", str(e)[:80])
        created, n_repos = prev.get("since", "2008"), prev.get("repos", 0)
    days = {}
    today = dt.date.today()
    for y in range(int(created), today.year + 1):
        h = http(f"https://github.com/users/{USER}/contributions?from={y}-01-01&to={y}-12-31")
        ids = dict(re.findall(r'data-date="(\d{4}-\d\d-\d\d)" id="([^"]+)"', h))
        tips = dict(re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', h))
        for date, cid in ids.items():
            if date > today.isoformat():
                continue
            m = re.match(r"(\d[\d,]*) contribution", tips.get(cid, ""))
            days[date] = int(m.group(1).replace(",", "")) if m else 0
    if not days:
        raise RuntimeError("calendar page returned no days")
    langs = prev.get("languages", {})
    try:
        repos = json.loads(http(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
        langs = {}
        for r in repos:
            if r.get("fork") or not r.get("language"):
                continue
            langs.setdefault(r["language"], {"size": 0, "color": "#8b949e"})["size"] += max(r.get("size", 1), 1)
    except Exception as e:
        print("REST repos unavailable, keeping previous languages:", str(e)[:80])
    return created, days, langs, "calendar", n_repos


def main():
    # Daily counts: the public contribution calendar is exactly the graph on the profile
    # (it includes private-repo contributions when "private contributions" is enabled).
    # The API with the Actions token only sees public activity, so it's the fallback.
    langs = repos = None
    try:
        created, days, langs_h, src, repos_h = via_html()
    except Exception as e:
        print("calendar page unavailable, using GraphQL:", str(e)[:120])
        created, days, langs, src, repos = via_graphql()
    else:
        langs, repos = langs_h, repos_h
        if TOKEN:                                    # byte-accurate languages when the API is reachable
            try:
                _, _, langs, _, repos = via_graphql(days_too=False)
            except Exception as e:
                print("graphql languages unavailable:", str(e)[:120])
    OUT.write_text(json.dumps({
        "user": USER, "since": created, "source": src, "repos": repos,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "days": dict(sorted(days.items())), "languages": langs}, indent=0))
    print(f"{len(days)} days, {sum(days.values())} contributions, {len(langs)} languages via {src}")


if __name__ == "__main__":
    main()
