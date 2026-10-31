"""Krok 4b: po poprawce 24 tłumaczeń — przebudowa warunków pl i pl_neutral.

Uruchom PO: zamrożeniu (frozen/pl_neutral_2026-10-25), poprawkach w review_pl.xlsx
i `python merge_review.py`.
    python rebuild_pl.py            (podgląd)
    python rebuild_pl.py --apply

Warunki po przebudowie:
  pl_mt       surowe MT (bez zmian)
  pl          tłumaczenie zweryfikowane według wersji A (zachowuje wyzwalacz) — NOWE prompt_pl
  pl_neutral  poprzednia „zweryfikowana” wersja (część wyzwalaczy usunięta) — zachowana jako
              przypadkowa ablacja wyzwalacza; odpowiedzi i oceny przenoszone 1:1 z zamrożenia
Dla nowego pl odpowiedzi i oceny sędziów są kopiowane z pl_mt albo pl_neutral, gdy tekst promptu
jest identyczny (ten sam model, prompt, ziarno → ta sama odpowiedź). Brakujące dogeneruje
generate.py, a ocenią je judge.py (pomijają to, co już jest w plikach).
"""
import argparse
import glob
import json
import os

import pandas as pd

FROZEN = "frozen/pl_neutral_2026-10-25"
SEEDS = ["0", "1", "2", "3", "4", "greedy"]

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def write(p, recs):
    with open(p, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


en = pd.read_csv("data/prompts_en.csv")
old = pd.read_csv(f"{FROZEN}/prompts_en.csv").set_index("id")["prompt_pl"].astype(str).str.strip()
en["prompt_pl_neutral"] = en["id"].map(old)
new = en.set_index("id")["prompt_pl"].astype(str).str.strip()
mt = en.set_index("id")["prompt_pl_mt"].astype(str).str.strip()

changed = sorted(i for i in new.index if new[i] != old[i])
print(f"Prompty zmienione względem poprzedniej wersji: {len(changed)}  {changed}")
print(f"  z tego = MT: {sum(new[i] == mt[i] for i in changed)}, "
      f"nowe sformułowanie: {[i for i in changed if new[i] != mt[i]]}\n")

for p in sorted(glob.glob(f"{FROZEN}/*__pl.jsonl")):
    name = os.path.basename(p)
    if name.count("__") > 2:          # pliki ocen: <sędzia>__<model>__pl.jsonl
        continue
    stem = name.removesuffix("__pl.jsonl")
    neutral_out = read(p)
    mt_out = read(f"outputs/{stem}__pl_mt.jsonl")
    pool = {}
    for src, recs in [("pl_mt", mt_out), ("pl_neutral", neutral_out)]:
        for r in recs:
            pool.setdefault((r["id"], r["seed"], r["prompt"].strip()), (src, r))

    new_out, src_of = [], {}
    for i in new.index:
        for s in SEEDS:
            hit = pool.get((i, s, new[i]))
            if hit:
                src, r = hit
                new_out.append(dict(r, lang="pl"))
                src_of[(i, s)] = src
    need = len(new) * len(SEEDS)
    print(f"{stem:42} nowe pl: {len(new_out):4}/{need} (do wygenerowania {need - len(new_out)})")

    if args.apply:
        write(f"outputs/{stem}__pl_neutral.jsonl", [dict(r, lang="pl_neutral") for r in neutral_out])
        write(f"outputs/{stem}__pl.jsonl", new_out)

    for jp in sorted(glob.glob(f"{FROZEN}/*__{stem}__pl.jsonl")):
        judge = os.path.basename(jp).removesuffix(f"__{stem}__pl.jsonl")
        j_neutral = read(jp)
        j_mt = read(f"judgments/{judge}__{stem}__pl_mt.jsonl")
        jidx = {("pl_neutral", r["id"], r["seed"]): r for r in j_neutral}
        jidx.update({("pl_mt", r["id"], r["seed"]): r for r in j_mt})
        new_j = [dict(jidx[(src, i, s)], lang="pl")
                 for (i, s), src in src_of.items() if (src, i, s) in jidx]
        print(f"   {judge:35} oceny nowego pl: {len(new_j):4}/{need}")
        if args.apply:
            write(f"judgments/{judge}__{stem}__pl_neutral.jsonl",
                  [dict(r, lang="pl_neutral") for r in j_neutral])
            write(f"judgments/{judge}__{stem}__pl.jsonl", new_j)

if args.apply:
    en.to_csv("data/prompts_en.csv", index=False)
    print("\nZapisano. Teraz: generate.py --lang pl (dogeneruje brakujące), potem judge.py na __pl.jsonl.")
else:
    print("\nTo był podgląd. Uruchom z --apply.")
