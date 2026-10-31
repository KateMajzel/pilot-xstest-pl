"""Krok 1b/3 pilotażu: generacja odpowiedzi modelu na prompty.

Przykład (test ścieżki):
    python generate.py --model Qwen/Qwen2.5-1.5B-Instruct --lang en --limit 10 --seeds 0

Pełny przebieg (później):
    python generate.py --model <model> --lang pl|pl_mt|en --seeds 0 1 2 3 4 greedy --load-4bit

Wynik: outputs/<model>__<lang>.jsonl  — jedna linia = jedna odpowiedź + pełne metadane.
Skrypt pomija odpowiedzi, które już są w pliku, więc przerwany przebieg można wznowić.
"""
import argparse
import json
import os
import time

import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

TEMPERATURE = 0.7
TOP_P = 0.9
MAX_NEW_TOKENS = 512

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--lang", choices=["en", "pl", "pl_mt"], required=True,
                help="en = oryginał; pl = tłumaczenie zweryfikowane; pl_mt = surowe tłumaczenie MT")
ap.add_argument("--seeds", nargs="+", default=["0"],
                help="liczby = próbkowanie z danym ziarnem; 'greedy' = dekodowanie zachłanne")
ap.add_argument("--limit", type=int, default=None, help="tylko pierwsze N promptów (do testów)")
ap.add_argument("--load-4bit", action="store_true", help="kwantyzacja 4-bit (dla modeli 7–11B)")
args = ap.parse_args()

# --- dane ---------------------------------------------------------------
df = pd.read_csv("data/prompts_en.csv")
col = {"en": "prompt", "pl": "prompt_pl", "pl_mt": "prompt_pl_mt"}[args.lang]
df = df[df[col].fillna("").str.strip() != ""]          # pomija nieprzetłumaczone
if args.limit:
    df = df.head(args.limit)
print(f"{len(df)} promptów, język {args.lang}, ziarna {args.seeds}")

# --- model --------------------------------------------------------------
tok = AutoTokenizer.from_pretrained(args.model)
kw = {"device_map": "cuda", "dtype": torch.bfloat16}
if args.load_4bit:
    from transformers import BitsAndBytesConfig
    kw["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
model = AutoModelForCausalLM.from_pretrained(args.model, **kw)
model.eval()

# --- wznawianie: co już mamy? ---------------------------------------------
os.makedirs("outputs", exist_ok=True)
out_path = f"outputs/{args.model.replace('/', '__')}__{args.lang}.jsonl"
done = set()
if os.path.exists(out_path):
    with open(out_path) as f:
        for line in f:
            r = json.loads(line)
            done.add((r["id"], r["seed"]))
print(f"Już w pliku: {len(done)} odpowiedzi")

# --- generacja -------------------------------------------------------------
with open(out_path, "a") as f:
    for seed in args.seeds:
        for _, row in df.iterrows():
            if (int(row["id"]), seed) in done:
                continue
            messages = [{"role": "user", "content": row[col]}]
            # transformers 5.x zwraca słownik (input_ids + attention_mask), nie sam tensor
            inputs = tok.apply_chat_template(
                messages, add_generation_prompt=True,
                return_tensors="pt", return_dict=True,
            ).to(model.device)
            n_prompt = inputs["input_ids"].shape[1]

            if seed == "greedy":
                gen_kw = {"do_sample": False}
            else:
                torch.manual_seed(int(seed))
                gen_kw = {"do_sample": True, "temperature": TEMPERATURE, "top_p": TOP_P}

            t0 = time.time()
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                     pad_token_id=tok.eos_token_id, **gen_kw)
            new_ids = out[0, n_prompt:]
            response = tok.decode(new_ids, skip_special_tokens=True)

            rec = {
                "id": int(row["id"]), "label": row["label"], "type": row["type"],
                "lang": args.lang, "model": args.model, "seed": seed,
                "quant": "4bit" if args.load_4bit else "bf16",
                "temperature": None if seed == "greedy" else TEMPERATURE,
                "top_p": None if seed == "greedy" else TOP_P,
                "prompt": row[col],
                "prompt_tokens": int(n_prompt),
                "response": response,
                "response_tokens": int(len(new_ids)),
                "truncated": int(len(new_ids)) >= MAX_NEW_TOKENS,
                "seconds": round(time.time() - t0, 2),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{seed}] id={rec['id']:>3} {rec['label']:6} "
                  f"{rec['response_tokens']:>3} tok  {rec['seconds']}s  "
                  f"{response[:70]!r}")

print("Gotowe →", out_path)
