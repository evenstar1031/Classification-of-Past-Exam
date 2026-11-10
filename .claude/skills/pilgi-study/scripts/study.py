#!/usr/bin/env python3
"""필기본 → 수업별 학습자료 PDF (1부 설명 · 2부 기출 · 3부 연습문제).

usage (저장소 맨 위 폴더에서):
  python3 .claude/skills/pilgi-study/scripts/study.py find   <과목> [검색어]   수업 id 찾기 + 기출 문항 수
  python3 .claude/skills/pilgi-study/scripts/study.py gichul <과목> <수업>     그 수업 기출을 글로 출력 (정답·해설 포함)
  python3 .claude/skills/pilgi-study/scripts/study.py build  <과목> <수업>     PDF 만들기

<수업> = 수업 id(예: 32) 또는 이름 일부(예: 응급기도). 다른 수업에 합쳐진 수업이면 합쳐진 쪽으로 간다.

입력 (Claude 가 쓴다):  학습자료/<과목>/<id>_<수업명>/1_설명.md        1부 (Markdown)
                       학습자료/<과목>/<id>_<수업명>/3_연습문제.json   3부
기출 (자동):           분류/<과목>/*.json 에서 그 수업 문항 + 해설/<과목>/<시험id>.json 의 정답·해설
출력:                  학습자료/<과목>/<id>_<수업명>_학습자료.pdf

글씨체: 본문 StudyBatang(KoPubWorld 바탕, scripts/setup_fonts.py), 제목·문항 GichulTT(저장소 fonts/ =
문제지와 같은 Apple SD 산돌고딕 Neo). 기출 문항은 문제지/ 의 수업별 PDF와 똑같은 코드(build_q)로 그린다.
"""
import argparse, glob, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_lectures as BL  # noqa: E402
B = BL.B

CIRCLE = B.CIRCLE
GOTHIC = f"'{B.FAMILY}',sans-serif"
BATANG = "'StudyBatang',serif"
INK = '#1d2b3a'
ACC = '#2c5d8f'       # 제목 색 — 문항 번호색(#1a4f8a)과 달라야 page-break 검사가 헷갈리지 않는다
OK = '#0b6e4f'
pt, mm = B.pt, B.mm


# ------------------------------------------------------------------ lookup
def load_info(subj):
    p = os.path.join(ROOT, '과목정보', f'{subj}.json')
    if not os.path.exists(p):
        have = ', '.join(os.path.splitext(os.path.basename(x))[0] for x in sorted(glob.glob(os.path.join(ROOT, '과목정보', '*.json'))))
        sys.exit(f'!! 과목정보/{subj}.json 이 없습니다. 있는 과목: {have}')
    return json.load(open(p, encoding='utf-8'))


def norm(s):
    return re.sub(r'[\s·/,()\-]', '', s).lower()


def find_lecture(inf, key):
    L = {x['id']: x for x in inf['lectures']}
    k = key.strip()
    if k.isdigit():
        k = f'{int(k):02d}'
    hit = [L[k]] if k in L else [x for x in inf['lectures']
                                 if norm(key) in norm(x['name']) or norm(key) in norm(BL.lname(x))]
    if len(hit) != 1:
        opts = '\n'.join(f"  {x['id']} {BL.lname(x)}" for x in (hit or inf['lectures']))
        sys.exit(f"!! '{key}' 에 맞는 수업이 {'여러 개' if hit else '없습'}{'입니다' if hit else '니다'}:\n{opts}")
    x = hit[0]
    if x.get('merged_into'):
        print(f"  ({x['id']} {x['name']} 은 {x['merged_into']} 에 합쳐져 있어 그쪽으로 만듭니다)")
        x = L[x['merged_into']]
    return x


def collect(subj, inf, lid):
    """[(exam, parsed_q, class_entry, answer_entry)] of one lecture, newest year first (문제지와 같은 순서)."""
    files = sorted(glob.glob(os.path.join(ROOT, '분류', subj, '*.json')))
    items, exams = [], []
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        ex = d['exam']
        mine = [n for n, e in d['questions'].items() if e.get('lecture') == lid]
        exams.append(ex)
        if not mine:
            continue
        ex['_work'] = BL.ensure_work(subj, ex)
        parsed = {str(q['n']): q for q in json.load(open(os.path.join(ex['_work'], 'parsed.json'), encoding='utf-8'))}
        ap = os.path.join(ROOT, '해설', subj, f"{ex['id']}.json")
        ans = json.load(open(ap, encoding='utf-8'))['questions'] if os.path.exists(ap) else {}
        for n in mine:
            items.append((ex, parsed[n], d['questions'][n], ans.get(n, {})))
    for ex, q, e, an in extra_items(subj, inf, lid):
        exams.append(ex); items.append((ex, q, e, an))
    BL.mark_exam_labels(exams)
    items.sort(key=lambda t: (-t[0]['year'], -(int(re.sub(r'\D', '', t[0].get('date') or '0') or 0)),
                              t[0]['id'], t[1]['n']))
    return items


def extra_items(subj, inf, lid):
    """학습자료/<과목>/<id>_<수업명>/2_추가기출.json — 저장소에 원본 시험이 없어 필기본 등에서 옮겨 적은 기출.
    {"exam": {id, year, date, title}, "questions": [{n, author, stem, box?, choices, answer, explanation}]}
    문제지와 같은 코드(build_q)로 그리도록 work/_study/<과목>/_extra/<id>/ 에 parsed/meta/fixes 를 만든다."""
    L = {x['id']: x for x in inf['lectures']}.get(lid)
    p = L and os.path.join(folder(subj, L), '2_추가기출.json')
    if not p or not os.path.exists(p):
        return []
    d = json.load(open(p, encoding='utf-8'))
    ex = dict(d['exam']); ex['_extra'] = True
    work = os.path.join(ROOT, 'work', '_study', subj, '_extra', ex['id'])
    os.makedirs(os.path.join(work, 'fig'), exist_ok=True)
    parsed, out = [], []
    for q in d['questions']:
        blocks = [{'t': 'text', 'lines': [q['stem']]}]
        if q.get('box'):
            blocks.append({'t': 'box', 'lines': q['box'] if isinstance(q['box'], list) else [q['box']]})
        parsed.append({'n': q['n'], 'blocks': blocks, 'notes': [], 'answer_text': [],
                       'choices': [{'n': f'{i + 1})', 'lines': [c], 'figs': [], 'label': None, 'mk': False,
                                    'mk_num': False, 'mk_lines': []} for i, c in enumerate(q['choices'])]})
    meta = {'title': ex.get('title', ex['id']), 'date': ex.get('date', ''), 'source': p,
            'authors': {str(q['n']): q.get('author') for q in d['questions'] if q.get('author')}}
    for f_, v in (('parsed.json', parsed), ('meta.json', meta), ('fixes.json', {'authors': None})):
        json.dump(v, open(os.path.join(work, f_), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ex['_work'] = work
    for q, pq in zip(d['questions'], parsed):
        e = {'lecture': lid, 'author': q.get('author', '')}
        a_ = q.get('answer')
        an = {'answer': a_ if isinstance(a_, list) else [],          # 단답형: answer 에 글로 쓰면 answer_text 로
              'answer_text': q.get('answer_text') or (a_ if isinstance(a_, str) else ''),
              'explanation': q.get('explanation', '')}
        out.append((ex, pq, e, an))
    return out


def counts(subj):
    c = {}
    for f in glob.glob(os.path.join(ROOT, '분류', subj, '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        for e in d['questions'].values():
            c[e.get('lecture')] = c.get(e.get('lecture'), 0) + 1
    return c


def folder(subj, L):
    return os.path.join(ROOT, '학습자료', subj, f"{L['id']}_{BL.safe(BL.lname(L))}")


def byline(ex, q, e):
    return (f"{ex.get('_label') or str(ex['year']) + '년 시험'} {q['n']}번"
            + (f" · 출제자 {e['author']}" if e.get('author') else '')
            + (' · 필기본 수록' if ex.get('_extra') else ''))


def ans_label(an):
    if an.get('answer'):
        return ', '.join(CIRCLE[a - 1] for a in an['answer'])
    return an.get('answer_text') or '원본에 정답 표시 없음'


# ------------------------------------------------------------------ commands
def cmd_find(a):
    inf = load_info(a.subject)
    c = counts(a.subject)
    if not c:
        print(f'!! 분류/{a.subject}/ 에 분류된 기출이 없습니다 — 기출이 없으면 2부는 비어 있게 됩니다.')
    for x in inf['lectures']:
        if a.key and norm(a.key) not in norm(x['name']) and norm(a.key) not in norm(BL.lname(x)) and a.key != x['id']:
            continue
        extra = f"  → {x['merged_into']} 에 합침" if x.get('merged_into') else ''
        made = os.path.exists(os.path.join(folder(a.subject, x), '1_설명.md'))
        print(f"{x['id']}  {BL.lname(x):28s}  기출 {c.get(x['id'], 0):3d}문항{'  [학습자료 있음]' if made else ''}{extra}")


def plain(h):
    h = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', lambda m: f' [그림: {m.group(1)}] ', h)
    h = re.sub(r'</(p|li|div)>', '\n', h)
    h = re.sub(r'<[^>]+>', '', h)
    h = html.unescape(h)
    return re.sub(r'\n\s*\n+', '\n', re.sub(r'[ \t]+', ' ', h)).strip()


def cmd_gichul(a):
    inf = load_info(a.subject); L = find_lecture(inf, a.lecture)
    items = collect(a.subject, inf, L['id'])
    B.IMG_ABS = True
    print(f"# {L['id']}. {BL.lname(L)} — 기출 {len(items)}문항\n")
    no_ex = []
    for k, (ex, q, e, an) in enumerate(items, 1):
        B.load(ex['_work'])
        print(f"--- [{k}] {byline(ex, q, e)}")
        print(plain(B.build_q(q, disp=k, byline_text='')))
        print(f"정답: {ans_label(an)}")
        print(f"해설: {an.get('explanation') or '(없음)'}\n")
        if not an.get('explanation'):
            no_ex.append(f"해설/{a.subject}/{ex['id']}.json {q['n']}번")
    if no_ex:
        print('!! 해설이 비어 있는 기출 (build 전에 그 JSON 의 "explanation" 을 채울 것):\n  ' + '\n  '.join(no_ex))


# ------------------------------------------------------------------ build
CSS = f"""
body {{ font-family:{BATANG}; color:{INK}; font-size:{pt(10.5)}; line-height:1.62; }}
.q, .q * {{ font-family:{GOTHIC}; }}
.cover {{ text-align:center; padding-top:{mm(38)}; }}
.cover .subj {{ font-family:{GOTHIC}; font-size:{pt(12)}; color:#6b7a89; letter-spacing:{pt(1)}; }}
.cover .title {{ font-family:{GOTHIC}; font-weight:bold; font-size:{pt(28)}; color:{INK}; margin:{mm(4)} 0 {mm(3)} 0; }}
.cover .rule {{ width:{mm(30)}; border-top:{pt(1.6)} solid {ACC}; margin:{mm(5)} auto; }}
.cover .meta {{ font-size:{pt(10.5)}; color:#55606b; }}
.toc {{ margin:{mm(16)} auto 0 auto; width:{mm(110)}; text-align:left; }}
.toc div {{ font-family:{GOTHIC}; font-size:{pt(11.5)}; padding:{mm(2.4)} 0; border-bottom:0.4pt solid #d5dbe1; }}
.toc b {{ color:{ACC}; display:inline-block; width:{mm(14)}; }}
.toc span {{ float:right; color:#8a96a3; font-size:{pt(10)}; }}
.part {{ font-family:{GOTHIC}; margin:0 0 {mm(6)} 0; border-bottom:{pt(1.4)} solid {ACC}; padding-bottom:{mm(2)}; }}
.part .pn {{ font-size:{pt(10)}; color:{ACC}; font-weight:bold; letter-spacing:{pt(1)}; }}
.part .pt {{ font-size:{pt(17)}; font-weight:bold; color:{INK}; }}
.part .ps {{ font-size:{pt(9.5)}; color:#8a96a3; }}
.notes h1 {{ font-family:{GOTHIC}; font-size:{pt(15)}; font-weight:bold; color:{INK}; text-align:left;
             margin:{mm(7)} 0 {mm(3)} 0; padding:{mm(1.4)} 0 {mm(1.4)} {mm(3)}; border-left:{pt(3.2)} solid {ACC};
             background:#eef3f8; page-break-after:avoid; }}
.notes h2 {{ font-family:{GOTHIC}; font-size:{pt(13)}; font-weight:bold; color:{ACC}; margin:{mm(5.5)} 0 {mm(2)} 0;
             page-break-after:avoid; }}
.notes h3 {{ font-family:{GOTHIC}; font-size:{pt(11.2)}; font-weight:bold; color:{INK}; margin:{mm(4)} 0 {mm(1.5)} 0;
             page-break-after:avoid; }}
.notes > h1:first-child {{ margin-top:0; }}
.notes p {{ margin:0 0 {mm(2.2)} 0; text-align:justify; }}
.notes ul, .notes ol {{ margin:0 0 {mm(2.2)} 0; padding-left:{mm(6)}; }}
.notes li {{ margin:0 0 {mm(0.9)} 0; text-align:justify; }}
.notes li > ul, .notes li > ol {{ margin:{mm(0.8)} 0 0 0; }}
.notes strong {{ font-weight:bold; color:#10202f; }}
.notes em {{ font-style:normal; color:{ACC}; font-weight:bold; }}
.notes code {{ font-family:{GOTHIC}; background:#f1f3f5; padding:0 {pt(2)}; }}
.notes table {{ border-collapse:collapse; width:100%; margin:{mm(1)} 0 {mm(3.2)} 0; page-break-inside:avoid;
                font-size:{pt(9.8)}; line-height:1.45; }}
.notes th {{ font-family:{GOTHIC}; font-weight:bold; background:#e4ecf4; color:{INK}; border:0.5pt solid #b9c6d3;
             padding:{mm(1.3)} {mm(1.8)}; text-align:left; }}
.notes td {{ border:0.5pt solid #c9d3dc; padding:{mm(1.3)} {mm(1.8)}; vertical-align:top; }}
.notes tr:nth-child(even) td {{ background:#f7f9fb; }}
.notes hr {{ border:0; border-top:0.5pt dashed #b9c6d3; margin:{mm(4)} 0; }}
h2.yr {{ font-family:{GOTHIC}; }}
.admonition {{ padding:{mm(2.4)} {mm(3.4)}; margin:{mm(1)} 0 {mm(3.4)} 0; page-break-inside:avoid;
               border-left:{pt(3)} solid #8a96a3; background:#f4f6f8; }}
.admonition p {{ margin:0 0 {mm(1.2)} 0; }}
.admonition > :last-child {{ margin-bottom:0; }}
.admonition .admonition-title {{ font-family:{GOTHIC}; font-weight:bold; font-size:{pt(10)}; margin-bottom:{mm(1.2)}; }}
.admonition.key {{ border-color:{ACC}; background:#edf3f9; }}  .admonition.key .admonition-title {{ color:{ACC}; }}
.admonition.exam {{ border-color:#b5542c; background:#fbf1ec; }} .admonition.exam .admonition-title {{ color:#b5542c; }}
.admonition.diff {{ border-color:#7a5aa6; background:#f4f0fa; }} .admonition.diff .admonition-title {{ color:#7a5aa6; }}
.admonition.memo {{ border-color:{OK}; background:#eef6f2; }}   .admonition.memo .admonition-title {{ color:{OK}; }}
.pb {{ page-break-before:always; }}
.empty {{ color:#8a96a3; font-size:{pt(10.5)}; margin:{mm(4)} 0; }}
.ak {{ page-break-inside:avoid; margin:0 0 {mm(3.6)} 0; padding:0 0 {mm(3)} 0; border-bottom:0.4pt solid #e1e6eb; }}
.ak .h {{ font-family:{GOTHIC}; font-size:{pt(11)}; }}
.ak .an {{ font-weight:bold; color:{OK}; margin-right:{mm(1.5)}; }}
.ak .lab {{ font-weight:bold; color:{OK}; }}
.ak .src {{ color:#8a96a3; font-size:{pt(8.5)}; margin-left:{mm(2)}; }}
.ak p {{ margin:{mm(1.2)} 0 0 {mm(7.6)}; text-align:justify; font-size:{pt(10.3)}; line-height:1.58; }}
.ak p.pt2 {{ color:#55606b; font-size:{pt(9.5)}; }}
.ak p.chk {{ color:#b5542c; }}
"""


_ORIG_SPLITS = B._splits


def _splits(raw, n_q):
    """build.py 의 쪽 넘김 검사는 '마지막 문항 뒤에는 아무것도 없다'고 가정한다. 이 자료는 각 부의 마지막
    문항 뒤에 새 쪽으로 정답·해설이 이어지므로, 그 문항이 한 쪽 안에 다 들어갔는데도 잘렸다고 보고 다음
    쪽으로 밀어 버린다. 다음 부(PART) 제목이 바로 다음 쪽에서 시작하면 잘린 게 아니므로 빼 준다."""
    import pymupdf
    out = _ORIG_SPLITS(raw, n_q)
    if not out:
        return out
    d = pymupdf.open(raw)
    starts, parts = [], []
    for k, pg in enumerate(d):
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for s_ in l['spans']:
                    t = s_['text'].strip()
                    if s_['color'] == 0x1a4f8a and re.match(r'^\d{1,3}\.$', t):
                        starts.append(k)
                    elif t.startswith('PART '):
                        parts.append(k)
    keep = []
    for i in out:
        k = starts[i]
        nxt_q = starts[i + 1] if i + 1 < len(starts) else None
        nxt_part = min((h for h in parts if h > k), default=None)
        last_in_part = nxt_part is not None and (nxt_q is None or nxt_q >= nxt_part)
        if last_in_part and nxt_part == k + 1:
            continue
        keep.append(i)
    return keep


B._splits = _splits


def ptext(s):
    """practice text → html (keeps simple <b>, <sub>, <sup>; ^ and _ shorthands)."""
    s = html.escape(s, quote=False)
    s = re.sub(r'&lt;(/?)(b|sub|sup|u)&gt;', r'<\1\2>', s)
    for pat, rep in B.SUBSUP:
        s = re.sub(pat, rep, s)
    return s.replace('\n', '<br>')


def practice_q(k, p):
    parts = [f'<div class="q"><div class="qb">',
             f'<p class="stem"><span class="num">{k}.</span> {ptext(p["stem"])}</p>']
    box = p.get('box')
    if box:
        lines = box if isinstance(box, list) else [box]
        cls = '' if isinstance(box, list) else ' class="pp"'
        parts.append('<div class="box">' + ''.join(f'<p{cls}>{ptext(l)}</p>' for l in lines) + '</div>')
    if p.get('choices'):
        parts.append('<ol class="ch">' + ''.join(f'<li><span class="cn">{CIRCLE[i]}</span>{ptext(c)}</li>'
                                                for i, c in enumerate(p['choices'])) + '</ol>')
    else:
        parts.append('<p class="subj">(단답·서술형)</p>')
    parts.append('</div></div>')
    return ''.join(parts)


def part_head(n, title, sub, brk=True):
    return (f'<div class="part{" pb" if brk else ""}"><div class="pn">PART {n}</div>'
            f'<div class="pt">{html.escape(title)}</div><div class="ps">{html.escape(sub)}</div></div>')


def cmd_build(a):
    import markdown
    inf = load_info(a.subject); L = find_lecture(inf, a.lecture)
    fd = folder(a.subject, L)
    md_p, pr_p = os.path.join(fd, '1_설명.md'), os.path.join(fd, '3_연습문제.json')
    for p in (md_p, pr_p):
        if not os.path.exists(p):
            sys.exit(f'!! {os.path.relpath(p, ROOT)} 가 없습니다.')
    notes_md = open(md_p, encoding='utf-8').read()
    practice = json.load(open(pr_p, encoding='utf-8'))
    practice = practice.get('questions', practice) if isinstance(practice, dict) else practice
    bad = [i + 1 for i, p in enumerate(practice)
           if not p.get('stem') or not p.get('explanation') or (p.get('choices') and not p.get('answer'))]
    if bad:
        sys.exit(f'!! 연습문제 {bad}번에 stem/answer/explanation 이 빠졌습니다.')
    items = collect(a.subject, inf, L['id'])
    B.IMG_ABS = True
    name = BL.lname(L)

    # 표지에 쓸 필기본 연도: 1_설명.md 맨 위 <!-- 필기본: 2026, 2025 --> (없으면 표시 안 함)
    m = re.search(r'<!--\s*필기본\s*:\s*([^>]*?)\s*-->', notes_md)
    src_years = m.group(1) if m else ''

    # 1부
    body_md = markdown.markdown(notes_md, extensions=['tables', 'admonition', 'sane_lists', 'attr_list'])
    p1 = part_head(1, '개념 설명', f'필기본 {src_years} 정리' if src_years else '필기본 정리') + f'<div class="notes">{body_md}</div>'

    # 2부 기출 (문제지와 같은 모양) + 정답·해설 모음
    years = []
    for ex, *_ in items:
        if ex['year'] not in years:
            years.append(ex['year'])
    if items:
        sec, nums = BL.section_html(L, [(ex, q, e) for ex, q, e, _ in items], inf['name'], title_tag='h2')
        sec = sec[sec.index('<h2 class="yr">'):]          # 수업 제목 줄은 빼고 연도별부터
        p2 = part_head(2, '기출문제', f"{', '.join(map(str, years))}년 · {len(items)}문항 · 정답·해설은 2부 끝에") + sec
        aks, missing = [], []
        for k, (ex, q, e, an) in enumerate(items, 1):
            exp = an.get('explanation') or ''
            if not exp:
                missing.append(f"{ex['id']} {q['n']}번")
            ps = ''.join(f'<p class="{"chk" if l.startswith("※") else ""}">{B.text(l)}</p>'
                         for l in (exp or '(해설 없음)').split('\n') if l.strip())
            aks.append(f'<div class="ak"><div class="h"><span class="an">{k}번</span><span class="lab">정답 '
                       f'{html.escape(ans_label(an))}</span><span class="src">{html.escape(byline(ex, q, e))}</span></div>{ps}</div>')
        p2 += part_head(2, '기출문제 정답·해설', f'{len(items)}문항') + ''.join(aks)
    else:
        nums, missing = [], []
        p2 = (part_head(2, '기출문제', '분류된 기출 없음') +
              f'<p class="empty">저장소 분류/{html.escape(a.subject)}/ 에 이 수업으로 분류된 기출이 없습니다.</p>')

    # 3부 연습문제 + 해설 모음
    p3 = part_head(3, '연습문제', f'{len(practice)}문항 · 해설은 3부 끝에')
    p3 += ''.join(practice_q(k, p) for k, p in enumerate(practice, 1))
    aks = []
    for k, p in enumerate(practice, 1):
        lab = (', '.join(CIRCLE[x - 1] for x in p['answer']) if p.get('choices') else str(p.get('answer', '')))
        extra = f'<p class="pt2">관련 개념 · {ptext(p["point"])}</p>' if p.get('point') else ''
        aks.append(f'<div class="ak"><div class="h"><span class="an">{k}번</span><span class="lab">정답 {ptext(lab)}</span></div>'
                   + ''.join(f'<p>{ptext(l)}</p>' for l in p['explanation'].split('\n') if l.strip()) + extra + '</div>')
    p3 += part_head(3, '연습문제 해설', f'{len(practice)}문항') + ''.join(aks)

    cover = (f'<div class="cover"><div class="subj">{html.escape(inf["name"])} · {L["id"]}강</div>'
             f'<div class="title">{html.escape(name)}</div><div class="rule"></div>'
             f'<div class="meta">학습자료{(" · 필기본 " + html.escape(src_years)) if src_years else ""}</div>'
             f'<div class="toc"><div><b>1부</b>개념 설명</div>'
             f'<div><b>2부</b>기출문제<span>{len(items)}문항 + 정답·해설</span></div>'
             f'<div><b>3부</b>연습문제<span>{len(practice)}문항 + 해설</span></div></div></div>')

    doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{B.CSS}{BL.EXTRA_CSS}{CSS}</style></head>'
           f'<body>{cover}{p1}{p2}{p3}</body></html>')
    out = os.path.join(ROOT, '학습자료', a.subject, f"{L['id']}_{BL.safe(name)}_학습자료.pdf")
    work = os.path.join(ROOT, 'work', '_study', a.subject, L['id']); os.makedirs(work, exist_ok=True)
    print(f'== {os.path.relpath(out, ROOT)}  (기출 {len(items)} · 연습 {len(practice)})')
    total = B.render_pdf(doc, work, out, f"{inf['name']} {name} 학습자료")
    ok = verify(out, work, total, len(items), len(practice))
    if missing:
        print(f'[FAIL] 해설이 비어 있는 기출 {len(missing)}개: {missing} — 해설/{a.subject}/<시험id>.json 에 채운 뒤 다시 build')
        ok = False
    sys.exit(0 if ok else 1)


def verify(out, work, total, n_g, n_p):
    import pymupdf
    d = pymupdf.open(out)
    pv = os.path.join(work, 'pv'); os.makedirs(pv, exist_ok=True)
    for f_ in os.listdir(pv):
        os.remove(os.path.join(pv, f_))
    for i, p in enumerate(d):
        p.get_pixmap(dpi=96).save(os.path.join(pv, f'{i + 1:02d}.png'))
    txt = '\n'.join(p.get_text() for p in d)
    fonts = sorted({f[3].split('+')[-1] for p in d for f in p.get_fonts()})
    need = [f'{B.FAMILY}-Regular', f'{B.FAMILY}-Bold', 'StudyBatang-Regular', 'StudyBatang-Bold']
    lack = [f for f in need if f not in fonts]
    stray = [f for f in fonts if f not in need and f != 'Helvetica']  # Helvetica = 쪽 번호 캔버스 기본값
    q_nums = re.findall(r'^(\d{1,3})\.\s', txt, re.M)
    aks = len(re.findall(r'^\d{1,3}번\s*\n?정답', txt, re.M))
    print(f'output: {out}  pages: {total}')
    print(f"[{'OK' if not lack else 'FAIL'}] 글씨체: {fonts}" + (f'  !! 빠짐 {lack}' if lack else '')
          + (f'  (대체 글꼴 {stray} — 해당 글자가 두 글씨체에 없음)' if stray else ''))
    print(f"[{'OK' if len(q_nums) >= n_g + n_p else 'FAIL'}] 문항 번호 {len(q_nums)}개 (기출 {n_g} + 연습 {n_p})")
    print(f"[{'OK' if aks == n_g + n_p else 'CHECK'}] 정답·해설 항목 {aks}개 (기출 {n_g} + 연습 {n_p})")
    print(f'previews: {pv}/NN.png  -> 페이지를 눈으로 확인할 것')
    return not lack and len(q_nums) >= n_g + n_p


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    f = sp.add_parser('find'); f.add_argument('subject'); f.add_argument('key', nargs='?', default='')
    g = sp.add_parser('gichul'); g.add_argument('subject'); g.add_argument('lecture')
    b = sp.add_parser('build'); b.add_argument('subject'); b.add_argument('lecture')
    a = ap.parse_args()
    {'find': cmd_find, 'gichul': cmd_gichul, 'build': cmd_build}[a.cmd](a)


if __name__ == '__main__':
    main()
