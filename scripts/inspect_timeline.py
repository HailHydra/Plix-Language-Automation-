import json
from pathlib import Path
import sys
sys.path.insert(0, ".")
from src.common import read_json

def main():
    m = read_json(r"output\dub_WhatsApp Video 2026-09-28 at 6.01.20 PM_en\dub_manifest.json")
    print("=== SCENE CUTS IN VIDEO ===")
    for s in m["scenes"]:
        print(f"Cut #{s['index']:02d}: {s['start']:6.3f}s -> {s['end']:6.3f}s ({s['duration']:5.3f}s)")

    print("\n=== TIMELINE SEGMENTS ===")
    for t in m["timeline"]:
        act = t.get("action", "")
        cls = t.get("classification", "")
        reason = t.get("reason", "")
        print(f"Seg #{t['index']:02d}: {t['start']:6.3f}s -> {t['end']:6.3f}s ({t['duration']:5.3f}s) | Act: {act:12s} | Class: {cls:10s} | {reason}")

if __name__ == "__main__":
    main()
