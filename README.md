# From verdict to behaviour: a pilot on the reliability of automated safety evaluations (XSTest, Polish vs English)

**Status:** 12-day pilot (Oct 2026), single annotator, draft report. Numbers are final for this pilot. Findings marked *hypothesis* are not yet tested.

**Question.** When an LLM judge scores a safety evaluation, how much of the reported number belongs to the model, and how much to the measuring instrument (judge, decoding, language, translation, token budget)?

## Main findings

| | |
|---|---|
| **Lead (hypothesis): judges agree with each other more than with a human** | Across all responses (n = 3,594 EN, 3,598 PL), judge–judge binary κ is 0.91 (EN) and 0.89 (PL), the kind of number usually read as evidence of reliability. On the human-rated subset, in English, Claude Haiku 5.5 and gpt-oss-120b agree on 42/42 binary labels, and both differ from the human label on the same 3. In Polish this holds for one of the two judges. Binary κ judge–human in Polish: 0.62 [0.35, 0.81] (Claude) and 0.76 [0.56, 0.95] (gpt-oss); judge–judge 0.76 [0.53, 0.95]. Aggregate refusal rates still match the human within 2.4 pp, although 7–19% of individual binary labels disagree, because the errors cancel. Neither judge labelled any of the 6 responses I coded PARTIAL as PARTIAL. With one annotator and n = 42 per language, this is a hypothesis about direction, not a result. |
| **Language gap in over-refusal** | On *safe* prompts, refusal rises from English to Polish: Qwen2.5-7B 10.8% → 20.8% (+10.0 pp, 95% CI [+4.6, +15.6]); Llama-3.1-8B 14.0% → 23.6% (+9.6 pp, [+3.8, +16.4]). Both judges agree on direction and significance. Bielik-11B shows no gap (+1.6 pp, ns). The gap persists on the 85 safe prompts whose trigger word survived translation (Qwen +8.5, Llama +8.2 pp). |
| **Decoding changes the conclusion** | Llama's gap is +9.6 pp over 5 sampled seeds but +2.0 pp with a single greedy run. Greedy fell outside the 5-seed CI in 4 of 12 PL–EN comparisons. |
| **Measurement artefacts are large** | Polish responses hit the 512-token limit 2–5× more often (Bielik 33.3% vs 6.5%, Llama 22.8% vs 10.8%, Qwen 10.9% vs 2.5%). As a result the *unsafe*-prompt results are unresolved. |

Judge = Claude Haiku 5.5 for the CIs above. gpt-oss-120b gives the same direction (see `deltas.csv` and `robust_summary.txt`). CIs come from a cluster bootstrap over prompts, B = 2000.

**Provenance.** This public repo was created fresh, so that withheld data never appears in its history. `PROVENANCE.txt` lists the commit log of my private working repo (dates and messages only). It shows that `CODEBOOK.md` was committed before the human sample was drawn.

## Setup

- **Benchmark:** XSTest ([Röttger et al., 2024](https://arxiv.org/abs/2308.01263)), a stratified sample of 200 prompts (100 safe, 100 unsafe), seed 20261018.
- **Polish prompts:**
  - Machine translation (Claude Sonnet 5.5) with a trigger-preservation instruction.
  - Manual review of all 200 prompts.
  - Three prompts (ids 103, 165, 428) were translated manually.
  - The trigger was preserved in 85/100 safe prompts (Wilson 76.7–90.7%) and 100/100 unsafe prompts.
- **Models:** Qwen2.5-7B-Instruct, Llama-3.1-8B-Instruct, Bielik-11B. All loaded in 4-bit.
- **Decoding:** 5 seeds at T = 0.7, plus one greedy run; `max_new_tokens = 512`.
- **Judges:** Claude Haiku 5.5 (Anthropic API) and gpt-oss-120b (OpenRouter). Three classes: COMPLIANCE / PARTIAL / REFUSAL. Binary refusal = REFUSAL or PARTIAL.
- **Human check:**
  - 84 responses (42 per language), rated blind to the judges.
  - The codebook (`CODEBOOK.md`) was committed before sampling.

## What is in this repo, and what is deliberately not

| Included | Not included (and why) |
|---|---|
| All code (`*.py`) | Polish translations of **unsafe** prompts (could lower the barrier to misuse in Polish) |
| Aggregate results (`*.csv`, `*.txt` in the main folder) | Model completions, including harmful ones (safety, and model licences) |
| Codebook, lab notebook | Raw judge outputs and the manual-review spreadsheet (they contain response text) |
| Provenance log (`PROVENANCE.txt`)| API keys (`.env` is git-ignored; see `.env.example`) |

Researchers who need the withheld data for replication can contact me.

## Pipeline

```
translate_draft.py → make_review.py → merge_review.py   # Polish prompts + manual review
generate.py   --model <hf_id> --lang {en,pl} --seeds ... # GPU, 4-bit
judge.py      --judge anthropic:claude-haiku-5-5 --input outputs/<file>.jsonl
analyze.py                                               # rates, deltas, seed noise, judge agreement, truncation
robustness.py                                            # without truncated; edited-prompt ablation
sample_manual.py → compare_human.py → sensitivity_human.py  # human vs judges
```

### Reading the result files

The files contain four conditions:
- `en`: English.
- `pl`: the final, reviewed Polish. After the full review it is identical to `pl_mt`.
- `pl_mt`: the raw machine translation, kept so that the comparison is explicit.
- `pl_neutral`: an earlier hand-edited version of 24 prompts. It is used only as an exploratory trigger ablation.

The headline comparisons are `pl` vs `en`. The console summaries (`*.txt`) have Polish headers.

`summary.txt` prints a raw count of "greedy outside the 5-seed CI: 13/48". That count covers every comparison, including the duplicate `pl_mt − en` and the ablation. The figure reported above (4/12) is `pl − en` only.

`NOTES.md` is the lab notebook (in Polish), kept chronologically. Superseded notes are marked as such rather than deleted, so the order of decisions and corrections is visible. Notes 33–34 hold the final numbers.

## Limitations

- **Annotation and benchmark:**
  - One annotator, with n = 42 per language.
  - One benchmark and 200 prompts.
  - No correction for multiple comparisons.
- **Models and generation:**
  - 4-bit models at 7–11B parameters.
  - The 512-token limit truncates many Polish responses.
- **Translation:**
  - 15 safe translations changed the trigger's strength or meaning (13 weakened, 1 strengthened, 1 shifted).
  - The Polish uses masculine grammatical forms.
- **Labels and the human sample:**
  - The COMPLIANCE label is ambiguous, and PARTIAL is unreliable.
  - The Polish human sample was drawn from responses to an earlier prompt version, in which 8 of 42 pairs had a changed prompt. κ is essentially unchanged without them (see `human_sensitivity.txt`).
- **Not tested:** the tokenisation hypothesis.

## Related work
[arXiv 2610.20221](https://arxiv.org/abs/2610.20221) (Al Sahili et al., 2026, v1) evaluates the same two models on a translated XSTest with greedy decoding, a single LLM judge (Gemma-3-12B) and automatic translation screening only; human evaluation is not yet included. They find a Polish over-refusal gap for Qwen2.5-7B (6.4% → 17.1%) but not for Llama-3.1-8B (13.6% → 12.9%). My greedy run agrees with theirs for Llama (+2.0 pp), while five sampled seeds give +9.6 pp, so decoding may explain part of the difference. Other differences between the setups (judge, translator, prompt subset, quantisation) are not yet ruled out.

My earlier Polish NLP work:
- [tokenizer-pl-32k](https://huggingface.co/KateMajzel/tokenizer-pl-32k)
- [GoLLeM-45M-PL](https://huggingface.co/KateMajzel/GoLLeM-45M-PL)
- [polish-tokenization-cost](https://huggingface.co/spaces/KateMajzel/polish-tokenization-cost)

## Changes after 31 Oct 2026

- Corrected the description of arXiv 2610.20221 after reading the full paper.
- Fixed file references: result files are in the main folder; removed an empty `results` file and a reference to a `report/` folder that was not uploaded.
- No results or numbers changed.

## Licence

Code: MIT. XSTest prompts are © Röttger et al. under CC-BY-4.0. Any XSTest-derived material here is shared under the same licence, with attribution.


## Contact

Katarzyna Majzel-Pośpiech
