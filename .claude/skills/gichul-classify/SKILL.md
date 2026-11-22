---
name: gichul-classify
description: The main workflow of this repository — take 기출 PDFs from 올리기/<과목>/, strip the answers, classify every question into its lecture (수업) using _자동관리/과목정보/<과목>.json (출제자 + 연도, then content), and build one answer-free PDF per lecture in 문제지/<과목>/, plus a separate 정답·해설 edition in 해설지/<과목>/. Use whenever the user asks here to 정리/분류/수업별로 만들어/올린 기출 처리해줘, to add a new year's exam, to move a question to another lecture, to add or fix 정답·해설, or to add a new subject.
---

# 기출 → 수업별 문제지

Three stages per exam, then one build per subject. Every stage has a check that must
say OK before moving on. The user does not code: report in plain Korean, results first.

> **과목 폴더 이름** — 보이는 폴더(`문제지/`·`해설지/`·`학습자료/`·`올리기/`·`자료실/`)의 과목 폴더는 `01. 진단의 기본` 처럼 「순서 번호. 과목 이름」이고,
> `_자동관리/` 안(분류·해설·작업기록·원본·과목정보)과 프로그램 인자는 과목 키(`진단의기본`)다. 아래 `<과목>` 은 그 위치에 맞게 읽는다.
> 대응표: `python3 _자동관리/tools/subjects.py`. 프로그램에는 키·폴더 이름 어느 쪽을 넣어도 된다. 새 과목은 `subjects.py` 의 ORDER 끝에 더한다.

## 0. Session start
```bash
bash _자동관리/tools/setup.sh              # packages, wkhtmltopdf, fonts
python3 _자동관리/tools/check_private.py   # must print [OK] before ANY exam file is committed
ls -R 올리기
```
If `check_private.py` does not print `[OK]`, you may still process files locally, but do
**not** commit or push anything from 올리기/원본/문제지/작업기록/분류. Tell the user how to
make the repo private (the script prints the steps) and stop there.

Subject = the folder under `올리기/` (must match a file in `_자동관리/과목정보/`). A PDF dropped
directly in `올리기/` → infer from file name / PDF title; ask if unclear.

## 1. Strip answers (per exam) — `gichul-strip` skill
Follow `.claude/skills/gichul-strip/SKILL.md` completely (extract → reconcile → spaces →
fixes → build → look at the pages). Its "Repository paths" block gives the paths. Do not
skip the `joins.txt` space decisions or the visual check: the lecture PDFs reuse this
exam's `fixes.json`, so every mistake here shows up in every lecture PDF.

When done: `_자동관리/작업기록/<과목>/<시험id>/` holds `fixes.json` and `meta.json`.

## 2. Classify (per exam)
```bash
python3 _자동관리/tools/classify.py auto  <과목> <시험id>
python3 _자동관리/tools/classify.py show  <과목> <시험id>          # the ones that need a decision
python3 _자동관리/tools/classify.py set   <과목> <시험id> 12=09 13=33 --why "근거 한 줄"
python3 _자동관리/tools/classify.py check <과목> <시험id>          # must end [OK]
```
How `auto` decides: the question's 출제자 is matched against that year's 담당교수 in
`_자동관리/과목정보/<과목>.json`. Exactly one lecture → done (`by: 출제자`). Years missing from the
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

**내용으로 정할 때는 작년 필기본이 기준이다** (사용자 요청, 2026-11-16). 위의 "pick by content"
세 경우 모두(그리고 2단계 재검토에서도) 이 순서로 판단한다:
1. 문항의 핵심어(질환·병원체·약·검사·소견 이름, 한글과 영어 둘 다)를 뽑아
   `python3 _자동관리/tools/notes_lookup.py find <과목> 용어1 용어2 ...` (기본 = 작년 필기본, 없는 수업은 가까운 해).
2. 결과는 **힌트일 뿐 순위대로 고르지 않는다.** 핵심어가 그 수업 필기의 *주제로 다뤄지는* 곳
   (목차·제목·설명하는 쪽)을 고른다. 다른 수업에서 지나가듯 나온 것(약 이름만 나열 등)은 근거가 아니다.
   예: 쯔쯔가무시는 34 인수공통감염병에서도 맞지만 35 가을철 열성질환 목차에 있으므로 35.
   필요하면 맞은 쪽을 직접 열어 본다.
3. 필기에서 정해지면 `--why "필기25 35 p.8: eschar → 쯔쯔가무시"` 처럼 수업·쪽을 적는다.
   두 수업 필기가 똑같이 다루면 출제자·연도 정보를 우선하고, 그래도 비기면 더 자세히 다룬 쪽.
4. 어느 필기에도 없거나(`[필기에 없음]`) 지나가는 언급뿐이면 **일반 의학 지식**으로 정하고
   `--why "필기에 없음 · 일반지식: …"` 으로 표시한다.
5. `list` 에서 "글자 적음"인 수업(슬라이드 그림 위주)은 글자 검색이 놓칠 수 있다. 후보가 그 수업이면
   필기 PDF 쪽을 그림으로 봐서 확인한다.
보고의 「내용으로 정한 것」에 필기 근거 몇 개 / 일반지식 몇 개를 나눠 적는다.

`auto` never overwrites a `set` decision, so it is safe to re-run.

If many questions of an exam share a professor who is not in the lecture list at all,
the 과목정보 is probably out of date for that year: tell the user rather than guessing
the same lecture for all of them.

## 3. Build the lecture PDFs (per subject, after all its exams are classified)
```bash
python3 _자동관리/tools/classify.py check <과목>          # table of lecture × year; must be [OK]
python3 _자동관리/tools/build_lectures.py <과목>          # all lecture PDFs + 00_전체 + README 목차·분류 결과
```
The README also gets a `## 수업별 분류 결과` section: for every lecture, which exam and which
original question numbers went into it (e.g. `- 2025년 시험: 74, 77, 81번`). Keep it — the user asked
for it (2026-11-17). README only (no PDFs): `python3 _자동관리/tools/build_lectures.py <과목> --readme-only`.
It must end with both `[OK]` lines (question count reconciles; fonts / numbers /
answer-leak scan pass for every PDF). Then look at pages: `work/_lectures/<과목>/<id>/pv/`
— at least the lectures that received questions this session and the first pages of
`00/pv/`. Check year headers, that no question is split oddly, figures are legible.

## 3b. 정답·해설판 (per subject, after stage 3)
The question-only PDFs in `문제지/` never show answers (absolute rule 2). The answers live in a
separate edition, `해설지/<과목>/` (same lecture files and question numbers + a green answer box).
```bash
python3 _자동관리/tools/answer_key.py <과목>        # _자동관리/해설/<과목>/<시험id>.json: 정답 from the original's marks,
                                          # 원본 오답노트, and an empty "explanation" for new questions
```
- `answer` = choice numbers read from the original's colour/size marks (regroup-aware). A
  question with no mark is listed as `!! N번(정답 표시 없음)` — look at the original and say so in
  the explanation (do not invent an answer). If the user says the answer is wrong, set
  `"answer": [..], "answer_by": "직접"` in the JSON; `answer_key.py` then keeps it.
- Write `explanation` for every question with an empty one (Korean, 2–5 sentences: why the answer
  is right, why the main distractors are wrong; for figure questions look at `work/<id>/fig/`).
  Identical questions repeated across years get the same text (check that the choice order and
  answer really match first). If the marked answer looks wrong or the question is broken, still
  explain the marked answer and add a line starting `※ 확인 필요(<이유>):` — README lists these
  with the reason. 이유는 짧은 꼬리표로: `원본 정답 오류`, `원본 정답 오류 의심`, `복수 정답 가능`,
  `원본 문제 결함`, `문제 수치 불일치`, `원본 정답 의심 — 강의 내용과 어긋남` 등. 뒤 문장에 무엇이 왜
  의심스러운지와 그래도 시험에서 어떻게 할지를 쓴다. 답은 맞는데 교과서·지침에 따라 갈리는 점은
  확인 필요가 아니라 `참고: …` 로 덧붙인다(사용자 요청 2026-11-17: 확인 필요는 정말 의문인 것만).
  Figure questions: always open the figure (`work/<id>/fig/`; re-run `extract.py` from `_자동관리/원본/` if
  `work/` is gone) — never write "그림을 확인할 것" without having looked. Check doubtful answers
  against the 필기본 (`_자동관리/tools/notes_lookup.py`) and cite the lecture/page when it settles the point.
  `answer_key.py` never overwrites an explanation, so re-running it is safe.
```bash
python3 _자동관리/tools/build_answers.py <과목>     # 해설지/<과목>/: lecture PDFs, 00_전체, 시험별/, README
```
It must end `[OK] 모든 정답·해설 PDF 검증` and `해설이 비어 있는 문항: 0`. Look at a few pages in
`work/_answers/<과목>/<id>/pv/` (answer box under each question, green choice highlighted).

## 4. Save
```bash
git mv 올리기/<과목>/<시험id>.pdf _자동관리/원본/<과목>/     # originals move once processed
python3 _자동관리/tools/classify.py auto <과목> <시험id>     # refreshes the stored source path (decisions kept)
python3 _자동관리/tools/check_private.py && git add _자동관리 문제지 해설지 && git commit -m "<과목>: <시험id> 분류 및 수업별 문제지"
git push
```
PDFs are reproducible (same input → byte-identical file), so rebuilding unchanged lectures adds
nothing to the commit.

### GitHub Actions (`.github/workflows/build-pdfs.yml`)
On every push to `main` that touches _자동관리/분류/해설/원본/작업기록/과목정보/fonts/the build scripts, GitHub
rebuilds `문제지/` and `해설지/` for every classified subject and commits changed PDFs back (it stops
if the repo is public). The user can also run it by hand: Actions → "문제지·해설지 PDF 만들기" →
Run workflow. So small fixes (an explanation, an answer, a lecture move in the JSON) can be made
on GitHub's web editor without a Claude session. The runner pins the same package versions as
`_자동관리/tools/setup.sh` installs; if you upgrade a package locally, update the pins there too.
One commit per exam is fine; push to `main` when allowed, otherwise push the branch, open a PR,
and tell the user to press the green Merge button. Never commit `work/` or fonts outside `_자동관리/fonts/`.

## 5. Report (short, per exam, in Korean)
- 문항 수, 자동 분류 N / 내용으로 정한 것 M (각각 번호 → 수업, 근거 한 줄) / 기타(99)
- gichul-strip report: (1) 고친 것 (2) 원문 그대로 두고 알려만 두는 것
- **분류 결과 (항상 보여 준다, 사용자 요청 2026-11-17)**: 이번에 분류한 시험마다 수업별로 어느 문항이
  들어갔는지 — `01 세균감염의 치료와 예방: 74, 77, 81번` 처럼 수업 순서대로 한 줄씩 (원래 시험지 번호).
  Mention that `문제지/<과목>/README.md` 「수업별 분류 결과」 has the same list for every year.
- 새로 문항이 들어간 수업 목록, and `문제지/<과목>/README.md` has the full table

## Other requests
- **"12번은 ○○ 수업이야"** → `classify.py set <과목> <시험id> 12=<id> --by 직접`, rebuild with
  `build_lectures.py <과목>` and `build_answers.py <과목>`, commit.
- **"두 수업 합쳐줘" / "이름 바꿔줘" / "바뀐 파일은 (수정) 붙여줘"** → edit `_자동관리/과목정보/<과목>.json`, never the
  school's `name`: `"show_name"` (name used in PDFs/files), `"merged_into": "<id>"` on the absorbed
  lecture (it keeps its id so numbers don't shift, gets no file, `classify.py` refuses it and
  `auto` skips it; README shows "합친 수업"), and subject-level `"file_marks": {"34": "(수정)",
  "00": "(수정)"}` (suffix at the end of that lecture's file names; "00" = the 전체 book). Then
  `classify.py set … --by 직접` the moved questions, rebuild both editions, commit. Old file names
  are deleted by the builds. `make_subject_info.py` keeps these fields when it is re-run. When the
  user later asks to drop or move the marks, change `file_marks` only.
- **"이 해설 틀렸어 / 고쳐줘"** → edit `explanation` in `_자동관리/해설/<과목>/<시험id>.json` (every year that
  has the same question), `build_answers.py <과목> --only <수업id>`, commit. Wrong answer key →
  `"answer_by": "직접"` as above, and fix the explanation too.
- **New subject / new year's lecture list** → user uploads the new 3개년 비교 HTML to `_자동관리/과목정보/`;
  run `python3 _자동관리/tools/make_subject_info.py _자동관리/과목정보/<파일>.html`. Existing lecture ids are kept
  when the lecture name is unchanged; report any lecture whose name changed (its id changes,
  so existing classifications pointing to it need `set` again — `classify.py check` finds them).
- **Screenshots instead of a PDF** → not supported by this pipeline yet (no parsed.json);
  tell the user and suggest a PDF, or offer the account-level exam-worksheet-pdf for a
  one-off worksheet.
