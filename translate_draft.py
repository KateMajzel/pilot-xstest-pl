"""Krok 2 pilotażu: SZKIC tłumaczeń PL przez Claude — do ręcznej weryfikacji.

Uruchom:  python translate_draft.py            (wszystkie 200)
          python translate_draft.py --limit 5  (test)

Wynik:    data/prompts_pl_draft.csv  — osobny plik, NIE nadpisuje prompts_en.csv.
          Kolumny: id, label, type, prompt, prompt_pl_draft, cultural_change_draft,
                   trigger_strength, status
Po przeglądzie przenosisz zaakceptowane tłumaczenia do kolumny prompt_pl w prompts_en.csv.
Skrypt pomija prompty już przetłumaczone, więc przerwany przebieg można wznowić.
"""
import argparse
import csv
import json
import os
import re

import httpx
import pandas as pd

from judge import load_env

MODEL = "claude-sonnet-5-5"   # mocniejszy model niż sędzia — tłumaczenie homonimów jest trudne
OUT = "data/prompts_pl_draft.csv"
FIELDS = ["id", "label", "type", "prompt", "prompt_pl_draft",
          "cultural_change_draft", "trigger_strength", "status"]

INSTRUCTION = """You are helping build a Polish version of XSTest, a research benchmark that measures
whether AI assistants refuse requests correctly. Safe prompts deliberately contain words that SOUND
harmful but are harmless in context (e.g. "kill a Python process", "beat my competition").
Unsafe prompts are their harmful counterparts. The Polish version must test the SAME thing.

Translate the prompt below into natural Polish following these rules:
1. Preserve the construct. If the English uses a word with a violent/harmful surface meaning,
   choose a Polish word or phrase with a similar double meaning, even if slightly less idiomatic.
   Do NOT replace it with a neutral word that removes the trigger.
2. Preserve intent strength. Do not soften or sharpen the request. Safe stays safe, unsafe stays unsafe.
3. Keep names, places and references unless they would make no sense to a Polish reader;
   if you change one, say so.
4. Report how well the trigger survived: "same", "weaker" or "stronger" than in English
   (use "none" if the prompt has no trigger word).

Category of this prompt: {type} ({label})
English prompt: {prompt}

Reply with JSON only, no other text:
{{"pl": "...", "cultural_change": "empty string, or a short note in Polish on any change or problem",
  "trigger_strength": "same|weaker|stronger|none"}}"""


def ask(client, text):
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"},
        json={"model": MODEL, "max_tokens": 2048,
              "messages": [{"role": "user", "content": text}]},
    )
    r.raise_for_status()
    d = r.json()
    out = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return out, d.get("stop_reason")


def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    load_env()

    df = pd.read_csv("data/prompts_en.csv")
    done = set()
    if os.path.exists(OUT):
        done = {int(r["id"]) for r in csv.DictReader(open(OUT, encoding="utf-8"))
                if r["status"] == "ok"}
    todo = df[~df["id"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"Do przetłumaczenia: {len(todo)}, gotowych: {len(done)}")

    new_file = not os.path.exists(OUT)
    stats = {"ok": 0, "unparsed": 0, "error": 0}
    with httpx.Client(timeout=120) as client, open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, (_, row) in enumerate(todo.iterrows(), 1):
            rec = {"id": int(row["id"]), "label": row["label"], "type": row["type"],
                   "prompt": row["prompt"], "prompt_pl_draft": "", "cultural_change_draft": "",
                   "trigger_strength": "", "status": "error"}
            try:
                raw, stop = ask(client, INSTRUCTION.format(**row))
                j = parse(raw)
                if j and j.get("pl"):
                    rec.update(prompt_pl_draft=j["pl"],
                               cultural_change_draft=j.get("cultural_change", ""),
                               trigger_strength=j.get("trigger_strength", ""), status="ok")
                else:
                    # np. odmowa tłumaczenia — zapisujemy surowy tekst do ręcznej obsługi
                    rec.update(cultural_change_draft=f"[{stop}] {raw.strip()[:200]}",
                               status="unparsed")
            except httpx.HTTPError as e:
                rec["cultural_change_draft"] = str(e)[:200]
            stats[rec["status"]] += 1
            w.writerow(rec)
            f.flush()
            print(f"[{i:>3}/{len(todo)}] id={rec['id']:>3} {rec['label']:6} {rec['status']:8} "
                  f"{rec['trigger_strength']:8} {rec['prompt_pl_draft'][:60]!r}")

    print("\nPodsumowanie:", stats)
    print("Gotowe →", OUT)


if __name__ == "__main__":
    main()
