"""Krok 5: analiza pilotażu — wszystkie liczby do raportu.

Uruchom:  python analyze.py
Wynik:    results/*.csv  + podsumowanie w terminalu

Definicje
- odmowa = sędzia ocenił REFUSAL lub PARTIAL (jak w XSTest: pełna + częściowa).
  Kolumna `full_only` liczy tylko REFUSAL. UNPARSED/ERROR = brak oceny (pomijane).
- jednostką losowania w bootstrapie jest PROMPT (cluster bootstrap): losujemy prompty
  ze zwracaniem, a wszystkie ziarna danego promptu idą razem. Dzięki temu przedział ufności
  uwzględnia, że 5 odpowiedzi na ten sam prompt nie jest niezależnych.
- „ziarna” = 5 przebiegów z próbkowaniem (0–4). „greedy” = osobny, pojedynczy przebieg.
"""
import glob
import json
import os

import numpy as np
import pandas as pd

B = 2000
RNG = np.random.default_rng(20261018)
SAMPLED = ["0", "1", "2", "3", "4"]
os.makedirs("results", exist_ok=True)


def short(m):
    return {"Qwen/Qwen2.5-7B-Instruct": "Qwen-7B", "meta-llama/Llama-3.1-8B-Instruct": "Llama-8B",
            "speakleash/Bielik-11B-v3.0-Instruct": "Bielik-11B"}.get(m, m)


def jshort(j):
    return "Claude" if j.startswith("anthropic") else "gpt-oss" if "gpt-oss" in j else j


# ---------------------------------------------------------------- dane
outs = []
for p in glob.glob("outputs/*.jsonl"):
    if "1.5B" in p:
        continue
    outs += [json.loads(l) for l in open(p, encoding="utf-8")]
outs = pd.DataFrame(outs)[["model", "lang", "id", "seed", "truncated", "prompt_tokens", "response_tokens"]]

jud = []
for p in glob.glob("judgments/*.jsonl"):
    if "1.5B" in p:
        continue
    jud += [json.loads(l) for l in open(p, encoding="utf-8")]
jud = pd.DataFrame(jud)
jud = jud.drop_duplicates(["judge", "model", "lang", "id", "seed"], keep="last")
jud["model"] = jud["model"].map(short)
jud["judge"] = jud["judge"].map(jshort)
jud["valid"] = jud["judgment"].isin(["COMPLIANCE", "REFUSAL", "PARTIAL"])
jud["refusal"] = jud["judgment"].isin(["REFUSAL", "PARTIAL"]).astype(float)
jud["full"] = (jud["judgment"] == "REFUSAL").astype(float)
outs["model"] = outs["model"].map(short)

prompts = pd.read_csv("data/prompts_en.csv")
effect = prompts.set_index("id").get("translation_effect")

print(f"Odpowiedzi: {len(outs)}   Oceny: {len(jud)}   (nieważne: {(~jud.valid).sum()})")
print(jud.groupby(["judge", "lang"]).size().unstack(), "\n")


# ---------------------------------------------------------------- bootstrap
def per_prompt(df, col="refusal"):
    """Średnia po ziarnach dla każdego promptu (tylko ważne oceny)."""
    return df[df.valid].groupby("id")[col].mean()


def boot_mean(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    idx = RNG.integers(0, len(x), (B, len(x)))
    bs = x[idx].mean(1)
    return x.mean(), *np.percentile(bs, [2.5, 97.5])


def boot_delta(a, b):
    """Różnica sparowana po promptach: a − b (te same prompty w obu językach)."""
    common = a.index.intersection(b.index)
    return boot_mean((a[common] - b[common]).values) + (len(common),)


# ---------------------------------------------------------------- 1. wskaźniki odmów
rows = []
for (judge, model, lang, label), g in jud[jud.seed.isin(SAMPLED)].groupby(
        ["judge", "model", "lang", "label_xstest"]):
    m, lo, hi = boot_mean(per_prompt(g))
    rows.append(dict(judge=judge, model=model, lang=lang, label=label,
                     refusal=m, ci_lo=lo, ci_hi=hi, full_only=per_prompt(g, "full").mean(),
                     n_prompts=g.id.nunique()))
rates = pd.DataFrame(rows)
rates.to_csv("results/refusal_rates.csv", index=False)

# ---------------------------------------------------------------- 2. różnica PL − EN
# trzy porównania sparowane po promptach:
#   pl − en      główna „luka językowa” (tłumaczenie zweryfikowane)
#   pl_mt − en   to, co zmierzyłby ktoś z samym MT (jak w pracach bez weryfikacji ludzkiej)
#   pl − pl_mt   artefakt tłumaczenia przy wyzerowanym efekcie języka
PAIRS = [("pl", "en"), ("pl_mt", "en"), ("pl", "pl_mt"), ("pl_neutral", "pl")]
# pl_neutral − pl: ablacja wyzwalacza (ta sama intencja, wyzwalacz usunięty) — tylko tam, gdzie teksty się różnią,
# patrz robustness.py; w pełnej tabeli rozmyte przez identyczne prompty
rows = []
for (judge, model, label), g in jud.groupby(["judge", "model", "label_xstest"]):
    s, gr = g[g.seed.isin(SAMPLED)], g[g.seed == "greedy"]
    for a, b in PAIRS:
        if not ((s.lang == a).any() and (s.lang == b).any()):
            continue
        d, lo, hi, n = boot_delta(per_prompt(s[s.lang == a]), per_prompt(s[s.lang == b]))
        d_greedy = per_prompt(gr[gr.lang == a]).mean() - per_prompt(gr[gr.lang == b]).mean()
        rows.append(dict(comparison=f"{a}−{b}", judge=judge, model=model, label=label,
                         delta=d, ci_lo=lo, ci_hi=hi, significant=not (lo <= 0 <= hi),
                         delta_greedy=d_greedy, greedy_outside_ci=not (lo <= d_greedy <= hi),
                         n_prompts=n))
delta = pd.DataFrame(rows)
delta.to_csv("results/deltas.csv", index=False)

# ---------------------------------------------------------------- 3. szum ziaren
rows = []
for (judge, model, lang, label), g in jud[jud.valid & jud.seed.isin(SAMPLED)].groupby(
        ["judge", "model", "lang", "label_xstest"]):
    per_seed = g.groupby("seed")["refusal"].mean()
    per_prompt_seed = g.pivot_table(index="id", columns="seed", values="refusal")
    unstable = ((per_prompt_seed.min(axis=1) == 0) & (per_prompt_seed.max(axis=1) == 1)).mean()
    rows.append(dict(judge=judge, model=model, lang=lang, label=label,
                     seed_min=per_seed.min(), seed_max=per_seed.max(),
                     seed_range=per_seed.max() - per_seed.min(),
                     unstable_prompts=unstable))
noise = pd.DataFrame(rows)
noise.to_csv("results/seed_noise.csv", index=False)


# ---------------------------------------------------------------- 4. zgodność sędziów
def cohen_kappa(a, b):
    cats = sorted(set(a) | set(b))
    a, b = np.asarray(a), np.asarray(b)
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def kripp_alpha_nominal(a, b):
    """Krippendorff α dla 2 oceniających, dane nominalne, bez braków."""
    vals = np.concatenate([a, b])
    cats = sorted(set(vals))
    n = len(vals)
    do = (np.asarray(a) != np.asarray(b)).mean()
    counts = np.array([(vals == c).sum() for c in cats])
    de = (n * n - (counts ** 2).sum()) / (n * (n - 1))
    return 1 - do / de if de > 0 else np.nan


wide = jud[jud.valid].pivot_table(index=["model", "lang", "id", "seed"], columns="judge",
                                  values="judgment", aggfunc="first").dropna()
rows = []
for (lang,), g in wide.groupby(level=["lang"]):
    a, b = g["Claude"].values, g["gpt-oss"].values
    rows.append(dict(lang=lang, n=len(g), raw_agreement=(a == b).mean(),
                     kappa_3class=cohen_kappa(a, b), alpha_3class=kripp_alpha_nominal(a, b),
                     kappa_binary=cohen_kappa(a != "COMPLIANCE", b != "COMPLIANCE")))
agree = pd.DataFrame(rows)
agree.to_csv("results/judge_agreement.csv", index=False)

# ---------------------------------------------------------------- 5. wpływ tłumaczenia
def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, c - h, c + h


# 5a. jaki odsetek tłumaczeń zachował wyzwalacz (wszystkie 200, z przedziałem Wilsona)
pres_rows = []
if effect is not None and effect.notna().any():
    for label, g in prompts.groupby("label"):
        k, n = (g["translation_effect"] == "preserved").sum(), len(g)
        p, lo, hi = wilson(k, n)
        pres_rows.append(dict(label=label, preserved=k, n=n, share=p, ci_lo=lo, ci_hi=hi))
pres = pd.DataFrame(pres_rows)
pres.to_csv("results/translation_preserved.csv", index=False)

# 5b. różnice wg kategorii tłumaczenia, dla wszystkich trzech porównań
rows = []
if effect is not None and effect.notna().any():
    for (judge, model, label), g in jud[jud.seed.isin(SAMPLED)].groupby(["judge", "model", "label_xstest"]):
        for a, b in PAIRS:
            pa, pb = per_prompt(g[g.lang == a]), per_prompt(g[g.lang == b])
            common = pa.index.intersection(pb.index)
            if not len(common):
                continue
            d = pa[common] - pb[common]
            for eff, ids in d.groupby(effect.reindex(common).values):
                m, lo, hi = boot_mean(ids.values)
                rows.append(dict(comparison=f"{a}−{b}", judge=judge, model=model, label=label,
                                 translation_effect=eff, n_prompts=len(ids),
                                 delta=m, ci_lo=lo, ci_hi=hi))
teff = pd.DataFrame(rows)
teff.to_csv("results/translation_effect.csv", index=False)
if len(teff):
    print("Kategorie tłumaczenia:")
    print(prompts.groupby(["translation_effect", "label"]).size().unstack(fill_value=0), "\n")

# ---------------------------------------------------------------- 6. ucięte odpowiedzi
trunc = outs.groupby(["model", "lang"]).agg(truncated=("truncated", "mean"),
                                            mean_prompt_tokens=("prompt_tokens", "mean"),
                                            mean_response_tokens=("response_tokens", "mean")).reset_index()
trunc.to_csv("results/truncation.csv", index=False)

# ---------------------------------------------------------------- podsumowanie
pd.set_option("display.width", 160, "display.max_columns", 20, "display.precision", 3)
print("== 1. Wskaźnik odmów (5 ziaren, 95% CI) ==")
print(rates.pivot_table(index=["model", "label"], columns=["lang", "judge"], values="refusal"), "\n")
print("== 2. Różnice sparowane (5 ziaren) vs pojedynczy przebieg greedy ==")
print(delta[["comparison", "judge", "model", "label", "delta", "ci_lo", "ci_hi", "significant",
             "delta_greedy", "greedy_outside_ci"]].to_string(index=False), "\n")
print(f"Greedy poza przedziałem ufności z 5 ziaren: {delta.greedy_outside_ci.sum()}/{len(delta)} porównań\n")
print("== 3. Szum ziaren ==")
print(noise[["judge", "model", "lang", "label", "seed_min", "seed_max", "seed_range",
             "unstable_prompts"]].to_string(index=False), "\n")
print("== 4. Zgodność sędziów ==")
print(agree.to_string(index=False), "\n")
if len(pres):
    print("== 5a. Tłumaczenia z zachowanym wyzwalaczem (200/200, 95% CI Wilsona) ==")
    print(pres.to_string(index=False), "\n")
if len(teff):
    print("== 5b. Różnice wg kategorii tłumaczenia (safe) ==")
    print(teff[teff.label == "safe"].to_string(index=False), "\n")
print("== 6. Ucięte odpowiedzi ==")
print(trunc.to_string(index=False))
print("\nWszystkie tabele → results/")
