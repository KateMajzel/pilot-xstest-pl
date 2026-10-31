"""Krok 2b: arkusz do przeglądu tłumaczeń (Excel/LibreOffice).

Uruchom:  python make_review.py
Wynik:    data/review_pl.xlsx

Kolejność wierszy = kolejność przeglądu:
  1) tłumacz MT sam zgłosił zmianę wyzwalacza (weaker / stronger),
  2) kategorie, w których słowo-wyzwalacz jest sednem testu (homonimy, metafory),
  3) reszta.
Wypełniasz dwie kolumny: prompt_pl_final (wstępnie = szkic MT, poprawiasz w miejscu)
oraz translation_effect (lista rozwijana). Notatki — w kolumnie notes.
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

EFFECTS = ["preserved", "trigger_weakened", "trigger_strengthened", "meaning_shifted"]
KEY_TYPES = {"homonyms", "contrast_homonyms", "figurative_language", "contrast_figurative_language"}

d = pd.read_csv("data/prompts_pl_draft.csv")
d = d[d["status"] == "ok"].drop_duplicates("id", keep="last")
assert len(d) == 200, f"oczekiwano 200 tłumaczeń, jest {len(d)}"


def priority(r):
    if r["trigger_strength"] in ("weaker", "stronger"):
        return 1
    if r["type"] in KEY_TYPES:
        return 2
    return 3


d["priority"] = d.apply(priority, axis=1)
d = d.sort_values(["priority", "type", "id"])

cols = ["priority", "id", "label", "type", "prompt", "prompt_pl_draft", "trigger_strength",
        "cultural_change_draft", "prompt_pl_final", "translation_effect", "notes"]
d["prompt_pl_final"] = d["prompt_pl_draft"]
d["translation_effect"] = ""
d["notes"] = ""

wb = Workbook()
ws = wb.active
ws.title = "przeglad"
ws.append(cols)
for _, r in d[cols].fillna("").iterrows():
    ws.append(list(r.values))

widths = {"A": 8, "B": 6, "C": 8, "D": 22, "E": 45, "F": 45, "G": 11, "H": 35, "I": 45, "J": 22, "K": 30}
for c, w in widths.items():
    ws.column_dimensions[c].width = w
for cell in ws[1]:
    cell.font = Font(bold=True)
for row in ws.iter_rows(min_row=2):
    for cell in row:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    row[8].fill = PatternFill("solid", fgColor="FFF4CC")   # prompt_pl_final — do edycji
    row[9].fill = PatternFill("solid", fgColor="FFF4CC")   # translation_effect — do wyboru
ws.freeze_panes = "E2"

dv = DataValidation(type="list", formula1='"' + ",".join(EFFECTS) + '"', allow_blank=True)
ws.add_data_validation(dv)
dv.add(f"J2:J{ws.max_row}")

wb.save("data/review_pl.xlsx")
print(d["priority"].value_counts().sort_index().rename({1: "1: MT zgłosił zmianę",
      2: "2: homonimy/metafory", 3: "3: reszta"}))
print("Gotowe → data/review_pl.xlsx")
