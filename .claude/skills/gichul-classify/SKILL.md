---
name: gichul-classify
description: The main workflow of this repository — take 기출 PDFs from 올리기/<과목>/, strip the answers, classify every question into its lecture (수업) using 과목정보/<과목>.json (출제자 + 연도, then content), and build one answer-free PDF per lecture in 문제지/<과목>/. Use whenever the user asks here to 정리/분류/수업별로 만들어/올린 기출 처리해줘, to add a new year's exam, to move a question to another lecture, or to add a new subject.
---

# 기출 → 수업별 문제지

Three stages per exam, then one build per subject. Every stage has a check that must
say OK before moving on. The user does not code: report in plain Korean, results first.

## 0. Session start
```bash
bash tools/setup.sh              # packages, wkhtmltopdf, fonts
python3 tools/check_private.py   # must print [OK] before ANY exam file is committed
ls -R 올리기
```
If `check_private.py` does not print `[OK]`, you may still process files locally, but do
**not** commit or push anything from 올리기/원본/문제지/작업기록/분류. Tell the user how to
make the repo private (the script prints the steps) and stop there.

Subject = the folder under `올리기/` (must match a file in `과목정보/`). A PDF dropped
directly in `올리기/` → infer from file name / PDF title; ask if unclear.

## 1. Strip answers (per exam) — `gichul-strip` skill
Follow `.claude/skills/gichul-strip/SKILL.md` completely (extract → reconcile → spaces →
fixes → build → look at the pages). Its "Repository paths" block gives the paths. Do not
skip the `joins.txt` space decisions or the visual check: the lecture PDFs reuse this
exam's `fixes.json`, so every mistake here shows up in every lecture PDF.

When done: `작업기록/<과목>/<시험id>/` holds `fixes.json` and `meta.json`.

## 2. Classify (per exam)
```bash
python3 tools/classify.py auto  <과목> <시험id>
python3 tools/classify.py show  <과목> <시험id>          # the ones that need a decision
python3 tools/classify.py set   <과목> <시험id> 12=09 13=33 --why "근거 한 줄"
python3 tools/classify.py check <과목> <시험id>          # must end [OK]
```
How `auto` decides: the question's 출제자 is matched against that year's 담당교수 in
`과목정보/<과목>.json`. Exactly one lecture → done (`by: 출제자`). Years missing from the
lecture list (e.g. 2024) use the nearest year. Lectures with `"exam": false` (실습) are never
auto-candidates.

What you decide (with `set`, by reading the stem and choices that `show` prints):
- **미정 — several candidates** (one professor teaches several lectures, e.g. 정신영: PET /
  방사성의약품 원리): pick by content.
- **미정 — no match / no 출제자**: pick by content from the full lecture list `show` prints.
  Use `99` (기타) only when no lecture plausibly fits, and say so in the report.
- **출제자-이어짐** (no byline on this question, so the previous question's 출제자 was
  carried over): check the content fits; `set` it to confirm (or to the right lecture).
  Several in a row with the same carried author and matching content can be confirmed
  in one `set` call.
- Keep `--why` short and concrete ("CK-MB → 진단효소학"). The user may read it.

`auto` never overwrites a `set` decision, so it is safe to re-run.

If many questions of an exam share a professor who is not in the lecture list at all,
the 과목정보 is probably out of date for that year: tell the user rather than guessing
the same lecture for all of them.

## 3. Build the lecture PDFs (per subject, after all its exams are classified)
```bash
python3 tools/classify.py check <과목>          # table of lecture × year; must be [OK]
python3 tools/build_lectures.py <과목>          # all lecture PDFs + 00_전체 + README 목차
```
It must end with both `[OK]` lines (question count reconciles; fonts / numbers /
answer-leak scan pass for every PDF). Then look at pages: `work/_lectures/<과목>/<id>/pv/`
— at least the lectures that received questions this session and the first pages of
`00/pv/`. Check year headers, that no question is split oddly, figures are legible.

## 4. Save
```bash
git mv 올리기/<과목>/<시험id>.pdf 원본/<과목>/     # originals move once processed
python3 tools/classify.py auto <과목> <시험id>     # refreshes the stored source path (decisions kept)
python3 tools/check_private.py && git add 원본 문제지 작업기록 분류 && git commit -m "<과목>: <시험id> 분류 및 수업별 문제지"
git push
```
One commit per exam is fine; push to `main` when allowed, otherwise push the branch, open a PR,
and tell the user to press the green Merge button. Never commit `work/` or fonts outside `fonts/`.

## 5. Report (short, per exam, in Korean)
- 문항 수, 자동 분류 N / 내용으로 정한 것 M (각각 번호 → 수업, 근거 한 줄) / 기타(99)
- gichul-strip report: (1) 고친 것 (2) 원문 그대로 두고 알려만 두는 것
- 새로 문항이 들어간 수업 목록, and `문제지/<과목>/README.md` has the full table

## Other requests
- **"12번은 ○○ 수업이야"** → `classify.py set <과목> <시험id> 12=<id> --by 직접`, rebuild with
  `build_lectures.py <과목>`, commit.
- **New subject / new year's lecture list** → user uploads the new 3개년 비교 HTML to `과목정보/`;
  run `python3 tools/make_subject_info.py 과목정보/<파일>.html`. Existing lecture ids are kept
  when the lecture name is unchanged; report any lecture whose name changed (its id changes,
  so existing classifications pointing to it need `set` again — `classify.py check` finds them).
- **Screenshots instead of a PDF** → not supported by this pipeline yet (no parsed.json);
  tell the user and suggest a PDF, or offer the account-level exam-worksheet-pdf for a
  one-off worksheet.
