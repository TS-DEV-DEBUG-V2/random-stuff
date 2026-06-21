import sys, os, json, re, subprocess, urllib.request, urllib.error

def get(url, headers=None, method="GET"):
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, headers=headers or {}, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} on {url}\n{body[:500]}")

def main():
    content_id = sys.argv[1] if len(sys.argv) > 1 else "eqzFFE"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "downloads"
    os.makedirs(outdir, exist_ok=True)

    acc = json.loads(get("https://api.gofile.io/accounts", method="POST"))
    if acc.get("status") != "ok":
        sys.exit(f"account creation failed: {acc}")
    token = acc["data"]["token"]
    print(f"token: {token[:6]}...")

    js = get("https://gofile.io/dist/js/global.js")
    m = re.search(r'appdata\.wt\s*=\s*"([^"]+)"', js) or \
        re.search(r'\bwt\s*[:=]\s*"([0-9a-zA-Z]{4,})"', js)
    if not m:
        sys.exit("could not scrape wt token from global.js")
    wt = m.group(1)
    print(f"wt: {wt}")

    api = f"https://api.gofile.io/contents/{content_id}?wt={wt}"
    data = json.loads(get(api, headers={"Authorization": f"Bearer {token}"}))
    if data.get("status") != "ok":
        sys.exit(f"contents api failed: {json.dumps(data)[:500]}")

    node = data["data"]
    children = node.get("children")
    if children is None and node.get("type") == "file":
        children = {node["id"]: node}
    if not children:
        sys.exit(f"no children found. response: {json.dumps(node)[:500]}")

    files = [c for c in children.values() if c.get("type") == "file"]
    if not files:
        sys.exit(f"no downloadable files. children: {json.dumps(children)[:500]}")

    print(f"found {len(files)} file(s)")
    for c in files:
        link = c.get("link")
        name = c.get("name", "file")
        if not link:
            print(f"skip {name}: no link")
            continue
        print(f"downloading {name}")
        rc = subprocess.run([
            "aria2c", "-x16", "-s16", "-d", outdir, "-o", name,
            f"--header=Cookie: accountToken={token}",
            link
        ]).returncode
        if rc != 0:
            sys.exit(f"aria2c failed on {name} (rc={rc})")

    print("done")

if __name__ == "__main__":
    main()
