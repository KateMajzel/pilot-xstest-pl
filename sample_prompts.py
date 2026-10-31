"""Krok 1 pilotażu: losowanie warstwowe 100 bezpiecznych + 100 niebezpiecznych promptów z XSTest.

Uruchom:  python sample_prompts.py
Wynik:    data/prompts_en.csv  (200 wierszy, kolumny do tłumaczenia już dodane)
"""
import os
import urllib.request

import pandas as pd

SEED = 20261018          # zapisane ziarno = ktoś inny wylosuje identyczne 200 promptów
N_PER_LABEL = 100
URL = ("https://raw.githubusercontent.com/paul-rottger/"
       "exaggerated-safety/main/xstest_prompts.csv")
RAW = "data/xstest_prompts.csv"

os.makedirs("data", exist_ok=True)
if not os.path.exists(RAW):
    urllib.request.urlretrieve(URL, RAW)

df = pd.read_csv(RAW)

# 1) Zawsze najpierw obejrzyj dane, zanim cokolwiek z nimi zrobisz.
print("Kolumny:", list(df.columns))
print("Liczba promptów:", len(df))
print(df["label"].value_counts(), "\n")
print(df.groupby(["label", "type"]).size(), "\n")

# 2) Losowanie warstwowe: z każdej kategorii (type) bierzemy proporcjonalnie,
#    żeby próbka 100 miała ten sam rozkład kategorii co całość.
def stratified(group_df: pd.DataFrame, n: int) -> pd.DataFrame:
    frac = n / len(group_df)
    parts = [
        g.sample(n=max(1, round(len(g) * frac)), random_state=SEED)
        for _, g in group_df.groupby("type")
    ]
    out = pd.concat(parts)
    # zaokrąglenia mogą dać 99 albo 101 — dociągamy/obcinamy deterministycznie
    if len(out) > n:
        out = out.sample(n=n, random_state=SEED)
    elif len(out) < n:
        rest = group_df.drop(out.index)
        out = pd.concat([out, rest.sample(n=n - len(out), random_state=SEED)])
    return out

sample = pd.concat(
    stratified(df[df["label"] == lab], N_PER_LABEL) for lab in ["safe", "unsafe"]
).sort_values("id")

# 3) Kolumny na tłumaczenie i notatki — wypełniasz je ręcznie w kroku 2.
sample["prompt_pl"] = ""
sample["cultural_change"] = ""   # np. zmieniona nazwa, realia prawne
sample["backtranslate"] = False

sample.to_csv("data/prompts_en.csv", index=False)
print("Zapisano", len(sample), "promptów")
print(sample.groupby(["label", "type"]).size())
