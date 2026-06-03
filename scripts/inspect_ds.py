import json
from collections import Counter

ds = json.load(open("data/sambel_pecel_150.json", encoding="utf-8"))
print("Total:", len(ds))
print()
print("=== USIA (age) ===")
for k, v in Counter(p["biodata"]["usia"] for p in ds).most_common():
    print(f"  {k:15s}: {v}")
print()
print("=== SAMPLE NAMES (first 15) ===")
for p in ds[:15]:
    print(f"  {p['biodata']['nama']:35s} | {p['biodata']['usia']:12s} | {p['biodata']['jenis_kelamin']}")
print()
print("=== DIGITAL COHERENCE (pakai_digital=Tidak -> kd_* should be low) ===")
tidak = [p for p in ds if p["biodata"]["pakai_digital"] == "Tidak"][:6]
for p in tidak:
    avg = sum(p["answers"][k] for k in ["kd_1", "kd_2", "kd_3", "kd_4"]) / 4
    print(f"  kd_avg={avg:.1f} | {p['biodata']['nama']}")
print()
print("=== LIKERT VALUE SPREAD (all scale answers) ===")
allv = [v for p in ds for v in p["answers"].values()]
for k, v in sorted(Counter(allv).items()):
    print(f"  skor {k}: {v} ({100*v/len(allv):.1f}%)")
