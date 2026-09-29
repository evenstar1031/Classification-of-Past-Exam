# fixes.json — per-exam decisions

`extract.py` creates an empty `WORKDIR/fixes.json`; `build.py` reads it. Everything
exam-specific lives here as data so the scripts never need editing. Keys:

Block tags come from `report.txt`: `s0`, `s1`… are the question's blocks in order
(text / box / fig share one counter), `c1`…`cN` are choices, `l1`…`lN` choice captions.

| key | shape | use |
|---|---|---|
| `title`, `date` | string / null | override header autodetect (`null` = use autodetect) |
| `authors` | `null` / `{}` / `{"12": "홍길동"}` | `null` (default) = use bylines auto-detected into `meta.json`; `{}` = print none; a dict overrides |
| `spaces` | `{"3/s0": [0, 4], "15/c2": [0], "64/s1": [4]}` | break indices where a space belonged — from `joins.txt`, plus box tags for prose boxes (count breaks from `report.txt`) |
| `fixes` | `[[q, where, old, new, note], …]` | literal replace. `where` = `"stem"`, `"c3"`, `"l1"`, `"box"` (any grey box of that question, including `split_box` regions). `new=""` deletes (answer hints). `note` is what you report |
| `regroup` | `{"73": {"1": [lines…], "2": [lines…]}}` | hand-set a choice's lines when a page break scrambled them |
| `prose_boxes` | `[28, 35]` | boxes that are flowing prose (join lines) rather than tabular lab data (keep line breaks) |
| `para_starts` | `{"35": ["SI=SI0", "Within minutes"]}` | inside a prose box, start a new paragraph at lines beginning with these |
| `split_box` | `{"3/s0": [8, 10]}` | lift stem lines [a, b) into a grey box (e.g. `CVP ↑, CO ↓ …`) |
| `drop_lines` | `{"41/s0": [5, 6]}` | delete lines (garbled table text you replace with an image; a memo box — dropping its only line removes the box) |
| `no_choice_note` | `{"83": "(원본 PDF에 그림과 보기가 빠져 있음)"}` | text printed under a question that has no choices, instead of the 주관식 note |
| `media` | `{"61": ["오디오 : 2025….mp4"]}` | media-file lines, shown as a grey box after the stem (pair with `regroup` to take them out of ①) |
| `extra_figs` | `{"41": [{"page": 24, "rect": [88, 300, 520, 450], "after_block": 0}]}` | crop a region of the source PDF (0-based page, PDF points) and insert it after block N |
| `extra_subsup` | `[["\\bNH4\\+", "NH₄⁺"]]` | extra regex replacements on top of the built-in sub/superscript list |

## Example (from 230824 본1 진단의 기본)

```json
{
 "title": null, "date": null, "authors": null,
 "spaces": {"3/s0": [0, 4], "9/s0": [3], "25/s0": [0, 4]},
 "fixes": [
  [11, "stem", "# 환자의 시야검사", "환자의 시야검사", "원문 앞머리의 편집 기호 \"#\" 제거"],
  [57, "c2", "Sjgren’s syndrome", "Sjögren’s syndrome", "오타 Sjgren → Sjögren"]
 ],
 "regroup": {"73": {"1": ["동일한 … 유사한 영", "상정보를 획득할 수 밖에 없다."]}},
 "prose_boxes": [28, 35],
 "split_box": {"3/s0": [8, 10], "62/s0": [5, 7]},
 "para_starts": {"28": ["If the time TR", "Both weightings"], "35": ["SI=SI0", "Within minutes"]},
 "drop_lines": {}, "extra_figs": {}
}
```

## Deciding `spaces` quickly

`joins.txt` lists every break where both sides are Hangul, e.g.
`3/s0|0|가슴 아래쪽에서|짓누르는듯한`. Ask: is the right side the start of a new 어절?
Particles/endings on the left (`에서`, `으로`, `하고`, `이며`, `었고`, `다.` inside a
sentence) followed by a free-standing word on the right usually mean *space*;
a left side ending mid-word (`심|하게`, `혈액검|사`, `내원하였|다`) means *no space*.
Typically ~30% of breaks need a space. Write only the ones that do.
