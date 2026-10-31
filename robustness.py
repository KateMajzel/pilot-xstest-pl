"""Krok 7a: dwa sprawdzenia odporności przed raportem.

Uruchom:  python robustness.py
Wynik:    results/robust_no_truncated.csv, results/robust_edited_prompts.csv

A. Różnica pl − en po wyłączeniu uciętych odpowiedzi (limit 512 tokenów).
   PL jest ucinane 2–5× częściej niż EN — jeśli wynik się utrzymuje, ucinanie go nie tłumaczy.
B. pl − pl_mt tylko na promptach, w których wersja zweryfikowana ≠ MT (24 prompty).
   Na pozostałych odpowiedzi są identyczne, więc pełna tabela rozmywa ten efekt.
"""
import glob
import json

import numpy as np
import pandas as pd

B = 2000
RNG = np.random.default_rng(20261025)
SAMPLED = ["0", "1", "2", "3", "4"]
SHORT = {"Qwen/Qwen2.5-7B-Instruct": "Qwen-7B", "meta-llama/Llama-3.1-8B-Instruct": "Llama-8B",
         "speakleash/Bielik-11B-v3.0-Instruct": "Bielik-11B"}


def boot_mean(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    bs = x[RNG.integers(0, len(x), (B, len(x)))].mean(1)
    return x.mean(), *np.percentile(bs, [2.5, 97.5])


outs = []
for p in glob.glob("outputs/*.jsonl"):
    if "1.5B" not in p:
        outs += [json.loads(l) for l in open(p, encoding="utf-8")]
outs = pd.DataFrame(outs)[["model", "lang", "id", "seed", "truncated"]]

jud = []
for p in glob.glob("judgments/*.jsonl"):
    if "1.5B" not in p:
        jud += [json.loads(l) for l in open(p, encoding="utf-8")]
jud = pd.DataFrame(jud).drop_duplicates(["judge", "model", "lang", "id", "seed"], keep="last")
jud["judge"] = jud["judge"].map(lambda j: "Claude" if j.startswith("anthropic") else "gpt-oss")
jud = jud[jud["judgment"].isin(["COMPLIANCE", "REFUSAL", "PARTIAL"]) & jud["seed"].isin(SAMPLED)]
jud["refusal"] = (jud["judgment"] != "COMPLIANCE").astype(float)
jud = jud.merge(outs, on=["model", "lang", "id", "seed"], how="left")
jud["model"] = jud["model"].map(SHORT)


def per_prompt(g):
    return g.groupby("id")["refusal"].mean()


def delta(g, a, b):
    pa, pb = per_prompt(g[g.lang == a]), per_prompt(g[g.lang == b])
    common = pa.index.intersection(pb.index)
    m, lo, hi = boot_mean((pa[common] - pb[common]).values)
    return m, lo, hi, len(common)


# A. bez uciętych
rows = []
for (judge, model, label), g in jud.groupby(["judge", "model", "label_xstest"]):
    full = delta(g, "pl", "en")
    nt = delta(g[~g["truncated"].astype(bool)], "pl", "en")
    rows.append(dict(judge=judge, model=model, label=label,
                     delta_all=full[0], ci_all=f"[{full[1]:+.3f}, {full[2]:+.3f}]",
                     delta_no_trunc=nt[0], ci_no_trunc=f"[{nt[1]:+.3f}, {nt[2]:+.3f}]",
                     prompts_no_trunc=nt[3],
                     sig_all=not (full[1] <= 0 <= full[2]), sig_no_trunc=not (nt[1] <= 0 <= nt[2])))
A = pd.DataFrame(rows)
A.to_csv("results/robust_no_truncated.csv", index=False)

# B. tylko zmienione prompty
pr = pd.read_csv("data/prompts_en.csv")
edited = set(pr.loc[pr["prompt_pl"].astype(str).str.strip() != pr["prompt_pl_mt"].astype(str).str.strip(), "id"])
rows = []
for (judge, model), g in jud[jud["id"].isin(edited)].groupby(["judge", "model"]):
    m, lo, hi, n = delta(g, "pl", "pl_mt")
    rows.append(dict(judge=judge, model=model, n_prompts=n, delta_pl_minus_plmt=m,
                     ci_lo=lo, ci_hi=hi, significant=not (lo <= 0 <= hi)))
# C. ablacja wyzwalacza: pl_neutral − pl tam, gdzie teksty się różnią (ta sama intencja, wyzwalacz usunięty)
if "prompt_pl_neutral" in pr.columns:
    abl = set(pr.loc[pr["prompt_pl"].astype(str).str.strip() != pr["prompt_pl_neutral"].astype(str).str.strip(), "id"])
    for (judge, model, label), g in jud[jud["id"].isin(abl)].groupby(["judge", "model", "label_xstest"]):
        m, lo, hi, n = delta(g, "pl_neutral", "pl")
        rows.append(dict(judge=judge, model=model, comparison=f"pl_neutral−pl ({label})", n_prompts=n,
                         delta_pl_minus_plmt=m, ci_lo=lo, ci_hi=hi, significant=not (lo <= 0 <= hi)))
Bdf = pd.DataFrame(rows)
Bdf.to_csv("results/robust_edited_prompts.csv", index=False)

pd.set_option("display.width", 160, "display.max_columns", 20, "display.precision", 3)
print("== A. pl − en: wszystkie odpowiedzi vs bez uciętych ==")
print(A.to_string(index=False), "\n")
print(f"== B. pl − pl_mt tylko na {len(edited)} zmienionych promptach (safe i unsafe razem) ==")
print(Bdf.to_string(index=False))
print(pr[pr["id"].isin(edited)].groupby("label").size().rename("zmienione prompty wg etykiety"))
