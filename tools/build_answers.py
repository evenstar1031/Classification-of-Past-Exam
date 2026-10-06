#!/usr/bin/env python3
"""정답·해설판 PDF 만들기 (문제지 PDF와 같은 문항 + 문항마다 정답·해설 상자).

usage: python3 tools/build_answers.py <과목> [--only 09 11] [--no-exams]

입력: 분류/<과목>/*.json, 해설/<과목>/<시험id>.json (tools/answer_key.py + 해설 작성),
      과목정보/<과목>.json, work/<시험id>/ (없으면 원본에서 다시 만든다)
출력: 해설지/<과목>/<수업id>_<수업명>_정답해설.pdf   수업마다 한 파일 (문제지와 같은 순서·번호)
      해설지/<과목>/00_전체_수업순_정답해설.pdf
      해설지/<과목>/시험별/<시험명>_정답해설.pdf     시험 통째 (원래 문항 번호)
      해설지/<과목>/README.md

문제지/ 의 문제만 있는 PDF는 건드리지 않는다.
"""
import argparse, glob, html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_lectures as BL  # noqa: E402
B = BL.B

OK = '#0b6e4f'
CIRCLE = B.CIRCLE
ANS_CSS = f"""
ol.ch li.ok {{ color:{OK}; font-weight:bold; }}
.cell.ok .gcap {{ color:{OK}; font-weight:bold; }}
.ans {{ border-left:{B.pt(2.2)} solid {OK}; background:#f1f7f4; padding:{B.mm(2.0)} {B.mm(3.0)};
        margin:{B.mm(2.0)} 0 0 {B.mm(7.6)}; page-break-inside:avoid; }}
.ans p {{ font-size:{B.pt(10.5)}; margin:0; text-align:justify; color:#222; line-height:1.5; }}
.ans p + p {{ margin-top:{B.mm(1.2)}; }}
.ans .al {{ font-size:{B.pt(11)}; font-weight:bold; color:{OK}; }}
.ans .sn {{ margin-top:{B.mm(1.6)}; padding-top:{B.mm(1.2)}; border-top:0.4pt dashed #9bbfae; }}
.ans .snh {{ font-size:{B.pt(9)}; color:#5a7d6c; font-weight:bold; }}
.ans .sn p {{ font-size:{B.pt(9.5)}; color:#444; }}
.ans .none {{ color:#888; }}
"""


def esc_lines(s):
    return '<br>'.join(html.escape(x) for x in s.split('\n'))


def answer_label(e):
    if e.get('answer'):
        return ', '.join(CIRCLE[a - 1] for a in e['answer'])
    if e.get('answer_text'):
        return html.escape(e['answer_text'])
    return '<span class="none">원본에 정답 표시 없음</span>'


def answer_box(e):
    parts = [f'<p class="al">정답 {answer_label(e)}</p>']
    if e.get('explanation'):
        parts.append(f'<p class="ex">{B.text(e["explanation"]).replace(chr(10), "<br>")}</p>')
    else:
        parts.append('<p class="ex none">(해설 준비 중)</p>')
    if e.get('source_note'):
        parts.append(f'<div class="sn"><p class="snh">원본 오답노트</p><p>{esc_lines(e["source_note"])}</p></div>')
    return '<div class="ans">' + ''.join(parts) + '</div>'


def with_answer(qhtml, e):
    """mark the correct choices and append the answer box inside the question div."""
    ans = set(e.get('answer') or [])
    if ans:
        k = 0

        def li(m):
            nonlocal k
            k += 1
            return '<li class="ok">' if k in ans else m.group(0)
        def cell(m):
            nonlocal k
            k += 1
            return '<div class="cell ok">' if k in ans else m.group(0)
        if '<ol class="ch">' in qhtml:
            head, _, tail = qhtml.partition('<ol class="ch">')
            qhtml = head + '<ol class="ch">' + re.sub(r'<li>', li, tail)
        else:
            qhtml = re.sub(r'<div class="cell">', cell, qhtml)
    assert qhtml.endswith('</div></div>'), qhtml[-60:]
    return qhtml[:-len('</div></div>')] + answer_box(e) + '</div></div>'


def page_doc(body):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{B.CSS}{BL.EXTRA_CSS}{ANS_CSS}</style>'
            f'</head><body>{body}</body></html>')


def verify(out, numbers, n_answers, work):
    """fonts, every question number, and one 정답 box per question (+ previews in work/pv)."""
    import pymupdf
    d = pymupdf.open(out)
    pv = os.path.join(work, 'pv'); os.makedirs(pv, exist_ok=True)
    for f_ in os.listdir(pv):
        os.remove(os.path.join(pv, f_))
    for i, p in enumerate(d):
        p.get_pixmap(dpi=96).save(os.path.join(pv, f'{i + 1:03d}.png'))
    txt = '\n'.join(p.get_text() for p in d)
    fonts = sorted({f[3].split('+')[-1] for p in d for f in p.get_fonts()})
    found = {int(x) for x in re.findall(r'^(\d{1,3})\.\s', txt, re.M)}
    missing = sorted(set(numbers) - found)
    boxes = len(re.findall(r'^정답 ', txt, re.M))
    ok_f = B.FAMILY + '-Bold' in fonts and B.FAMILY + '-Regular' in fonts
    print(f"[{'OK' if ok_f else 'FAIL'}] text layer fonts: {fonts}")
    print(f"[{'OK' if not missing else 'FAIL'}] question numbers: {len(found)} (missing {missing})")
    print(f"[{'OK' if boxes == n_answers else 'FAIL'}] 정답 상자 {boxes} / 문항 {n_answers}")
    return ok_f and not missing and boxes == n_answers


def load_answers(subj, ex_id):
    p = os.path.join(ROOT, '해설', subj, f'{ex_id}.json')
    if not os.path.exists(p):
        sys.exit(f'!! {p} 가 없습니다. 먼저 python3 tools/answer_key.py {subj} 를 돌리세요.')
    return json.load(open(p, encoding='utf-8'))['questions']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('subject'); ap.add_argument('--only', nargs='*'); ap.add_argument('--no-exams', action='store_true')
    a = ap.parse_args()
    inf = json.load(open(os.path.join(ROOT, '과목정보', f'{a.subject}.json'), encoding='utf-8'))
    L = {x['id']: x for x in inf['lectures']}; L['99'] = BL.OTHER
    files = sorted(glob.glob(os.path.join(ROOT, '분류', a.subject, '*.json')))
    if not files:
        sys.exit(f'분류/{a.subject}/ 에 분류된 시험이 없습니다.')
    groups, exams, total, no_ex = {}, [], 0, 0
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        ex = d['exam']; ex['_work'] = BL.ensure_work(a.subject, ex)
        ans = load_answers(a.subject, ex['id'])
        parsed = {str(q['n']): q for q in json.load(open(os.path.join(ex['_work'], 'parsed.json'), encoding='utf-8'))}
        exams.append((ex, parsed, ans))
        for n, e in d['questions'].items():
            lid = e.get('lecture') if e.get('lecture') in L else '99'
            if n not in ans:
                sys.exit(f'!! 해설/{a.subject}/{ex["id"]}.json 에 {n}번이 없습니다. answer_key.py 를 다시 돌리세요.')
            groups.setdefault(lid, []).append((ex, parsed[n], e, ans[n])); total += 1
            no_ex += not ans[n].get('explanation')
    for lid in groups:
        groups[lid].sort(key=lambda t: (-t[0]['year'], -(int(re.sub(r'\D', '', t[0].get('date') or '0') or 0)),
                                        t[0]['id'], t[1]['n']))
    outdir = os.path.join(ROOT, '해설지', a.subject)
    os.makedirs(os.path.join(outdir, '시험별'), exist_ok=True)
    B.IMG_ABS = True
    ok = True

    def section(lid, items):
        Lx = L[lid]
        out, nums, cur_year, k, years = [], [], None, 0, []
        for ex, q, e, an in items:
            if ex['year'] not in years:
                years.append(ex['year'])
        out.append(f'<h1>{html.escape(Lx["id"])}. {html.escape(Lx["name"])}</h1>'
                   f'<div class="sub">{html.escape(inf["name"])} · {", ".join(str(y) for y in years)}년 기출 · '
                   f'총 {len(items)}문항 · 정답·해설판</div>')
        for ex, q, e, an in items:
            new_year = ex['year'] != cur_year
            if new_year:
                cur_year = ex['year']
                profs = ', '.join(Lx.get('profs', {}).get(str(cur_year), [])) if 'profs' in Lx else ''
                out.append(f'<h2 class="yr">{cur_year}년 <span>{html.escape("담당 " + profs if profs else "")}</span></h2>')
            k += 1; nums.append(k)
            B.load(ex['_work'])
            by = f"{ex['year']}년 시험 {q['n']}번" + (f" · 출제자 {e['author']}" if e.get('author') else '')
            qh = B.build_q(q, disp=k, byline_text=by)
            if new_year and qh.startswith('<div class="q flow'):
                qh = qh.replace('">', '" style="page-break-before:auto">', 1)
                if len(out) > 2:
                    out[-1] = out[-1].replace('<h2 class="yr">', '<h2 class="yr" style="page-break-before:always">', 1)
            out.append(with_answer(qh, an))
        return '\n'.join(out), nums

    order = [x['id'] for x in inf['lectures']] + ['99']
    sections, made = [], set()
    for lid in order:
        if lid not in groups:
            continue
        body, nums = section(lid, groups[lid])
        sections.append((lid, body, nums))
        if a.only and lid not in a.only:
            continue
        name = f"{lid}_{BL.safe(L[lid]['name'])}_정답해설.pdf"
        work = os.path.join(ROOT, 'work', '_answers', a.subject, lid); os.makedirs(work, exist_ok=True)
        out = os.path.join(outdir, name)
        print(f'\n== {name}  ({len(nums)}문항)')
        B.render_pdf(page_doc(body), work, out, f"{inf['name']} {L[lid]['name']} 정답·해설")
        ok &= verify(out, nums, len(nums), work); made.add(name)

    if not a.only:
        body = '\n'.join(f'<div class="lect">{b}</div>' for _, b, _ in sections)
        work = os.path.join(ROOT, 'work', '_answers', a.subject, '00'); os.makedirs(work, exist_ok=True)
        out = os.path.join(outdir, '00_전체_수업순_정답해설.pdf')
        print(f'\n== 00_전체_수업순_정답해설.pdf  ({total}문항)')
        B.render_pdf(page_doc(body), work, out, f"{inf['name']} 수업별 기출 정답·해설 전체")
        ok &= verify(out, [], total, work)
        for f in glob.glob(os.path.join(outdir, '[0-9][0-9]_*_정답해설.pdf')):
            b = os.path.basename(f)
            if b != '00_전체_수업순_정답해설.pdf' and b not in made:
                os.remove(f); print(f'  옛 파일 삭제: {b}')

    if not a.no_exams and not a.only:
        for ex, parsed, ans in exams:
            B.load(ex['_work'])
            title = ex.get('title') or ex['id']
            body = (f'<h1>{html.escape(title)}</h1><div class="sub">시험일 : {html.escape(ex.get("date") or "")} · '
                    f'총 {len(parsed)}문항 · 정답·해설판</div>'
                    + '\n'.join(with_answer(B.build_q(q), ans[str(q['n'])]) for q in B.P))
            work = os.path.join(ROOT, 'work', '_answers', a.subject, 'exam_' + ex['id']); os.makedirs(work, exist_ok=True)
            out = os.path.join(outdir, '시험별', f"{title.replace(' ', '_')}_정답해설.pdf")
            print(f'\n== 시험별/{os.path.basename(out)}  ({len(B.P)}문항)')
            B.render_pdf(page_doc(body), work, out, f'{title} 정답·해설')
            ok &= verify(out, [q['n'] for q in B.P], len(B.P), work)

    years = sorted({t[0]['year'] for v in groups.values() for t in v}, reverse=True)
    lines = [f"# {inf['name']} — 수업별 기출 정답·해설", '',
             f"시험 {len(files)}개 · 총 {total}문항 · 한 권으로 보기: "
             f"[00_전체_수업순_정답해설.pdf](00_%EC%A0%84%EC%B2%B4_%EC%88%98%EC%97%85%EC%88%9C_%EC%A0%95%EB%8B%B5%ED%95%B4%EC%84%A4.pdf)", '',
             '- 정답: 원본 기출에 표시된 정답 그대로 (정답 보기는 초록색으로 표시)',
             '- 해설: Claude가 작성 · 원본에 오답노트가 있던 문항은 "원본 오답노트"를 함께 실음',
             '- 해설은 공부를 돕기 위한 것이라 틀릴 수 있습니다. 이상한 해설은 알려 주세요.',
             '- 해설에 "※ 확인 필요"가 붙은 문항은 원본 정답이나 문제 자체에 의문이 있는 문항입니다 (아래 목록).',
             '- 문제만 있는 PDF는 `문제지/` 폴더에 그대로 있습니다.', '',
             '| 수업 | ' + ' | '.join(str(y) for y in years) + ' | 합계 |', '|---|' + '---:|' * (len(years) + 1)]
    import urllib.parse
    for lid in order:
        if lid not in groups:
            continue
        cnt = {}
        for t in groups[lid]:
            cnt[t[0]['year']] = cnt.get(t[0]['year'], 0) + 1
        fn = f"{lid}_{BL.safe(L[lid]['name'])}_정답해설.pdf"
        lines.append(f"| [{lid}. {L[lid]['name']}]({urllib.parse.quote(fn)}) | "
                     + ' | '.join(str(cnt.get(y, '')) for y in years) + f' | {sum(cnt.values())} |')
    doubt = [(ex['year'], q['n'], lid, an) for lid in order for ex, q, e, an in groups.get(lid, [])
             if '확인 필요' in (an.get('explanation') or '') or not (an.get('answer') or an.get('answer_text'))]
    if doubt:
        lines += ['', '## 확인이 필요한 문항', '']
        for y, n, lid, an in sorted(doubt, key=lambda t: (-t[0], t[1])):
            why = '원본에 정답 표시 없음' if not (an.get('answer') or an.get('answer_text')) else '원본 정답·문제에 의문'
            lines.append(f"- {y}년 {n}번 ({lid}. {L[lid]['name']}) — {why}")
    open(os.path.join(outdir, 'README.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    print(f"\n[{'OK' if ok else 'FAIL'}] 모든 정답·해설 PDF 검증 (폰트·문항번호·정답 상자)")
    print(f"[{'OK' if no_ex == 0 else 'WARN'}] 해설이 비어 있는 문항: {no_ex}")
    print(f'목차: 해설지/{a.subject}/README.md')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
