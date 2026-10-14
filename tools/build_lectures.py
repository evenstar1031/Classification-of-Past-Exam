#!/usr/bin/env python3
"""분류 결과로 수업별 문제지 PDF 만들기.

usage: python3 tools/build_lectures.py <과목> [--only 09 11] [--allow-missing]

입력: 분류/<과목>/*.json, 과목정보/<과목>.json,
      work/<시험id>/ (없으면 원본 PDF에서 extract 를 다시 돌리고 작업기록의 fixes.json 을 씌움)
출력: 문제지/<과목>/<수업id>_<수업명>.pdf   수업마다 한 파일, 최신 연도부터
      문제지/<과목>/00_전체_수업순.pdf        모든 수업을 한 파일로 (수업마다 새 페이지)
      문제지/<과목>/README.md                수업 × 연도 문항 수 표 (GitHub 폴더 화면에 보임)

과목정보에서 읽는 표시용 설정 (없으면 무시):
  수업 "show_name"   파일·제목에 쓰는 이름 (학교 수업명 "name" 은 그대로 두어 make_subject_info 와 맞춤)
  수업 "merged_into" 다른 수업에 합쳐진 수업 — 문항을 받지 않고 README 에 "→ 합침" 으로만 표시
  과목 "file_marks"  {"34": "(수정)", "00": "(수정)"} 처럼 파일 이름 끝에 붙일 표시 ("00" = 전체 한 권)
"""
import argparse, glob, html, json, os, re, shutil, subprocess, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, '.claude', 'skills', 'gichul-strip', 'scripts')
sys.path.insert(0, S)
import build as B  # noqa: E402

OTHER = {'id': '99', 'name': '기타 (수업 특정 불가)'}
EXTRA_CSS = f"""
h2.yr {{ font-size:{B.pt(13)}; font-weight:bold; color:#1a4f8a; border-bottom:0.6pt solid #1a4f8a;
         margin:{B.mm(4)} 0 {B.mm(4)} 0; padding-bottom:{B.mm(0.8)}; page-break-after:avoid; }}
h2.yr span {{ font-size:{B.pt(9)}; font-weight:normal; color:#777; }}
.lect {{ page-break-before:always; }}
.lect:first-of-type {{ page-break-before:auto; }}
"""


def lname(L):
    """수업 표시 이름 (show_name 이 있으면 그것)."""
    return L.get('show_name') or L['name']


def fmark(inf, lid):
    """파일 이름 끝에 붙일 표시, 예: '(수정)'."""
    return (inf.get('file_marks') or {}).get(lid, '')


def all_name(inf, tail=''):
    return f"00_전체_수업순{tail}{fmark(inf, '00')}.pdf"


def lect_file(inf, L, tail=''):
    return f"{L['id']}_{safe(lname(L))}{tail}{fmark(inf, L['id'])}.pdf"


def mark_exam_labels(exams):
    """Set ex['_label'] used in bylines: '2025년 시험', or '2023년 9월 18일 시험' when the
    subject has more than one exam in that year (e.g. 230911 and 230918)."""
    per_year = {}
    for ex in exams:
        per_year[ex['year']] = per_year.get(ex['year'], 0) + 1
    for ex in exams:
        m = re.match(r'\d{4}-(\d{2})-(\d{2})', ex.get('date') or '')
        if per_year[ex['year']] > 1 and m:
            ex['_label'] = f"{ex['year']}년 {int(m.group(1))}월 {int(m.group(2))}일 시험"
        else:
            ex['_label'] = f"{ex['year']}년 시험"


def safe(name):
    s = re.sub(r'\s*/\s*', '·', name)
    s = re.sub(r'[\\:*?"<>|]', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def ensure_work(subj, ex):
    """work/<시험id> 가 없으면 원본에서 다시 만든다 (클라우드 세션은 매번 새로 시작하므로)."""
    work = os.path.join(ROOT, 'work', ex['id'])
    rec = os.path.join(ROOT, '작업기록', subj, ex['id'], 'fixes.json')
    src = os.path.join(ROOT, ex['source'])
    if not os.path.exists(src):   # 올리기/ → 원본/<과목>/ 으로 옮겨진 경우
        alt = os.path.join(ROOT, '원본', subj, os.path.basename(ex['source']))
        if os.path.exists(alt):
            src = alt
    if not os.path.exists(os.path.join(work, 'parsed.json')):
        if not os.path.exists(src):
            sys.exit(f"!! {ex['id']}: 원본 {ex['source']} 도, 작업 폴더도 없습니다.")
        print(f"  {ex['id']}: 작업 폴더 재생성 (extract)")
        r = subprocess.run([sys.executable, os.path.join(S, 'extract.py'), src, work], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout[-2000:] + r.stderr[-2000:])
        if os.path.exists(rec):
            shutil.copy(rec, os.path.join(work, 'fixes.json'))
        else:
            print(f"  !! {ex['id']}: 작업기록/…/fixes.json 이 없어 띄어쓰기·오타 수정 없이 만듭니다.")
    # 원본이 올리기/ → 원본/ 으로 옮겨졌으면 meta 의 경로도 맞춰 둔다 (extra_figs 가 원본을 다시 읽음)
    mp = os.path.join(work, 'meta.json')
    meta = json.load(open(mp, encoding='utf-8'))
    if not os.path.exists(meta.get('source', '')) and os.path.exists(src):
        meta['source'] = src
        json.dump(meta, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return work


def section_html(L, items, subj_name, title_tag='h1'):
    """items: [(exam, q, entry)] already sorted. Returns (html, numbers)."""
    out, nums, cur_year, k = [], [], None, 0
    years = []
    for ex, q, e in items:
        if ex['year'] not in years:
            years.append(ex['year'])
    head = (f'<{title_tag}>{html.escape(L["id"])}. {html.escape(lname(L))}</{title_tag}>'
            f'<div class="sub">{html.escape(subj_name)} · {", ".join(str(y) for y in years)}년 기출 · '
            f'총 {len(items)}문항 · 문제만 수록 (정답 표시 없음)</div>')
    out.append(head)
    for ex, q, e in items:
        new_year = ex['year'] != cur_year
        if new_year:
            cur_year = ex['year']
            profs = ', '.join(L.get('profs', {}).get(str(cur_year), [])) if 'profs' in L else ''
            extra = f'담당 {profs}' if profs else ''
            out.append(f'<h2 class="yr">{cur_year}년 <span>{html.escape(extra)}</span></h2>')
        k += 1; nums.append(k)
        B.load(ex['_work'])
        by = f"{ex.get('_label') or str(ex['year']) + '년 시험'} {q['n']}번"
        if e.get('author'):
            by += f" · 출제자 {e['author']}"
        qh = B.build_q(q, disp=k, byline_text=by)
        if new_year and qh.startswith('<div class="q flow'):
            # image-choice grids start a new page; take the year header along instead of
            # stranding it (the first year of a lecture stays under the lecture title)
            qh = qh.replace('">', '" style="page-break-before:auto">', 1)
            if len(out) > 2:
                out[-1] = out[-1].replace('<h2 class="yr">', '<h2 class="yr" style="page-break-before:always">', 1)
        out.append(qh)
    return '\n'.join(out), nums


def page_doc(body):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{B.CSS}{EXTRA_CSS}</style></head>'
            f'<body>{body}</body></html>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('subject'); ap.add_argument('--only', nargs='*'); ap.add_argument('--allow-missing', action='store_true')
    a = ap.parse_args()
    inf = json.load(open(os.path.join(ROOT, '과목정보', f'{a.subject}.json'), encoding='utf-8'))
    L = {x['id']: x for x in inf['lectures']}; L['99'] = OTHER
    files = sorted(glob.glob(os.path.join(ROOT, '분류', a.subject, '*.json')))
    if not files:
        sys.exit(f'분류/{a.subject}/ 에 분류된 시험이 없습니다.')

    groups, missing, total = {}, [], 0
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        ex = d['exam']; ex['_work'] = ensure_work(a.subject, ex)
        parsed = {str(q['n']): q for q in json.load(open(os.path.join(ex['_work'], 'parsed.json'), encoding='utf-8'))}
        for n, e in d['questions'].items():
            lid = e.get('lecture')
            if not lid or lid not in L:
                if not a.allow_missing:
                    missing.append(f"{ex['id']} {n}번"); continue
                lid = '99'
            if n not in parsed:
                sys.exit(f"!! {ex['id']} {n}번이 parsed.json 에 없습니다 (분류 파일과 원본이 안 맞음).")
            groups.setdefault(lid, []).append((ex, parsed[n], e)); total += 1
    mark_exam_labels({id(t[0]): t[0] for v in groups.values() for t in v}.values())
    if missing:
        sys.exit(f'!! 수업이 정해지지 않은 문항 {len(missing)}개: {missing}\n'
                 f'   classify.py show 로 확인 후 set 하거나, --allow-missing 으로 "99 기타"에 넣으세요.')

    for lid in groups:
        groups[lid].sort(key=lambda t: (-t[0]['year'], -(int(re.sub(r'\D', '', t[0].get('date') or '0') or 0)),
                                        t[0]['id'], t[1]['n']))
    outdir = os.path.join(ROOT, '문제지', a.subject)
    os.makedirs(outdir, exist_ok=True)
    B.IMG_ABS = True
    order = [x['id'] for x in inf['lectures']] + ['99']
    todo = [lid for lid in order if lid in groups and (not a.only or lid in a.only)]
    made, all_ok, sections = set(), True, []
    for lid in order:
        if lid not in groups:
            continue
        body, nums = section_html(L[lid], groups[lid], inf['name'])
        sections.append((lid, body, nums))
        if lid not in todo:
            continue
        name = lect_file(inf, L[lid])
        work = os.path.join(ROOT, 'work', '_lectures', a.subject, lid)
        os.makedirs(work, exist_ok=True)
        doc = page_doc(body)
        out = os.path.join(outdir, name)
        print(f'\n== {name}  ({len(nums)}문항)')
        tot = B.render_pdf(doc, work, out, f"{inf['name']} {lname(L[lid])}")
        all_ok &= bool(B.verify(doc, work, out, tot, nums, report_fixes=False))
        made.add(name)

    # 전체 한 권 (수업마다 새 페이지)
    if not a.only:
        body = '\n'.join(f'<div class="lect">{b}</div>' for _, b, _ in sections)
        work = os.path.join(ROOT, 'work', '_lectures', a.subject, '00')
        os.makedirs(work, exist_ok=True)
        doc = page_doc(body)
        out = os.path.join(outdir, all_name(inf))
        print(f'\n== {all_name(inf)}  ({total}문항)')
        tot = B.render_pdf(doc, work, out, f"{inf['name']} 수업별 기출 전체")
        all_ok &= bool(B.verify(doc, work, out, tot, [], report_fixes=False))
        # 수업이 바뀌어 더는 문항이 없는 옛 PDF 정리
        for f in glob.glob(os.path.join(outdir, '[0-9][0-9]_*.pdf')):
            b = os.path.basename(f)
            if b != all_name(inf) and b not in made:
                os.remove(f); print(f'  옛 파일 삭제: {b}')

    # README 목차
    years = sorted({t[0]['year'] for v in groups.values() for t in v}, reverse=True)
    lines = [f"# {inf['name']} — 수업별 기출", '',
             f"시험 {len(files)}개 · 총 {total}문항 · 한 권으로 보기: [{all_name(inf)}]({urllib.parse.quote(all_name(inf))})", '',
             '| 수업 | ' + ' | '.join(f'{y}' for y in years) + ' | 합계 |',
             '|---|' + '---:|' * (len(years) + 1)]
    for lid in order:
        if lid not in groups:
            continue
        cnt = {}
        for ex, _, _ in groups[lid]:
            cnt[ex['year']] = cnt.get(ex['year'], 0) + 1
        fn = lect_file(inf, L[lid])
        link = f"[{lid}. {lname(L[lid])}]({urllib.parse.quote(fn)})"
        lines.append(f'| {link} | ' + ' | '.join(str(cnt.get(y, '')) for y in years) + f' | {sum(cnt.values())} |')
    none = [x for x in inf['lectures'] if x['id'] not in groups and x.get('exam', True) and not x.get('merged_into')]
    if none:
        lines += ['', '아직 기출이 없는 수업: ' + ', '.join(f"{x['id']} {lname(x)}" for x in none)]
    merged = [x for x in inf['lectures'] if x.get('merged_into')]
    if merged:
        lines += ['', '합친 수업: ' + ', '.join(f"{x['id']} {x['name']} → {x['merged_into']} {lname(L[x['merged_into']])}"
                                            for x in merged)]
    open(os.path.join(outdir, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    counted = sum(len(n) for _, _, n in sections)
    print(f"\n[{'OK' if counted == total else 'FAIL'}] 분류된 문항 {total}개 = 수업별 PDF 문항 합계 {counted}개")
    print(f"[{'OK' if all_ok else 'FAIL'}] 모든 PDF 검증 (폰트·문항번호·정답 유출)")
    print(f'목차: 문제지/{a.subject}/README.md')
    sys.exit(0 if all_ok and counted == total else 1)


if __name__ == '__main__':
    main()
