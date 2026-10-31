"""Krok 4: budowa dwóch warunków polskich z zamrożonych odpowiedzi.

Uruchom PO `python merge_review.py` (gdy prompts_en.csv ma ostateczne prompt_pl):
    python build_pl_conditions.py            (podgląd, nic nie zapisuje)
    python build_pl_conditions.py --apply

Co robi:
1. Dopisuje do data/prompts_en.csv kolumnę prompt_pl_mt = surowy szkic MT
   (z data/prompts_pl_draft.csv). Uwaga: 3 prompty (103, 165, 428) nie mają prawdziwej
   wersji MT (MT się poprawiało / odmówiło) — dla nich pl_mt = wersja ręczna; flagujemy je.
2. Z zamrożonych odpowiedzi (frozen/pl_2026-10-21, tylko do odczytu) przepisuje każdą
   odpowiedź do warunku, którego tekst promptu dokładnie się zgadza:
     outputs/<model>__pl.jsonl     ← prompt == prompt_pl (zweryfikowany)
     outputs/<model>__pl_mt.jsonl  ← prompt == prompt_pl_mt (MT)
   Gdy oba teksty są identyczne, ta sama odpowiedź trafia do obu plików.
3. Pokazuje, ile odpowiedzi brakuje w każdym warunku. Brakujące dogeneruje generate.py
   z tymi samymi ziarnami (ziarno jest ustawiane przed każdą odpowiedzią osobno).
Pliki w frozen/ nie są modyfikowane.
"""
import argparse
import glob
import json
import os

import pandas as pd

FROZEN = "frozen/pl_2026-10-21"
SEEDS = ["0", "1", "2", "3", "4", "greedy"]
NO_TRUE_MT = {103, 165, 428}

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

en = pd.read_csv("data/prompts_en.csv")
draft = (pd.read_csv("data/prompts_pl_draft.csv")
         .query("status == 'ok'").drop_duplicates("id", keep="last")
         .set_index("id")["prompt_pl_draft"].astype(str).str.strip())
assert en["prompt_pl"].notna().all(), "prompt_pl niepełne — najpierw python merge_review.py"
assert len(draft) == 200, f"szkic MT: {len(draft)} wierszy zamiast 200"

en["prompt_pl_mt"] = en["id"].map(draft)
en["no_true_mt"] = en["id"].isin(NO_TRUE_MT)
final = en.set_index("id")["prompt_pl"].astype(str).str.strip()
mt = en.set_index("id")["prompt_pl_mt"].astype(str).str.strip()
changed = sorted(i for i in final.index if final[i] != mt[i])
print(f"Prompty, w których wersja zweryfikowana ≠ MT: {len(changed)}")
print(f"  {changed}\n")

for p in sorted(glob.glob(f"{FROZEN}/*__pl.jsonl")):
    stem = os.path.basename(p).removesuffix("__pl.jsonl")
    rs = [json.loads(l) for l in open(p, encoding="utf-8")]
    to_pl, to_mt, orphan = [], [], 0
    for r in rs:
        txt = r["prompt"].strip()
        hit = False
        if txt == final[r["id"]]:
            to_pl.append(dict(r, lang="pl")); hit = True
        if txt == mt[r["id"]]:
            to_mt.append(dict(r, lang="pl_mt")); hit = True
        if not hit:
            orphan += 1
    need = len(en) * len(SEEDS)
    print(f"{stem:42} pl: {len(to_pl):4}/{need} (brak {need - len(to_pl):4})   "
          f"pl_mt: {len(to_mt):4}/{need} (brak {need - len(to_mt):4})   "
          f"nie pasuje do żadnego: {orphan}")
    if args.apply:
        for lang, recs in [("pl", to_pl), ("pl_mt", to_mt)]:
            with open(f"outputs/{stem}__{lang}.jsonl", "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

if args.apply:
    en.to_csv("data/prompts_en.csv", index=False)
    print("\nZapisano outputs/*__pl.jsonl, outputs/*__pl_mt.jsonl i kolumnę prompt_pl_mt.")
    print("Teraz dogeneruj brakujące odpowiedzi (generate.py, --lang pl i --lang pl_mt).")
else:
    print("\nTo był podgląd. Uruchom z --apply.")
