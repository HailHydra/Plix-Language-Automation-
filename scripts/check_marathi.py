import os, requests, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

key = os.environ.get("ELEVENLABS_API_KEY", "")
r = requests.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": key}, timeout=15)
if not r.ok:
    print("Error:", r.status_code, r.text[:300])
    sys.exit(1)

models = r.json()
print("=== Models with Marathi (mr) or Hindi (hi) support ===")
for m in models:
    langs = [l.get("language_id", "") for l in m.get("languages", [])]
    if "mr" in langs or "hi" in langs:
        mr_supported = "mr" in langs
        hi_supported = "hi" in langs
        print(f"\nModel: {m['model_id']}")
        print(f"  Name: {m.get('name','')}")
        print(f"  Marathi (mr): {mr_supported}")
        print(f"  Hindi (hi): {hi_supported}")
        if mr_supported:
            mr_lang = next(l for l in m.get("languages",[]) if l.get("language_id")=="mr")
            print(f"  Marathi entry: {mr_lang}")
