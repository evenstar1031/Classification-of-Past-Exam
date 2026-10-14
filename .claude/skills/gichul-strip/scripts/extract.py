#!/usr/bin/env python3
"""Extract figures + structure from an answer-marked exam PDF.

usage: extract.py SOURCE.pdf WORKDIR

Writes into WORKDIR:
  fig/*.png          trimmed figures
  meta.json          title / exam date / detected layout profile
  parsed.json        questions as ordered blocks + choices
  report.txt         one-screen-per-question review dump (answer marks shown as *)
  joins.txt          every Hangul|Hangul line break, for the space decisions
  fixes.json         created empty if absent (never overwritten)
and prints a reconciliation check that must pass.
"""
import collections, io, json, os, re, sys
import pymupdf
import numpy as np
from PIL import Image

SRC, WORK = sys.argv[1], sys.argv[2]
FIG = os.path.join(WORK, 'fig')
os.makedirs(FIG, exist_ok=True)
doc = pymupdf.open(SRC)
QRE = re.compile(r'^(\d{1,3})\.$')
CRE = re.compile(r'^(\d{1,2})\)$')
AUTH_RE = re.compile(r'^출제자\s*[:：]\s*(.+?)\s*$')
AUTH_ANY = re.compile(r'출제자\s*[:：]\s*(\S+)')
LISTNUM = re.compile(r'^\d{1,2}\.$')
BULLETS = {'●', '•', '▪', '■', '◦', '○', '·'}
HANGUL = re.compile(r'[\uac00-\ud7a3\u3131-\u318e]')

# ------------------------------------------------------------------ text
lines = []
for pno, page in enumerate(doc):
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        for l in b['lines']:
            sp = l['spans']
            # split lines where the question/choice number span is merged with its text
            if len(sp) > 1 and re.match(r'^\d{1,3}[.)]$', sp[0]['text'].strip()) and ''.join(x['text'] for x in sp[1:]).strip():
                m0 = sp[0]
                lines.append({'page': pno, 'x': round(m0['bbox'][0], 1), 'y': l['bbox'][1],
                              'y1': l['bbox'][3], 'x1': m0['bbox'][2], 't': m0['text'].strip(),
                              'sz': round(m0['size'], 1), 'col': [m0['color']]})
                rest = [x for x in sp[1:] if x['text'].strip()]
                rest_all = sp[1:]
                while rest_all and not rest_all[0]['text'].strip():
                    rest_all = rest_all[1:]
                lines.append({'page': pno, 'x': round(rest[0]['bbox'][0], 1), 'y': l['bbox'][1] + 0.01,
                              'y1': l['bbox'][3], 'x1': l['bbox'][2], 't': ''.join(x['text'] for x in rest_all),
                              'sz': round(max(x['size'] for x in rest), 1),
                              'col': sorted({x['color'] for x in rest})})
                continue
            t = ''.join(s['text'] for s in l['spans'])
            if not t.strip():
                continue
            # 3-digit numbers can share ONE span with the stem ("102. 다음은 …"); split
            # them like the multi-span case (the text's x is set to main_x after profiling)
            m = re.match(r'^\s*(\d{1,3}\.)\s+(\S.*)$', t)
            if m and l['bbox'][0] < 0.12 * page.rect.width:
                lines.append({'page': pno, 'x': round(l['bbox'][0], 1), 'y': l['bbox'][1],
                              'y1': l['bbox'][3], 'x1': l['bbox'][2], 't': m.group(1),
                              'sz': round(max(s['size'] for s in l['spans']), 1),
                              'col': sorted({s['color'] for s in l['spans']})})
                lines.append({'page': pno, 'x': None, 'y': l['bbox'][1] + 0.01,
                              'y1': l['bbox'][3], 'x1': l['bbox'][2], 't': m.group(2),
                              'sz': round(max(s['size'] for s in l['spans']), 1),
                              'col': sorted({s['color'] for s in l['spans']})})
                continue
            lines.append({'page': pno, 'x': round(l['bbox'][0], 1), 'y': l['bbox'][1],
                          'y1': l['bbox'][3], 'x1': l['bbox'][2], 't': t,
                          'sz': round(max(s['size'] for s in l['spans']), 1),
                          'col': sorted({s['color'] for s in l['spans']})})

# a 3-digit number can also wrap its "." onto the next line ("101" / "."): rejoin them
for l in lines:
    if l['x'] is not None and l['x'] < 0.12 * doc[l['page']].rect.width and re.match(r'^\d{1,3}$', l['t'].strip()):
        dot = next((d for d in lines if d is not l and d['page'] == l['page'] and d['t'].strip() == '.'
                    and d['x'] is not None and abs(d['x'] - l['x']) < 2 and 0 < d['y'] - l['y'] < 30), None)
        if dot is not None:
            l['t'] = l['t'].strip() + '.'
            dot['t'] = ''
lines = [l for l in lines if l['t'].strip()]

# ------------------------------------------------------------------ profile
qn = [l for l in lines if QRE.match(l['t'].strip())]
cn = [l for l in lines if CRE.match(l['t'].strip())]
marker_x = collections.Counter(l['x'] for l in qn + cn).most_common(1)[0][0]
q_size = collections.Counter(l['sz'] for l in qn if l['x'] == marker_x).most_common(1)[0][0]
body = [l for l in lines if l['x'] is not None and l['x'] > marker_x + 5]
main_x = collections.Counter(l['x'] for l in body).most_common(1)[0][0]
for l in lines:
    if l['x'] is None:          # stem text split off a one-span "102. …" line
        l['x'] = main_x
page_w = doc[0].rect.width
prof = {'marker_x': marker_x, 'main_x': main_x, 'q_size': q_size,
        'box_x_max': round(page_w * 0.3, 1)}
print('layout profile:', prof)
dist = collections.Counter((l['sz'], l['x'], tuple(hex(c) for c in l['col'])) for l in lines)
print('size/x/colour distribution (check nothing unexpected):')
for k, v in sorted(dist.items()):
    print('   ', k, v)

# header (page 0, above the first question number)
first_q_y = min(l['y'] for l in qn if l['page'] == 0) if any(l['page'] == 0 for l in qn) else 80
head = [l for l in lines if l['page'] == 0 and l['y'] < first_q_y - 2]
title, date = None, None
for h in head:
    m = re.search(r'(\d{4}-\d{2}-\d{2})', h['t'])
    if m:
        date = m.group(1)
    elif title is None:
        title = h['t'].strip()
if date is None and title:
    m = re.match(r'(\d{2})(\d{2})(\d{2})', title)
    if m:
        date = f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
print('title:', title, '| date:', date)
head_ids = {id(h) for h in head}


def is_marked(l, choice_size):
    blueish = any(((c >> 16) & 255) + 40 < (c & 255) for c in l['col'])
    return blueish or (choice_size + 0.8 < l['sz'] < q_size - 0.3)


choice_size = collections.Counter(l['sz'] for l in cn).most_common(1)[0][0]
for l in lines:
    x, big = l['x'], l['sz'] >= q_size - 0.3
    if id(l) in head_ids:
        k = 'head'
    elif x <= marker_x + 5:
        k = 'qnum' if (big and QRE.match(l['t'].strip())) else 'cnum'
    elif x <= main_x + 5:
        k = 'stem' if big else 'ctext'
    elif x < prof['box_x_max']:
        # stem text indented by a Word list sits here too: question-size text is stem
        k = 'stem' if big else 'box'
    else:
        k = 'aside'
    t_ = l['t'].strip()
    if k in ('stem', 'box', 'ctext') and x > marker_x + 5 and (LISTNUM.match(t_) or t_ in BULLETS):
        k = 'junk'        # orphan Word list numbering ("1." "2." "3.") / bullet glyphs
    if k != 'head' and AUTH_RE.match(l['t'].strip()):
        k = 'author'      # byline of the NEXT question; never a label/box/note
    l['k'] = k
    l['mk'] = is_marked(l, choice_size)

# ------------------------------------------------------------------ figures
def merge_rects(rects, pad=2.0):
    boxes = [list(r) for r in rects]
    changed = True
    while changed:
        changed, out = False, []
        for b in boxes:
            for o in out:
                if b[0] < o[2] + pad and o[0] < b[2] + pad and b[1] < o[3] + pad and o[1] < b[3] + pad:
                    o[:] = [min(b[0], o[0]), min(b[1], o[1]), max(b[2], o[2]), max(b[3], o[3])]
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return [pymupdf.Rect(*b) for b in sorted(boxes, key=lambda b: (b[1], b[0]))]


def trim_white(im, thresh=246, pad=4):
    g = np.asarray(im.convert('L')); mask = g < thresh
    if not mask.any():
        return im
    ys, xs = np.where(mask)
    return im.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                    min(im.width, xs.max() + 1 + pad), min(im.height, ys.max() + 1 + pad)))


def embedded_for(page, rect):
    best = None
    for info in page.get_image_info(xrefs=True):
        xref = info.get('xref', 0)
        r = pymupdf.Rect(info['bbox'])
        if not xref or r.is_empty:
            continue
        inter = r & rect
        if inter.is_empty or inter.get_area() < 0.6 * r.get_area():
            continue
        if best is None or info['width'] * info['height'] > best[1]['width'] * best[1]['height']:
            best = (xref, info)
    if best is None:
        return None, 0
    xref, info = best
    try:
        base = doc.extract_image(xref)
        im = Image.open(io.BytesIO(base['image']))
    except Exception:
        return None, 0
    bg = Image.new('RGB', im.size, (255, 255, 255))
    if base.get('smask'):
        try:
            m = Image.open(io.BytesIO(doc.extract_image(base['smask'])['image'])).convert('L').resize(im.size)
            bg.paste(im.convert('RGB'), mask=m); im = bg
        except Exception:
            im = im.convert('RGB')
    elif im.mode in ('RGBA', 'LA'):
        im = im.convert('RGBA'); bg.paste(im, mask=im.split()[-1]); im = bg
    else:
        im = im.convert('RGB')
    return im, info['width']


figs = []
for pno, page in enumerate(doc):
    infos = page.get_image_info()
    if not infos:
        continue
    # a full-page background image would swallow every real figure when merged
    pa = page.rect.width * page.rect.height
    infos = [i for i in infos if pymupdf.Rect(i['bbox']).get_area() < 0.85 * pa]
    for k, rect in enumerate(merge_rects([pymupdf.Rect(i['bbox']) for i in infos])):
        if rect.width < 25 or rect.height < 25:
            continue
        pix = page.get_pixmap(clip=rect, dpi=220)
        rend = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        emb, embw = embedded_for(page, rect)
        im, src = (emb, 'embedded') if emb is not None and embw > pix.width * 1.05 else (rend, 'render')
        im = trim_white(im)
        name = f'p{pno:02d}_{k}.png'
        im.save(os.path.join(FIG, name))
        figs.append({'page': pno, 'x': rect.x0, 'y': rect.y0, 'y1': rect.y1, 'k': 'fig',
                     't': name, 'sz': 0, 'mk': False, 'src': src})
print(f'figures: {len(figs)} ({sum(f["src"] == "embedded" for f in figs)} embedded originals)')

# ------------------------------------------------------------------ stream -> questions
stream = sorted(lines + figs, key=lambda s: (s['page'], s['y'], s['x']))
qs, cur = [], None
authors, pending = {}, None
for h in head:
    m = AUTH_ANY.search(h['t'])
    if m:
        pending = m.group(1).strip()
for s in stream:
    if s['k'] == 'head':
        continue
    if s['k'] == 'author':
        pending = AUTH_RE.match(s['t'].strip()).group(1)
        continue
    if s['k'] == 'qnum':
        cur = {'n': int(QRE.match(s['t'].strip()).group(1)), 'items': []}
        qs.append(cur)
        if pending:
            authors[str(cur['n'])] = pending
            pending = None
    elif cur is not None:
        cur['items'].append(s)
print(f"list-number/bullet artefacts dropped: {sum(1 for l in lines if l['k'] == 'junk')}")
print(f'bylines (출제자) detected: {len(authors)} -> meta.json "authors"')


def dp_assign(bodies, markers):
    """Cut contiguous choice-text lines into one group per marker.  Markers are
    vertically centred on multi-line choices, so the first line of a choice can
    sit ABOVE its marker; assign by vertical distance, not by 'after marker'."""
    n, m = len(bodies), len(markers)
    if m == 0:
        return []
    INF = float('inf')
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for j in range(1, m + 1):
        mk = markers[j - 1]
        for i in range(n + 1):
            for k in range(i + 1):
                if dp[k][j - 1] == INF:
                    continue
                grp = bodies[k:i]
                if grp:
                    c = sum(b['y'] for b in grp) / len(grp)
                    cost = abs(c - mk['y']) + (0 if mk['page'] in {b['page'] for b in grp} else 500)
                else:
                    cost = 60.0
                if dp[k][j - 1] + cost < dp[i][j]:
                    dp[i][j], bk[i][j] = dp[k][j - 1] + cost, k
    groups, i = [], n
    for j in range(m, 0, -1):
        k = bk[i][j]; groups.append(bodies[k:i]); i = k
    return groups[::-1]


out, dropped_total = [], 0
for q in qs:
    items = q['items']
    markers = [s for s in items if s['k'] == 'cnum']
    first_key = (markers[0]['page'], markers[0]['y']) if markers else (10 ** 6, 0)

    def before(el, y=None):
        return (el['page'], el['y'] if y is None else y) < first_key

    blocks, note, notes = [], False, []      # notes: dropped ⓘ 오답노트/해설 lines (for the answer edition)
    for s in items:
        if not before(s, s['y1'] if s['k'] == 'fig' else s['y']):
            continue
        if s['k'] in ('box', 'aside'):
            if s['t'].strip().startswith('ⓘ'):
                note = True
            if note:
                dropped_total += 1
                notes.append(s['t'])
                continue
            if blocks and blocks[-1]['t'] == 'box' and s['page'] == blocks[-1]['_p'] \
                    and s['y'] - blocks[-1]['_y'] < 22:
                blocks[-1]['lines'].append(s['t']); blocks[-1]['_y'] = s['y']
            else:
                blocks.append({'t': 'box', 'lines': [s['t']], '_p': s['page'], '_y': s['y']})
        elif s['k'] == 'stem':
            note = False
            if blocks and blocks[-1]['t'] == 'text':
                blocks[-1]['lines'].append(s['t'])
            else:
                blocks.append({'t': 'text', 'lines': [s['t']]})
        elif s['k'] == 'fig':
            note = False
            blocks.append({'t': 'fig', 'file': s['t']})
    # merge boxes that only split at a page break
    merged = []
    for b in blocks:
        if merged and b['t'] == 'box' and merged[-1]['t'] == 'box':
            merged[-1]['lines'] += b['lines']
        else:
            merged.append(b)
    blocks = [{k: v for k, v in b.items() if not k.startswith('_')} for b in merged]

    # box-position lines between the first choice number and the first ⓘ note are
    # choice text indented by a Word list (e.g. "1. 치밀 유방을…" set at x≈116)
    note_key = next(((s['page'], s['y']) for s in items if s['k'] in ('box', 'aside')
                     and s['t'].strip().startswith('ⓘ')), (10 ** 6, 0))
    for s in items:
        if s['k'] == 'box' and markers and not before(s) and (s['page'], s['y']) < note_key:
            s['k'] = 'ctext'
    ctexts = [s for s in items if s['k'] == 'ctext']          # ALL of them
    answer_text = []
    if not markers and ctexts:
        # 주관식: choice-size text under a question with no choice numbers is the typed answer
        answer_text = [s_['t'].strip() for s_ in ctexts]
        for s_ in ctexts:
            s_['k'] = 'answer'
            print(f'  !! Q{q["n"]}: 주관식 answer text dropped: {s_["t"][:60]!r}')
        ctexts = []
    groups = dp_assign(ctexts, markers)
    choices = [{'n': mk['t'].strip(), 'page': mk['page'], 'y': mk['y'],
                'lines': [b['t'] for b in g], 'figs': [], 'label': None,
                'mk': mk['mk'] or any(b['mk'] for b in g), 'mk_num': mk['mk'],
                'mk_lines': [b['t'] for b in g if b['mk']]} for mk, g in zip(markers, groups)]

    def owner(page, y):
        tgt = None
        for c in choices:
            if (c['page'], c['y']) < (page, y):
                tgt = c
        return tgt

    note = False
    note_figs = []                       # images inside an ⓘ 오답노트/해설 box (e.g. a table)
    for s in items:
        if before(s, s['y1'] if s['k'] == 'fig' else s['y']):
            continue
        if s['k'] == 'fig' and note:
            # after the choices, an ⓘ note runs to the end of the question: its images
            # are part of the note (an answer leak if attached to the last choice)
            note_figs.append(s['t'])
            print(f'  !! Q{q["n"]}: figure inside ⓘ note dropped: {s["t"]}')
            continue
        if s['k'] == 'fig':
            o = owner(s['page'], s['y1'])
            if o:
                o['figs'].append(s['t'])
        elif s['k'] in ('box', 'aside'):
            if s['t'].strip().startswith('ⓘ'):
                note = True
            if note:
                dropped_total += 1
                notes.append(s['t'])
            elif s['k'] == 'aside':
                o = owner(s['page'], s['y'])
                if o:
                    o['label'] = s['t'].strip()
            else:
                # choice text indented past the box threshold (e.g. "●  Aortic stenosis"
                # set as a bulleted list inside the choice cell): same row as a marker
                row = next((c for c in choices if c['page'] == s['page'] and abs(c['y'] - s['y']) < 8), None)
                if row is not None:
                    if s['t'].strip() in BULLETS:
                        dropped_total += 1          # decorative bullet glyph
                    else:
                        s['k'] = 'ctext'; row['lines'].append(s['t'])
                        row['mk'] = row['mk'] or s['mk']
                        if s['mk']:
                            row['mk_lines'].append(s['t'])
                    continue
                print(f'  !! Q{q["n"]}: box line after choices kept nowhere: {s["t"][:60]!r}')
    # notes / answer_text / mk_num / mk_lines feed the answer edition (tools/build_answers.py);
    # the question-only build never reads them
    out.append({'n': q['n'], 'blocks': blocks, 'notes': notes, 'answer_text': answer_text,
                'choices': [{k: c[k] for k in ('n', 'lines', 'figs', 'label', 'mk', 'mk_num', 'mk_lines')}
                            for c in choices]})
    if note_figs:
        out[-1]['note_figs'] = note_figs

json.dump(out, open(os.path.join(WORK, 'parsed.json'), 'w'), ensure_ascii=False, indent=1)
json.dump({'title': title, 'date': date, 'profile': prof, 'source': SRC, 'authors': authors},
          open(os.path.join(WORK, 'meta.json'), 'w'), ensure_ascii=False, indent=1)
fx = os.path.join(WORK, 'fixes.json')
if not os.path.exists(fx):
    json.dump({"title": None, "date": None, "authors": None, "spaces": {}, "fixes": [],
               "regroup": {}, "prose_boxes": [], "split_box": {}, "para_starts": {},
               "drop_lines": {}, "extra_figs": {}, "media": {}},
              open(fx, 'w'), ensure_ascii=False, indent=1)

# ------------------------------------------------------------------ report / joins
with open(os.path.join(WORK, 'report.txt'), 'w') as R:
    for q in out:
        R.write('=' * 70 + f"\nQ{q['n']}\n")
        for bi, b in enumerate(q['blocks']):
            if b['t'] == 'fig':
                R.write(f"  [s{bi} FIG] {b['file']}\n")
            else:
                R.write(f"  [s{bi} {b['t'].upper()}] " + ' ¶ '.join(b['lines']) + '\n')
        for i, c in enumerate(q['choices']):
            R.write(f"   c{i+1} {'*' if c['mk'] else ' '} " + ' ¶ '.join(c['lines'])
                    + (f"  figs={c['figs']}" if c['figs'] else '')
                    + (f"  label={c['label']!r}" if c['label'] else '') + '\n')
# ------------------------------------------------------------------ warnings
def reddish(c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return r > 150 and g < 90 and b < 90
GARBLED = re.compile(r'[\x00-\x08\x0b-\x1f]|[\u0800-\u0fff]')
warns = []
for l in lines:
    if l['k'] in ('head',):
        continue
    if any(reddish(c) for c in l['col']):
        warns.append(f"p{l['page']+1} RED  {l['t'][:70]!r}  <- 정답수정/미디어 표기 등 원본 메모일 수 있음")
    if GARBLED.search(l['t']):
        warns.append(f"p{l['page']+1} GARBLED {l['t'][:40]!r}  <- 폰트 매핑 깨짐: 원본을 렌더해서 확인")
with open(os.path.join(WORK, 'report.txt'), 'a') as R:
    R.write('=' * 70 + '\nWARNINGS (look at every one in the source render)\n' + '\n'.join(warns or ['(none)']) + '\n')
if warns:
    print(f'WARNINGS: {len(warns)} red/garbled lines -> end of report.txt (check each: answer memos hide here)')
    for w in warns:
        print('   ', w)

njoin = 0
with open(os.path.join(WORK, 'joins.txt'), 'w') as J:
    J.write('# key|break-index|...앞줄끝|다음줄시작...   -> put indices that need a SPACE into fixes.json "spaces"\n')
    for q in out:
        def scan(tag, ls):
            global njoin
            for i in range(len(ls) - 1):
                a, b = ls[i].strip(), ls[i + 1].strip()
                if a and b and HANGUL.match(a[-1]) and HANGUL.match(b[0]):
                    J.write(f"{q['n']}/{tag}|{i}|{a[-12:]}|{b[:12]}\n"); njoin += 1
        for bi, b in enumerate(q['blocks']):
            if b['t'] == 'text':
                scan(f's{bi}', b['lines'])
        for i, c in enumerate(q['choices']):
            scan(f'c{i+1}', c['lines'])

# ------------------------------------------------------------------ reconciliation
src_cnt = collections.Counter(l['k'] for l in lines)
p_stem = sum(len(b['lines']) for q in out for b in q['blocks'] if b['t'] == 'text')
p_ch = sum(len(c['lines']) for q in out for c in q['choices'])
p_box = sum(len(b['lines']) for q in out for b in q['blocks'] if b['t'] == 'box')
p_lab = sum(1 for q in out for c in q['choices'] if c['label'])
p_fig = (sum(1 for q in out for b in q['blocks'] if b['t'] == 'fig') + sum(len(c['figs']) for q in out for c in q['choices'])
         + sum(len(q.get('note_figs', [])) for q in out))
nums = [q['n'] for q in out]
checks = [
    ('question numbers 1..N contiguous', nums == list(range(1, len(nums) + 1)), f'{len(nums)} questions'),
    ('stem lines', src_cnt['stem'] == p_stem, f"{src_cnt['stem']} -> {p_stem}"),
    ('choice lines', src_cnt['ctext'] == p_ch, f"{src_cnt['ctext']} -> {p_ch}"),
    ('box/aside lines = kept + labels + dropped notes',
     src_cnt['box'] + src_cnt['aside'] == p_box + p_lab + dropped_total,
     f"{src_cnt['box'] + src_cnt['aside']} = {p_box} + {p_lab} + {dropped_total}"),
    ('figures placed (incl. dropped ⓘ-note images)', len(figs) == p_fig, f'{len(figs)} -> {p_fig}'),
    ('every question has choices or is flagged subjective', True,
     'subjective/no-choice: ' + str([q['n'] for q in out if not q['choices']])),
]
print('\nRECONCILIATION')
ok = True
for name, passed, detail in checks:
    ok &= passed
    print(f"  [{'OK' if passed else 'FAIL'}] {name}: {detail}")
print(f'\nHangul|Hangul joins to review: {njoin}  -> joins.txt')
print('ALL CHECKS PASSED' if ok else 'RECONCILIATION FAILED - fix parsing before building')
sys.exit(0 if ok else 1)
