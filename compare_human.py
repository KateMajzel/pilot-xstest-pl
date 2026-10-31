"""Krok 6b: Twoje 84 ręczne oceny vs sędziowie LLM.

Uruchom:  python compare_human.py
Wynik:    results/human_vs_judges.csv, results/human_confusion.csv, results/behaviour_axis.csv

Porównanie na tych samych odpowiedziach (model, język, prompt, ziarno). Język „pl” = wersja
zweryfikowana (z niej losowano próbę). Odmowa binarnie = REFUSAL lub PARTIAL (jak w analyze.py).
Przy n = 42 na język przedziały ufności są szerokie — to kotwica, nie precyzyjny pomiar.
"""
import glob
import json
import os

import numpy as np
import pandas as pd

B = 2000
RNG = np.random.default_rng(20261025)
os.makedirs("results", exist_ok=True)


def jshort(j):
    return "Claude" if j.startswith("anthropic") else "gpt-oss" if "gpt-oss" in j else j


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    cats = sorted(set(a) | set(b))
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def boot(fn, a, b):
    a, b = np.asarray(a), np.asarray(b)
    idx = RNG.integers(0, len(a), (B, len(a)))
    vals = np.array([fn(a[i], b[i]) for i in idx])
    vals = vals[~np.isnan(vals)]
    return np.percentile(vals, [2.5, 97.5]) if len(vals) else (np.nan, np.nan)


# ------------------------------------------------------------------ dane
h = pd.read_excel("data/manual_review.xlsx", keep_default_na=False, dtype=str)
for c in ["verdict", "behaviour", "label", "lang", "model", "seed"]:
    h[c] = h[c].str.strip()
h["id"] = h["id"].astype(int)
assert len(h) == 84 and h["verdict"].isin(["COMPLIANCE", "REFUSAL", "PARTIAL"]).all()

jud = []
for p in glob.glob("judgments/*__en.jsonl") + glob.glob("judgments/*__pl.jsonl"):
    if "1.5B" in p:
        continue
    jud += [json.loads(l) for l in open(p, encoding="utf-8")]
# ręczna ocena PL była robiona na odpowiedziach sprzed poprawki 24 tłumaczeń → warunek pl_neutral
for p in glob.glob("judgments/*__pl_neutral.jsonl"):
    jud += [dict(json.loads(l), lang="pl_from_neutral") for l in open(p, encoding="utf-8")]
jud = pd.DataFrame(jud)
if (jud["lang"] == "pl_from_neutral").any():
    jud = jud[jud["lang"] != "pl"]
    jud.loc[jud["lang"] == "pl_from_neutral", "lang"] = "pl"
jud = jud.drop_duplicates(["judge", "model", "lang", "id", "seed"], keep="last")
jud["judge"] = jud["judge"].map(jshort)
jud["seed"] = jud["seed"].astype(str)

m = h.merge(jud[["judge", "model", "lang", "id", "seed", "judgment"]],
            on=["model", "lang", "id", "seed"], how="left")
missing = m["judgment"].isna().sum()
if missing:
    print(f"Uwaga: {missing} par bez oceny sędziego (pomijam).")
m = m[m["judgment"].isin(["COMPLIANCE", "REFUSAL", "PARTIAL"])]
m["h_ref"] = m["verdict"] != "COMPLIANCE"
m["j_ref"] = m["judgment"] != "COMPLIANCE"

# ------------------------------------------------------------------ zgodność
rows = []
for (judge, lang), g in m.groupby(["judge", "lang"]):
    a3, b3 = g["verdict"].values, g["judgment"].values
    a2, b2 = g["h_ref"].values, g["j_ref"].values
    agree = lambda x, y: (x == y).mean()
    lo3, hi3 = boot(agree, a3, b3)
    klo, khi = boot(kappa, a2, b2)
    rows.append(dict(judge=judge, lang=lang, n=len(g),
                     agreement_3class=agree(a3, b3), agr_ci_lo=lo3, agr_ci_hi=hi3,
                     kappa_3class=kappa(a3, b3),
                     kappa_binary=kappa(a2, b2), kappa_bin_ci_lo=klo, kappa_bin_ci_hi=khi,
                     human_refusal=a2.mean(), judge_refusal=b2.mean(),
                     judge_minus_human=b2.mean() - a2.mean()))
for judge, g in m.groupby("judge"):   # łącznie EN + PL (n = 84)
    a2, b2 = g["h_ref"].values, g["j_ref"].values
    klo, khi = boot(kappa, a2, b2)
    rows.append(dict(judge=judge, lang="en+pl", n=len(g),
                     agreement_3class=(g["verdict"].values == g["judgment"].values).mean(),
                     kappa_3class=kappa(g["verdict"].values, g["judgment"].values),
                     kappa_binary=kappa(a2, b2), kappa_bin_ci_lo=klo, kappa_bin_ci_hi=khi,
                     human_refusal=a2.mean(), judge_refusal=b2.mean(),
                     judge_minus_human=b2.mean() - a2.mean()))
# zgodność sędzia–sędzia na tych samych 84 odpowiedziach (porównanie z zgodnością z człowiekiem)
w = m.pivot_table(index=["model", "lang", "id", "seed"], columns="judge", values="j_ref", aggfunc="first").dropna()
for lang, g in list(w.groupby(level="lang")) + [("en+pl", w)]:
    klo, khi = boot(kappa, g["Claude"].values, g["gpt-oss"].values)
    rows.append(dict(judge="Claude↔gpt-oss", lang=lang, n=len(g),
                     kappa_binary=kappa(g["Claude"].values, g["gpt-oss"].values),
                     kappa_bin_ci_lo=klo, kappa_bin_ci_hi=khi))
res = pd.DataFrame(rows)
res.to_csv("results/human_vs_judges.csv", index=False)

conf = (m.groupby(["judge", "lang", "verdict", "judgment"]).size()
        .rename("n").reset_index())
conf.to_csv("results/human_confusion.csv", index=False)

# ------------------------------------------------------------------ oś 2 (opisowo)
beh = (h.groupby(["lang", "label", "behaviour"]).size().rename("n").reset_index())
beh.to_csv("results/behaviour_axis.csv", index=False)

pd.set_option("display.width", 160, "display.max_columns", 20, "display.precision", 3)
print("== Zgodność sędziów z oceną ręczną (n na język ≈ 42) ==")
print(res.to_string(index=False), "\n")
for (judge, lang), g in m.groupby(["judge", "lang"]):
    print(f"-- {judge}, {lang}: wiersze = Ty, kolumny = sędzia")
    print(pd.crosstab(g["verdict"], g["judgment"]), "\n")
print("== Oś 2 (Twoja ocena) ==")
print(h.groupby(["label", "behaviour", "lang"]).size().unstack(fill_value=0))
print("\nTabele → results/")
