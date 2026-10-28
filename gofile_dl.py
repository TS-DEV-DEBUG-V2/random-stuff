import sys, os, json, subprocess, tempfile, urllib.request, urllib.error, urllib.parse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LANG = "en-US"

SIGNER = r"""
const [, , file, token, ua, lang] = process.argv;
Object.defineProperty(globalThis, "navigator", { value: { userAgent: ua, language: lang }, configurable: true });
globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.document = {};
globalThis.location = { hostname: "gofile.io", href: "https://gofile.io/" };
require("vm").runInThisContext(require("fs").readFileSync(file, "utf8"));
Promise.resolve(globalThis.generateWT(token)).then(v => process.stdout.write(v));
"""

def get(url, headers=None, method="GET"):
    h = {"User-Agent": UA, "Origin": "https://gofile.io", "Referer": "https://gofile.io/"}
    h.update(headers or {})
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} on {url}\n{body[:500]}")

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: gofile_dl.py <id|url> [outdir]")
    content_id = arg.rstrip("/").split("/")[-1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "downloads"
    os.makedirs(outdir, exist_ok=True)

    acc = json.loads(get("https://api.gofile.io/accounts", method="POST"))
    if acc.get("status") != "ok":
        sys.exit(f"account creation failed: {acc}")
    token = acc["data"]["token"]
    print(f"token: {token[:6]}...")

    work = tempfile.mkdtemp()
    wt_path = os.path.join(work, "wt.obf.js")
    signer_path = os.path.join(work, "sign.js")
    with open(wt_path, "w") as f:
        f.write(get("https://gofile.io/js/wt.obf.js"))
    with open(signer_path, "w") as f:
        f.write(SIGNER)

    def sign():
        r = subprocess.run(["node", signer_path, wt_path, token, UA, LANG], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout:
            sys.exit(f"signer failed: {r.stderr[:500]}")
        return r.stdout

    files = []

    def walk(cid, prefix=""):
        q = urllib.parse.urlencode({"page": 1, "pageSize": 1000, "sortField": "name", "sortDirection": 1})
        data = json.loads(get(
            f"https://api.gofile.io/contents/{cid}?{q}",
            headers={"Authorization": f"Bearer {token}", "X-Website-Token": sign(), "X-BL": LANG},
        ))
        if data.get("status") != "ok":
            sys.exit(f"contents api failed: {json.dumps(data)[:500]}")
        node = data["data"]
        if node.get("canAccess") is False:
            sys.exit(f"no access to {cid} (password or private?)")
        if node.get("type") == "file":
            files.append((node.get("link"), prefix + node.get("name", "file")))
            return
        for c in (node.get("children") or {}).values():
            if c.get("type") == "folder":
                walk(c["id"], prefix + c["name"] + "/")
            else:
                files.append((c.get("link"), prefix + c.get("name", "file")))

    walk(content_id)
    if not files:
        sys.exit("no downloadable files")

    print(f"found {len(files)} file(s)")
    for link, name in files:
        if not link:
            print(f"skip {name}: no link")
            continue
        print(f"downloading {name}")
        rc = subprocess.run([
            "aria2c", "-x16", "-s16", "-k1M", "--file-allocation=none",
            "--max-tries=10", "--retry-wait=5", "--summary-interval=30",
            "-d", outdir, "-o", name,
            f"--header=Cookie: accountToken={token}",
            f"--header=Referer: https://gofile.io/",
            f"--user-agent={UA}",
            link
        ]).returncode
        if rc != 0:
            sys.exit(f"aria2c failed on {name} (rc={rc})")

    print("done")

if __name__ == "__main__":
    main()
