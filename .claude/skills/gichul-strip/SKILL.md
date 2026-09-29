---
name: "gichul-strip"
description: Repo version of exam-answer-strip — extract and typeset one answer-marked 기출 PDF from 올리기/<과목>/ into a clean question-only PDF, as step 1 of the gichul-classify workflow. Use it (not the account-level exam-answer-strip) for any exam PDF in this repository.
---

> **Repository paths (override every path below).** Run from the repo root.
> Scripts: `S=.claude/skills/gichul-strip/scripts`. Fonts: `python3 $S/setup_fonts.py fonts`
> (done by `bash tools/setup.sh`). `<시험id>` = the PDF file name without `.pdf`.
> Input: `올리기/<과목>/<시험id>.pdf`. Workdir: `work/<시험id>/` (git-ignored).
> Output of step 5: `문제지/<과목>/시험별/<YYMMDD>_<시험명>_문제.pdf`.
> After step 5 passes, copy `fixes.json` + `meta.json` to `작업기록/<과목>/<시험id>/`.
> "Deliver" is not present_files: this skill is step 1 of the `gichul-classify` workflow,
> which continues with classification, lecture PDFs and the commit.

# Exam answer-strip PDF

Rebuild an answer-marked exam PDF as a question-only A4 PDF. Two things decide
success, and every step below exists to protect one of them:

1. **No answer leaks.** Answer marks (colour *or* size), 오답노트/해설 boxes, and
   in-stem hints like "(2번, 4번 복수정답처리)" must all go.
2. **No corrupted questions.** Every stem line and choice line survives, in order,
   in the right choice. A dropped first line of ① is as bad as a leaked answer.

The scripts do the deterministic work. Your judgement is needed for three things
only: line-break spaces, typo calls, and the visual check.

## Workflow

Work in `/home/claude/exam/<stem-of-pdf>/`. Locate the scripts with
`S=$(ls -d /mnt/skills/*/exam-answer-strip/scripts | head -1)` (the install path differs
between user skills and plugins).

### 1. Fonts
```bash
python $S/setup_fonts.py            # needs KoPubWorld Batang Pro Medium + Bold in uploads
```
If either font file is missing, ask the user to upload it before going further.
The script copies the OTFs to `~/.fonts` and also registers TrueType copies as
family `KoPubBatangTT`. That second part matters: wkhtmltopdf draws `@font-face`
and CFF-OTF fonts as outlines, which leaves a PDF with no text layer (unsearchable,
and the leak scan in step 5 would silently see nothing).

### 2. Extract and reconcile
```bash
python $S/extract.py /mnt/user-data/uploads/<file>.pdf /home/claude/exam/<name>
```
It classifies lines by **font size, x-position and colour** (printed as a
distribution — glance at it for anything odd), crops figures, detects the
`출제자 : …` bylines (stored in `meta.json → authors`, printed automatically above
each question), and writes `parsed.json`, `report.txt`, `joins.txt`, an empty
`fixes.json`, a WARNINGS list and a RECONCILIATION block. **Do not continue until every check says OK.** If one fails,
the layout differs from what the scripts expect; look at the distribution and
`report.txt`, find the category that is off, and fix the classification in
`extract.py` (copy the skill to `/home/claude` first if the install path is read-only).

**Check every WARNING against a render of the source page.** Red text is how
hand-added memos appear (one source had "정답수정 4 or 5" beside a question, and it
extracted as garbled characters, so the leak regex could not see it); red media lines
(`동영상 : ….mp4`) are the other common case. Garbled lines are font-mapping failures
— render the region (`page.get_pixmap(clip=…)`) and look.

Then read `report.txt` end to end. Choices marked `*` were answer-marked in the
source, which is only there so you can spot problems. Watch for:
- a choice that begins mid-sentence, or two choices that look swapped: a page
  break scrambled it → `regroup`
- stem lines that are really a data block (`CVP ↑, CO ↓ …`, lab values typed
  inline) → `split_box`
- long English passages in a box → `prose_boxes` (+ `para_starts` where the
  original had paragraph/formula breaks)
- garbled text where the source had a table → `drop_lines` + `extra_figs`
- hints that give away the answer; answers typed into 주관식 → `fixes` with `new=""`;
  a memo that is a box's only line → `drop_lines` (the empty box is then omitted)
- a stem the source printed twice (once in a box, once as text) → `drop_lines`
  every line of the box; the question then lays out as a plain one
- `동영상/오디오 : ….mp4` lines glued to choice ① → `regroup` ① without it and list
  the line under `media` (rendered as a grey box between stem and choices)
- lab data inside a box whose lines break mid-word (`백혈|구(-)`) → `prose_boxes`
  with `para_starts` (e.g. `["•"]`) so each bullet stays its own paragraph
- a question with no choices at all because the source lost them (figure and
  options missing, not a 주관식) → `no_choice_note` with the note to print instead of
  "(주관식 — 답안 서술형)"
- 출제자: detected automatically; set `authors` in fixes only to override
  (`{}` = print none)

### 3. Decide line-break spaces
The source PDFs drop line-final spaces, so geometry cannot tell `심|하게` (one
word) from `아래쪽에서|짓누르는` (two words). Read every entry in `joins.txt` and
put the breaks that need a space into `fixes.json → spaces`. There are usually
100–200 entries and roughly a third need a space; this is the single most
tedious step and it is what makes the text read naturally, so don't skip it.
Non-Hangul breaks are handled automatically. `joins.txt` does not list lines inside
grey boxes; for prose boxes and `split_box` regions, read those breaks from
`report.txt` and add them under the box's own tag (e.g. `"64/s1": [4]` for
`응급실 내원|당시`).

### 4. Content fixes → `fixes.json → fixes`
- Fix mechanical spacing inside a line (`2병을마셨고`, `무엇인가?약`, missing `.`),
  and unambiguous letter-level typos (`Sjgren→Sjögren`, `enenma→enema`,
  `opthalmic→ophthalmic`). A correct spelling of the same term elsewhere in the
  same exam is good evidence.
- Leave alone anything that could be the trap — a plausible-but-wrong drug name,
  a spelling variant like `clindamycine`, a number, a negation — and anything that
  is the source's own error (garbled passage, duplicated word, duplicated choice).
  Report these instead.
- Sub/superscripts (mm³, PaO₂, HCO₃⁻, Ca²⁺, FEV₁, HbA₁c, ⁹⁹ᵐTc…) are converted
  automatically; T3/T4 and G0/G1/G2 stay plain. Add `extra_subsup` for others. If
  `setup_fonts.py` reported a missing glyph, use `<sup>`/`<sub>` in the replacement.

Full key reference and an example: `references/fixes_format.md`.

### 5. Build and verify
```bash
python $S/build.py /home/claude/exam/<name> "/mnt/user-data/outputs/<YYMMDD>_<시험명>_문제.pdf"
```
Use the title from `meta.json` for the filename (spaces → `_`). The script prints
four checks — text-layer fonts, all question numbers present, answer-leak regex
(the subtitle's "(정답 표시 없음)" is excluded), and byline→number gap uniform
across plain and box-first questions (spread ≤ 1 pt; 0.6 pt is one render pixel) —
plus any `fixes` whose old text wasn't found. All must be OK and none unapplied.

Then look at the pages yourself; the checks can't see layout:
```bash
python $S/review.py <workdir> sheets                 # overview strips, 8 pages each
python $S/review.py <workdir> pages 5 6              # closer look
python $S/review.py <workdir> find "O₂" "mm³" "첫 줄 텍스트"   # zoomed snippets
```
Look for: a number stranded apart from its figure, a box that looks like it
belongs to the previous question, figures too small to read, and every place you
regrouped/split/fixed. Iterate on `fixes.json` and rebuild — the scripts
stay untouched.

### 6. Deliver
`present_files` the PDF, then report briefly:
- pages / questions / figures, and that reconciliation + leak scan passed
- **(1) 고친 것** by question number (spacing, typos, sub/superscripts, regroups,
  removed hints)
- **(2) 원문 유지하고 알려만 두는 것** (source errors, possible trap spellings)
- any judgement call the user might want reversed, flagged so they can say so

## Layout (implemented in build.py — change only if the user asks)

A4, margins 11 mm top/bottom and 12 mm left/right, passed to wkhtmltopdf in real mm.
Every CSS size is pre-multiplied by 1.30259, because wkhtmltopdf lays out at
125 dpi and prints at 96 dpi. Title 21 pt bold; subtitle 10.5 pt grey
`시험일 : YYYY-MM-DD · 총 N문항 · 문제만 수록 (정답 표시 없음)`. Stem 12 pt bold with
number in #1a4f8a; choices 11 pt with ①②③ and hanging indent; 8 pt grey
`출제자 : …` byline above the question.
Byline spacing: the byline sits outside the question body (`.qb`), and the gap
constants `BYLINE_GAP` (3.0 mm, plain) / `BYLINE_GAP_BF` (0.95 mm, box-first) are
tuned so the byline→number distance is identical for both kinds, because a
box-first number is aligned with the box's first text line, `BOX_PAD_V` below the
box edge. Change them together and re-run the build's gap check. Grey boxes (11 pt, weight 400, #333) hold conditions, lab data, <보기>,
and clinical numbers. Figure width is min(186 mm, px/4.2); height caps are
165/140/115 mm by aspect (>1.7 / >1.3 / else). Each question uses
`page-break-inside: avoid`. Questions whose choices are all images get a
two-column grid on a fresh page (caps 85/66 mm) so the whole set fits on one page.
Questions that open with a box hang their number in the margin beside it. Page
numbers `n / N` are overlaid bottom-centre with pypdf + reportlab.

## Why the parser works the way it does

Knowing these helps when a new file breaks a check:
- **Answer marks aren't only colour.** One source marked an answer with black
  text at 13.5 pt instead of 11.2 pt. Classification is by size bands, so the
  mark never matters: everything is re-typeset plainly.
- **Choice numbers sit at the vertical centre of multi-line choices.** The first
  line of a choice can be *above* its number, so choice lines are assigned to
  numbers by distance (DP over contiguous runs), never "lines after the marker".
  An earlier version lost the first line of six ① choices this way; the
  choice-line count check exists to catch it.
- **Figures belong to the last choice number that starts before the figure's
  bottom edge.** Numbers are centred on image choices, or left behind on the
  previous page when the image overflows; this rule handles both.
- **Number and first stem line can be one text line.** Some files put `10.` and
  the stem in separate spans of the same line from some question on (1–9 split,
  10–72 merged). Such lines are split by span before classification; without it
  only 23 of 72 questions were found.
- **출제자 lines are bylines, not labels.** They sit right-aligned at the aside
  x-position, so without their own class they were attached as a caption to the
  previous question's last choice (and one following a 해설 note was dropped with it).
  They now belong to the next question number in reading order; a header byline
  goes to question 1.
- **Box-first numbers used to be positioned from the byline.** With the number
  absolutely positioned inside the whole question div, a byline pushed the box down
  but not the number, so the number hugged the byline and the gap differed from
  plain questions.
- **Choice text can sit past the box threshold.** One source set every choice of a
  question as a bulleted list ("● Aortic stenosis", text at x≈110). Box-classified
  lines after the choices that share a row with a choice number are folded into that
  choice, and lone bullet glyphs are dropped (counted in the reconciliation).
- **Word list numbering leaves orphans.** Sources written with automatic numbering
  keep bare "1." "2." "3." lines (and bullet glyphs) beside indented stems and
  choices. They are classified `junk` and dropped before anything else; question-size
  text indented to x≈119 is still stem, and box-position text between the first
  choice number and the first ⓘ note is choice text. A choice line that sits *above*
  its number at box position can still land in a box — check `report.txt` and fix
  with `regroup` + `drop_lines` (201130 Q75).
- **주관식 answers are typed in.** Choice-size text under a question with no choice
  numbers is the answer; extract drops it and prints it (`!! Qn: 주관식 answer text
  dropped`). Read those lines to confirm nothing of the stem went with them.
- **Some pages carry a full-page background image.** Merged with a real figure it
  made one page-sized "figure" that landed on the last choice; images covering
  ≥85% of the page are ignored.
- **The leak regex also fires on instructions.** "(정답 3개)" in a stem is a count,
  not an answer; reword it to "(답 3개)" with a fix and report it.
- **ⓘ-headed boxes are notes.** They are dropped up to the next non-box element,
  and the box-line count check proves nothing else was dropped.
