"""Release checks for the deployment bundle. Read-only. Run from the repository root: python deploy/check_release.py"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "deploy" / "ledger-bundle"
problems = []


def need(ok, msg):
    if not ok:
        problems.append(msg)


# 1. checksums over exactly the four shipped ledger files
sums = {}
for line in (B / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    if line.strip():
        h, name = line.split(None, 1)
        sums[name.strip().lstrip("*")] = h
need(set(sums) == {"ledger.sqlite", "demo-reference.json", "demo-reference.json.registry-binding.json", "manifest.json"}, f"unexpected checksum set {sorted(sums)}")
for name, h in sums.items():
    need(hashlib.sha256((B / name).read_bytes()).hexdigest() == h, f"checksum mismatch {name}")
need(sorted(p.name for p in B.iterdir()) == sorted(list(sums) + ["SHA256SUMS", "IDENTITY.json"]), "unexpected files in bundle")

# 2. identity record
ident = json.loads((B / "IDENTITY.json").read_text(encoding="utf-8"))
need(ident["archiveId"] == "8322f95011cc4e6d83c7d9e17cd6c01a" and ident["sequence"] == 10 and ident["events"] == 47 and ident["motors"] == 9, "identity record differs from approved reference")

# 3. no credentials, e-mail, local paths or non-example URLs in the bundle text files
pat = re.compile(r"(?i)(C:\\\\|C:/Users|/Users/|/home/|@[a-z0-9-]+\.[a-z]{2,}|api[_-]?key|secret|password|bearer |BEGIN [A-Z ]*PRIVATE|AIza|127\.0\.0\.1|localhost)")
for name in ["demo-reference.json", "demo-reference.json.registry-binding.json", "manifest.json", "IDENTITY.json"]:
    for m in pat.finditer((B / name).read_text(encoding="utf-8")):
        problems.append(f"{name}: sensitive-looking text {m.group(0)!r}")
need(b"C:\\" not in (B / "ledger.sqlite").read_bytes() and b"C:/Users" not in (B / "ledger.sqlite").read_bytes(), "local path inside ledger.sqlite")

# 4. proxy allowlist is GET-only and exposes no session, notifications or recovery route
route = (ROOT / "stitch-nextjs" / "src" / "app" / "api" / "[...path]" / "route.ts").read_text(encoding="utf-8")
need("session" not in route and "notifications" not in route and "recovery" not in route, "proxy references session/notifications/recovery")
need(re.findall(r"export (?:async )?function (\w+)", route) == ["GET"], "proxy exports a non-GET handler")

# 5. bundle is private (not under Next public assets) and no model-provider or key references in frontend source/env
need(not (ROOT / "stitch-nextjs" / "public" / "ledger-bundle").exists(), "bundle under public")
for p in (ROOT / "stitch-nextjs" / "src").rglob("*"):
    if p.suffix in {".ts", ".tsx"}:
        t = p.read_text(encoding="utf-8", errors="ignore")
        need(not re.search(r"GEMINI|generativelanguage|NEXT_PUBLIC_\w*(KEY|TOKEN|SECRET)", t), f"model/key reference in {p.relative_to(ROOT)}")
need(not any(ROOT.glob("**/.env*")) or all("node_modules" in str(p) for p in ROOT.glob("**/.env*")), "an .env file is present")

if problems:
    print("RELEASE CHECK FAILED"); [print(" -", p) for p in problems]; sys.exit(1)
print("release check ok: bundle checksums, identity, no sensitive text, GET-only proxy without session, bundle not public, no model/key references")
