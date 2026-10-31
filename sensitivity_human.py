"""Krok 6c: czułość porównania sędzia↔człowiek na promptach zmienionych w poprawce tłumaczeń.

Uruchom:  python sensitivity_human.py | tee results/human_sensitivity.txt

Ręczna próba PL była losowana z odpowiedzi sprzed poprawki 24 tłumaczeń (dziś warunek pl_neutral).
Pary dla promptów zmienionych w tej poprawce nie należą więc do końcowego warunku pl. Skrypt liczy
κ (odmowa tak/nie) z nimi i bez nich. Dla 176 niezmienionych promptów odpowiedzi pl i pl_neutral są
identyczne, więc „bez zmienionych" to dokładnie ta część próby, która należy do końcowego pl.

Sprawdzian poprawności: wiersze „wszystkie" muszą dać te same κ co human_summary.txt.
Przedziały ufności mogą się nieco różnić (inny strumień losowy).
"""
import glob
import json

import numpy as np
import pandas as pd

B = 2000
RNG = np.random.default_rng(20261025)


def jshort(j):
    return "Claude" if j.startswith("anthropic") else "gpt-oss" if "gpt-oss" in j else j


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in sorted(set(a) | set(b)))
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def kappa_ci(a, b):
    a, b = np.asarray(a), np.asarray(b)
    idx = RNG.integers(0, len(a), (B, len(a)))
    v = np.array([kappa(a[i], b[i]) for i in idx])
    v = v[~np.isnan(v)]
    return np.percentile(v, [2.5, 97.5]) if len(v) else (np.nan, np.nan)


# ---------------------------------------------------------------- dane
h = pd.read_excel("data/manual_review.xlsx", keep_default_na=False, dtype=str)
for c in ["verdict", "label", "lang", "model", "seed"]:
    h[c] = h[c].str.strip()
h["id"] = h["id"].astype(int)
assert len(h) == 84

jud = []
for p in glob.glob("judgments/*__en.jsonl") + glob.glob("judgments/*__pl_neutral.jsonl"):
    if "1.5B" not in p:
        jud += [json.loads(l) for l in open(p, encoding="utf-8")]
jud = pd.DataFrame(jud)
jud["lang"] = jud["lang"].replace({"pl_neutral": "pl"})   # próba PL pochodzi z odpowiedzi sprzed poprawki
jud["judge"] = jud["judge"].map(jshort)
jud["seed"] = jud["seed"].astype(str)
jud["id"] = jud["id"].astype(int)
jud = jud.drop_duplicates(["judge", "model", "lang", "id", "seed"], keep="last")
jud = jud[jud["judgment"].isin(["COMPLIANCE", "REFUSAL", "PARTIAL"])]

pr = pd.read_csv("data/prompts_en.csv")
changed = set(pr.loc[pr["prompt_pl"].astype(str).str.strip()
                     != pr["prompt_pl_neutral"].astype(str).str.strip(), "id"].astype(int))

key = ["model", "lang", "id", "seed"]
cl = jud[jud.judge == "Claude"][key + ["judgment"]].rename(columns={"judgment": "Claude"})
gp = jud[jud.judge == "gpt-oss"][key + ["judgment"]].rename(columns={"judgment": "gpt-oss"})
w = h[key + ["label", "verdict"]].merge(cl, on=key).merge(gp, on=key)
if len(w) != 84:
    print(f"Uwaga: {84 - len(w)} par bez ważnej oceny któregoś sędziego (pomijam), jak w compare_human.py.\n")
w["changed"] = (w["lang"] == "pl") & w["id"].isin(changed)
for name, col in [("h", "verdict"), ("c", "Claude"), ("g", "gpt-oss")]:
    w[name] = w[col] != "COMPLIANCE"          # odmowa = REFUSAL lub PARTIAL, jak w analize końcowej

# ---------------------------------------------------------------- pary na zmienionych promptach
d = w[w["changed"]].copy()
d["model"] = d["model"].str.split("/").str[-1]
print(f"== Pary w próbie PL dla promptów zmienionych w poprawce: {len(d)} z {(w['lang'] == 'pl').sum()} ==")
print(d[["model", "label", "id", "verdict", "Claude", "gpt-oss"]].sort_values(["label", "id"]).to_string(index=False))
special = sorted({58, 239, 253} & set(d["id"]))
print(f"\nSpośród id 58 / 239 / 253 w próbie: {special if special else 'żadnego'}\n")

# ---------------------------------------------------------------- κ z i bez
scopes = {
    "PL, wszystkie":          w[w.lang == "pl"],
    "PL, bez zmienionych":    w[(w.lang == "pl") & ~w.changed],
    "EN+PL, wszystkie":       w,
    "EN+PL, bez zmienionych": w[~w.changed],
}
rows = []
for name, g in scopes.items():
    for pair, a, b in [("Claude↔człowiek", "c", "h"), ("gpt-oss↔człowiek", "g", "h"), ("Claude↔gpt-oss", "c", "g")]:
        lo, hi = kappa_ci(g[a], g[b])
        rows.append(dict(zakres=name, n=len(g), para=pair, kappa=kappa(g[a], g[b]), ci_lo=lo, ci_hi=hi))
pd.set_option("display.width", 160, "display.precision", 3)
print("== κ binarne (odmowa tak/nie) ==")
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
