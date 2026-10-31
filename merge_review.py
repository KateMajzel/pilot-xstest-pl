"""Krok 2c: przeniesienie przejrzanych tłumaczeń do data/prompts_en.csv.

Uruchom:  python merge_review.py            (tylko gdy wszystkie 200 wierszy są przejrzane)
          python merge_review.py --check    (sam podgląd postępu, nic nie zapisuje)

Sprawdza, że każdy wiersz ma tłumaczenie i poprawną kategorię translation_effect.
Zapisuje w prompts_en.csv kolumny: prompt_pl, translation_effect, cultural_change.
"""
import argparse

import pandas as pd

EFFECTS = {"preserved", "trigger_weakened", "trigger_strengthened", "meaning_shifted"}

ap = argparse.ArgumentParser()
ap.add_argument("--check", action="store_true")
args = ap.parse_args()

rv = pd.read_excel("data/review_pl.xlsx").fillna("")
rv["translation_effect"] = rv["translation_effect"].astype(str).str.strip()
rv["prompt_pl_final"] = rv["prompt_pl_final"].astype(str).str.strip()

missing_pl = rv[rv["prompt_pl_final"] == ""]
bad_eff = rv[~rv["translation_effect"].isin(EFFECTS)]
done = len(rv) - len(bad_eff)
print(f"Przejrzane: {done}/{len(rv)}")
print("Według priorytetu:")
print(rv.assign(ok=rv["translation_effect"].isin(EFFECTS))
        .groupby("priority")["ok"].agg(["sum", "count"]).rename(columns={"sum": "gotowe", "count": "razem"}))

if done:
    print("\nKategorie (dotychczas):")
    print(pd.crosstab(rv.loc[rv["translation_effect"].isin(EFFECTS), "translation_effect"],
                      rv.loc[rv["translation_effect"].isin(EFFECTS), "label"], margins=True))

changed = rv[(rv["prompt_pl_final"] != rv["prompt_pl_draft"].astype(str).str.strip())
             & (rv["prompt_pl_final"] != "")]
print(f"\nTłumaczeń poprawionych względem szkicu MT: {len(changed)}")

if args.check:
    raise SystemExit(0)
if len(missing_pl) or len(bad_eff):
    print(f"\nNie zapisuję: brak tłumaczenia w {len(missing_pl)} wierszach, "
          f"brak/zła kategoria w {len(bad_eff)}. Pierwsze id do uzupełnienia: "
          f"{bad_eff['id'].head(10).tolist()}")
    raise SystemExit(1)

en = pd.read_csv("data/prompts_en.csv")
rv = rv.set_index("id")
en["prompt_pl"] = en["id"].map(rv["prompt_pl_final"])
en["translation_effect"] = en["id"].map(rv["translation_effect"])
en["cultural_change"] = en["id"].map(
    lambda i: rv.at[i, "notes"] or rv.at[i, "cultural_change_draft"])
en["edited_vs_mt"] = en["id"].isin(changed["id"])
en.to_csv("data/prompts_en.csv", index=False)
print("Zapisano → data/prompts_en.csv")
