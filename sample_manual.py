"""Krok 6: losowanie 84 odpowiedzi do ręcznej oceny (kodeks: CODEBOOK.md).

Uruchom:  python sample_manual.py
Wynik:    data/manual_review.xlsx  — arkusz do wypełnienia (bez ocen sędziów!)
          data/manual_sample.csv   — lista wylosowanych (model, lang, id, seed), do commita

Rozwarstwienie: safe/unsafe × en/pl × 3 modele = 12 komórek po 7 odpowiedzi.
W komórce 7 różnych promptów, dla każdego losowe ziarno z 0–4. Wiersze w losowej kolejności.
"""
import glob
import json
import os

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

SEED = 20261024
PER_CELL = 7
LANGS = ["en", "pl"]          # pl = wersja zweryfikowana
SAMPLED = ["0", "1", "2", "3", "4"]
rng = np.random.default_rng(SEED)

if os.path.exists("data/manual_review.xlsx"):
    raise SystemExit("data/manual_review.xlsx już istnieje — nie nadpisuję (to byłoby ponowne losowanie).")

rows = []
for p in sorted(glob.glob("outputs/*.jsonl")):
    if "1.5B" in p:
        continue
    for l in open(p, encoding="utf-8"):
        r = json.loads(l)
        if r["lang"] in LANGS and r["seed"] in SAMPLED:
            rows.append(r)
df = pd.DataFrame(rows)

picked = []
for (model, lang, label), g in df.groupby(["model", "lang", "label"]):
    ids = sorted(g["id"].unique())
    chosen = rng.choice(ids, size=PER_CELL, replace=False)
    for i in sorted(chosen):
        seed = rng.choice(SAMPLED)
        rec = g[(g["id"] == i) & (g["seed"] == seed)].iloc[0]
        picked.append(rec)
sample = pd.DataFrame(picked)
assert len(sample) == 12 * PER_CELL, len(sample)
sample = sample.sample(frac=1, random_state=SEED).reset_index(drop=True)
sample.insert(0, "row", range(1, len(sample) + 1))

sample[["row", "model", "lang", "label", "type", "id", "seed"]].to_csv("data/manual_sample.csv", index=False)

cols = ["row", "model", "lang", "label", "type", "id", "seed", "prompt", "response", "truncated",
        "verdict", "behaviour", "notes"]
sample["verdict"] = ""
sample["behaviour"] = ""
sample["notes"] = ""
wb = Workbook()
ws = wb.active
ws.title = "ocena"
ws.append(cols)
for _, r in sample[cols].iterrows():
    ws.append([str(v) if k in ("seed",) else v for k, v in r.items()])

widths = {"A": 6, "B": 34, "C": 6, "D": 8, "E": 20, "F": 6, "G": 6, "H": 45, "I": 90, "J": 9,
          "K": 14, "L": 20, "M": 30}
for c, w in widths.items():
    ws.column_dimensions[c].width = w
for cell in ws[1]:
    cell.font = Font(bold=True)
for row in ws.iter_rows(min_row=2):
    for cell in row:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for k in (10, 11, 12):
        row[k].fill = PatternFill("solid", fgColor="FFF4CC")
ws.freeze_panes = "H2"

n = ws.max_row
dv1 = DataValidation(type="list", formula1='"COMPLIANCE,REFUSAL,PARTIAL"', allow_blank=True)
dv2 = DataValidation(type="list",
                     formula1='"clean,unrequested_caveat,clean_refusal,leaky_refusal,n/a"', allow_blank=True)
ws.add_data_validation(dv1)
ws.add_data_validation(dv2)
dv1.add(f"K2:K{n}")
dv2.add(f"L2:L{n}")

wb.save("data/manual_review.xlsx")
print(sample.groupby(["model", "lang", "label"]).size().unstack())
print(f"\nWylosowano {len(sample)} odpowiedzi → data/manual_review.xlsx")
