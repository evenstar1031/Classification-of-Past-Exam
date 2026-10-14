#!/usr/bin/env python3
"""Typeset parsed.json + fixes.json into the answer-free A4 PDF.

usage: build.py WORKDIR OUTPUT.pdf

Also importable (tools/build_lectures.py): load(workdir) switches the current exam,
build_q(q, disp, byline) renders one question, CSS / render_pdf / verify are shared.

Steps: HTML -> wkhtmltopdf -> "n / N" page-number overlay -> verification
(text layer, 88/88 question numbers, answer-leak regex, fonts) -> previews in
WORKDIR/pv/*.png for visual review.
"""
import html, io, json, os, re, subprocess, sys
from PIL import Image

WORK = FIG = OUT = None
P, META, FX = [], {}, {}
IMG_ABS = False        # True when the HTML is not written inside WORK (multi-exam documents)
_CACHE = {}


def load(work):
    """Make `work` the current exam (parsed/meta/fixes + figure dir)."""
    global WORK, FIG, P, META, FX
    work = os.path.abspath(work)
    if work not in _CACHE:
        rd = lambda f: json.load(open(os.path.join(work, f), encoding='utf-8'))
        _CACHE[work] = (rd('parsed.json'), rd('meta.json'), rd('fixes.json'))
    WORK, FIG = work, os.path.join(work, 'fig')
    P, META, FX = _CACHE[work]


def src_of(path):
    return os.path.abspath(path) if IMG_ABS else os.path.relpath(path, WORK)

F = 1.30259            # wkhtmltopdf lays out at 125dpi, prints at 96dpi -> pre-scale all CSS
BODY_MM = 186.0        # A4 210 - 12 - 12
FAMILY = 'GichulTT'     # registered by setup_fonts.py from whatever font is in fonts/
CIRCLE = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
HANGUL = re.compile(r'[\uac00-\ud7a3\u3131-\u318e]')
NO_SPACE_BEFORE = '.,)]}?!;:%’”℃/'
APPLIED = []
# vertical rhythm around the 출제자 byline (mm, before the 1.30259 pre-scale).
# Box-first questions hang their number beside the box's first text line, which sits
# BOX_PAD_V below the box edge, so their byline gap is smaller by that amount;
# the two gaps are tuned so byline-bottom -> number-top is identical for both kinds.
BOX_PAD_V = 2.4
BYLINE_GAP = 3.0
BYLINE_GAP_BF = 0.95


# characters the chosen font may lack (e.g. Apple SD Gothic Neo has no ₀ ₅ · −):
# replaced before rendering so the text layer stays in our font instead of a fallback
_SUB = dict(zip('₀₁₂₃₄₅₆₇₈₉₊₋', '0123456789+−'))
_SUP = dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻', '0123456789+−'))
_ALT = {'·': '∙ㆍ・•', '−': '–-', '×': 'x', 'é': 'e', 'ö': 'o', '℃': '', '→': '', '↑': '', '↓': ''}


def glyph_safe(doc):
    """Swap characters missing from the installed font. Returns (doc, still-missing chars)."""
    from fontTools.ttLib import TTFont
    cm = TTFont(os.path.expanduser(f'~/.fonts/{FAMILY}-Regular.ttf')).getBestCmap()
    have = lambda c: ord(c) in cm
    left = set()

    def one(c):
        if c.isascii() or have(c):
            return c
        for tbl, tag in ((_SUB, 'sub'), (_SUP, 'sup')):
            if c in tbl:
                return f'<{tag}>{one(tbl[c])}</{tag}>'
        for alt in _ALT.get(c, ''):
            if have(alt):
                return alt
        left.add(c)
        return c

    head, sep, body = doc.partition('<body>')
    body = re.sub(r'>([^<]+)<', lambda m: '>' + ''.join(one(c) for c in m.group(1)) + '<', body)
    return head + sep + body, sorted(left)


def mm(v): return f'{v * F:.3f}mm'
def pt(v): return f'{v * F:.2f}pt'


# ----------------------------------------------------------------- text helpers
def join_lines(lines, spaces=()):
    """PDF drops line-final spaces; `spaces` = break indices that were a space."""
    out = ''
    for idx, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        if not out:
            out = s; continue
        a, b = out[-1], s[0]
        if (idx - 1) in spaces:
            sep = ' '
        elif b in NO_SPACE_BEFORE or a in '([{‘“/-':
            sep = ''
        elif HANGUL.match(a) and HANGUL.match(b):
            sep = ''
        else:
            sep = ' '
        out += sep + s
    return re.sub(r'  +', ' ', out).strip()


SUBSUP = [  # applied after html-escaping; keep T3/T4, G0/G1/G2 plain
    (r'\bmm3\b', 'mm³'), (r'\bPaO2\b', 'PaO₂'), (r'\bPaCO2\b', 'PaCO₂'), (r'\bPAO2\b', 'PAO₂'),
    (r'\bSaO2\b', 'SaO₂'), (r'\bSpO2\b', 'SpO₂'), (r'\bFiO2\b', 'FiO₂'), (r'\bHCO3-', 'HCO₃<sup>−</sup>'),
    (r'\bHCO3\b', 'HCO₃<sup>−</sup>'), (r'\bCO2\b', 'CO₂'), (r'\bO2\b', 'O₂'), (r'\bH2O\b', 'H₂O'),
    (r'\bH2O2\b', 'H₂O₂'), (r'\bH\+', 'H<sup>+</sup>'), (r'\bCl-(?=[\s,.)]|$)', 'Cl<sup>−</sup>'),
    (r'\bNa\+', 'Na<sup>+</sup>'), (r'\bK\+', 'K<sup>+</sup>'), (r'\bCa2\+', 'Ca<sup>2+</sup>'), (r'\bMg2\+', 'Mg<sup>2+</sup>'),
    (r'\bFe2\+', 'Fe<sup>2+</sup>'), (r'\bFe3\+', 'Fe<sup>3+</sup>'), (r'\bLD50\b', 'LD₅₀'), (r'\bED50\b', 'ED₅₀'),
    (r'\bIC50\b', 'IC₅₀'), (r'\bEC50\b', 'EC₅₀'), (r'\bFEV1\b', 'FEV₁'), (r'\bHbA1c\b', 'HbA₁c'),
    (r'\bD2 receptor', 'D₂ receptor'), (r'\bH1 receptor', 'H₁ receptor'), (r'\bSI=SI0\b', 'SI=SI₀'),
    (r'\b99mTc\b', '<sup>99m</sup>Tc'), (r'\b(\d{1,3})m(Tc|In)\b', r'<sup>\1m</sup>\2'),
    (r'\s+([,.](?:\s|$))', r'\1'),
]


def text(s):
    s = html.escape(s, quote=False)
    for pat, rep in SUBSUP + [tuple(x) for x in FX.get('extra_subsup', [])]:
        s = re.sub(pat, rep, s)
    return re.sub(r'  +', ' ', s).strip()


def apply_fixes(q, where, s):
    for fq, fw, old, new, note in FX.get('fixes', []):
        if fq == q and fw == where and old in s:
            s = s.replace(old, new)
            APPLIED.append((q, note))
    return s


def spaces(q, tag):
    return set(FX.get('spaces', {}).get(f'{q}/{tag}', []))


def drop(q, tag, lines):
    d = set(FX.get('drop_lines', {}).get(f'{q}/{tag}', []))
    return [l for i, l in enumerate(lines) if i not in d]


# ----------------------------------------------------------------- figures
def fig_box(path):
    im = Image.open(path); iw, ih = im.size; r = ih / iw
    w = min(BODY_MM, iw / 4.2)
    h = 165.0 if r > 1.7 else (140.0 if r > 1.3 else 115.0)
    rel = src_of(path)
    return f'<div class="figwrap"><img src="{rel}" style="max-width:{mm(w)};max-height:{mm(h)}"></div>'


def grid_img(path):
    im = Image.open(path); iw, ih = im.size
    w = min(86.0, iw / 4.2); h = 85.0 if ih / iw > 1.5 else 66.0
    return f'<div class="gimg"><img src="{src_of(path)}" style="max-width:{mm(w)};max-height:{mm(h)}"></div>'


def extra_fig(q, spec):
    """crop a region of the source PDF (e.g. a table that extracted as garbage)"""
    import pymupdf
    d = pymupdf.open(META['source'])
    pix = d[spec['page']].get_pixmap(clip=pymupdf.Rect(*spec['rect']), dpi=220)
    path = os.path.join(FIG, f"extra_q{q}_{spec['page']}_{int(spec['rect'][1])}.png")
    pix.save(path)
    return fig_box(path)


def box_html(q, lines, prose, sp=()):
    """sp: break indices (relative to `lines`) where a space belonged."""
    if not [l for l in lines if l.strip()]:
        return ''
    if prose:
        starts = FX.get('para_starts', {}).get(str(q), [])
        paras, cur = [], []
        for i, ln in enumerate(lines):
            key = re.sub(r'\s+', ' ', ln.strip())
            if cur and any(key.startswith(st) for st in starts):
                paras.append(cur); cur = []
            cur.append((i, ln))
        if cur:
            paras.append(cur)
        out = []
        for p in paras:
            base = p[0][0]
            local = {i - base for i in sp if base <= i and i + 1 < base + len(p)}
            out.append(f'<p class="pp">{text(apply_fixes(q, "box", join_lines([l for _, l in p], local)))}</p>')
        return '<div class="box">' + ''.join(out) + '</div>'
    rows = []
    for ln in lines:
        st = ln.rstrip(); ind = len(st) - len(st.lstrip(' '))
        if st.strip():
            rows.append('<p>' + '&nbsp;' * ind + text(apply_fixes(q, 'box', st.strip())) + '</p>')
    return '<div class="box">' + ''.join(rows) + '</div>'


# ----------------------------------------------------------------- questions
def is_image_choice(q):
    cs = q['choices']
    return bool(cs) and all(c['figs'] for c in cs) and not any(join_lines(c['lines']) for c in cs)


def build_q(q, disp=None, byline_text=None):
    """disp: number to print (default: original number). byline_text: replaces the 출제자 line."""
    n = q['n']
    dn = n if disp is None else disp
    imgq = is_image_choice(q)
    boxfirst = (bool(q['blocks']) and q['blocks'][0]['t'] == 'box'
                and any(l.strip() for l in drop(q['n'], 's0', q['blocks'][0]['lines'])))
    cls = 'q' + (' flow' if imgq else '') + (' bf' if boxfirst else '')
    # byline sits OUTSIDE .qb, so the box-first number (absolute, inside .qb) is
    # positioned from the question's own top edge, never from the byline's.
    auth = FX.get('authors')
    author = (META.get('authors', {}) if auth is None else (auth or {})).get(str(n))
    byline = f'<div class="byline">출제자 : {html.escape(author)}</div>' if author else ''
    if byline_text is not None:
        byline = f'<div class="byline">{html.escape(byline_text)}</div>' if byline_text else ''
    parts = [f'<div class="{cls}">{byline}<div class="qb">']
    if boxfirst:
        parts.append(f'<span class="num bfnum">{dn}.</span>')
    head_start = len(parts)
    first = True
    prose = set(FX.get('prose_boxes', []))
    extras = FX.get('extra_figs', {}).get(str(n), [])

    def add_text(s):
        nonlocal first
        if first and boxfirst:
            parts.append(f'<p class="stem bfstem">{text(s)}</p>')
        elif first:
            parts.append(f'<p class="stem"><span class="num">{dn}.</span> {text(s)}</p>')
        else:
            parts.append(f'<p class="stem cont">{text(s)}</p>')
        first = False

    for bi, b in enumerate(q['blocks']):
        tag = f's{bi}'
        if b['t'] == 'fig':
            parts.append(fig_box(os.path.join(FIG, b['file'])))
        elif b['t'] == 'box':
            parts.append(box_html(n, drop(n, tag, b['lines']), n in prose, spaces(n, tag)))
        else:
            lines = b['lines']
            dl = set(FX.get('drop_lines', {}).get(f'{n}/{tag}', []))
            cut = FX.get('split_box', {}).get(f'{n}/{tag}')
            segs = ([('t', 0, cut[0]), ('x', cut[0], cut[1]), ('t', cut[1], len(lines))]
                    if cut else [('t', 0, len(lines))])
            for kind, a, z in segs:
                ls = [(i, lines[i]) for i in range(a, z) if i not in dl]
                if not ls:
                    continue
                if kind == 'x':
                    idxmap = {orig: k for k, (orig, _) in enumerate(ls)}
                    bsp = {idxmap[i] for i in spaces(n, tag) if i in idxmap and i + 1 in idxmap}
                    parts.append(box_html(n, [l for _, l in ls], True, bsp)); continue
                # re-index space breaks after dropping / slicing
                idxmap = {orig: k for k, (orig, _) in enumerate(ls)}
                sp = {idxmap[i] for i in spaces(n, tag) if i in idxmap and i + 1 in idxmap}
                add_text(apply_fixes(n, 'stem', join_lines([l for _, l in ls], sp)))
        for e in extras:
            if e.get('after_block') == bi:
                parts.append(extra_fig(n, e))
    for e in extras:
        if e.get('after_block') is None:
            parts.append(extra_fig(n, e))
    if first and not boxfirst:   # a box-first question whose box is the whole stem is not empty
        parts.insert(head_start, f'<p class="stem"><span class="num">{dn}.</span> '
                                 '(문항 지문 없음 — 원본 PDF에 지문이 비어 있습니다)</p>')

    for ml in FX.get('media', {}).get(str(n), []):
        parts.append(box_html(n, [ml], False))
    if not q['choices']:
        note = FX.get('no_choice_note', {}).get(str(n), '(주관식 — 답안 서술형)')
        parts.append(f'<p class="subj">{html.escape(note)}</p></div></div>')
        return '\n'.join(parts)

    if imgq:
        parts = parts[:head_start] + ['<div class="qhead">'] + parts[head_start:] + ['</div>', '<div class="grid">']
        for i, c in enumerate(q['choices']):
            cap = f'<span class="gn">{CIRCLE[i]}</span>'
            if c.get('label'):
                cap += f' <span>{text(apply_fixes(n, f"l{i+1}", c["label"]))}</span>'
            imgs = ''.join(grid_img(os.path.join(FIG, f)) for f in c['figs'])
            parts.append(f'<div class="cell"><div class="gcap">{cap}</div>{imgs}</div>')
        parts.append('</div></div></div>')
        return '\n'.join(parts)

    parts.append('<ol class="ch">')
    rg = FX.get('regroup', {}).get(str(n), {})
    for i, c in enumerate(q['choices']):
        idx = i + 1
        lines = drop(n, f'c{idx}', rg.get(str(idx), c['lines']))
        s = apply_fixes(n, f'c{idx}', join_lines(lines, spaces(n, f'c{idx}')))
        inner = f'<span class="cn">{CIRCLE[i]}</span>' + text(s)
        if c.get('label'):
            inner += ' ' + text(apply_fixes(n, f'l{idx}', c['label']))
        for f in c['figs']:
            inner += fig_box(os.path.join(FIG, f))
        parts.append(f'<li>{inner}</li>')
    parts.append('</ol></div></div>')
    return '\n'.join(parts)


FAM = f"'{FAMILY}',serif"
CSS = f"""
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:{FAM}; color:#000; font-size:{pt(11)}; line-height:1.45; }}
h1 {{ font-family:{FAM}; font-weight:bold; font-size:{pt(21)}; text-align:center; margin:0 0 {mm(1.5)} 0; }}
.sub {{ font-size:{pt(10.5)}; color:#777; text-align:center; margin:0 0 {mm(7)} 0; }}
.q {{ page-break-inside:avoid; margin:0 0 {mm(6.2)} 0; }}
.q.flow {{ page-break-inside:auto; page-break-before:always; }}
.qb {{ position:relative; }}
.byline {{ font-size:{pt(8)}; line-height:1.2; color:#777; margin:0 0 {mm(BYLINE_GAP)} 0; }}
.q.bf .byline {{ margin-bottom:{mm(BYLINE_GAP_BF)}; }}
.stem {{ font-weight:bold; font-size:{pt(12)}; margin:0 0 {mm(2.2)} 0; text-align:justify;
         padding-left:{mm(7.6)}; text-indent:-{mm(7.6)}; }}
.stem.cont {{ margin-top:{mm(1.6)}; text-indent:0; }}
.stem.bfstem {{ padding-left:0; text-indent:0; }}
.num {{ color:#1a4f8a; font-weight:bold; }}
.bfnum {{ position:absolute; left:0; top:{mm(BOX_PAD_V)}; font-size:{pt(12)}; line-height:{pt(11 * 1.45)}; }}
.q.bf .box, .q.bf .stem.bfstem, .q.bf .figwrap {{ margin-left:{mm(7.6)}; }}
ol.ch {{ list-style:none; margin:0; padding:0; }}
ol.ch li {{ font-size:{pt(11)}; font-weight:400; padding-left:{mm(6.4)}; text-indent:-{mm(6.4)};
            margin:0 0 {mm(1.0)} 0; text-align:justify; }}
.cn {{ display:inline-block; width:{mm(6.4)}; text-indent:0; }}
.subj {{ font-size:{pt(11)}; color:#555; margin:{mm(1)} 0 0 {mm(7.6)}; }}
.box {{ border:0.4pt solid #cfcfcf; background:#f4f4f4; border-radius:{mm(0.8)};
        padding:{mm(BOX_PAD_V)} {mm(3.2)}; margin:0 0 {mm(2.4)} 0; page-break-inside:avoid; }}
.box p {{ font-size:{pt(11)}; font-weight:400; color:#333; margin:0; text-indent:-{mm(2.6)};
          padding-left:{mm(2.6)}; text-align:justify; }}
.box p.pp {{ text-indent:0; padding-left:0; }}
.box p.pp + p.pp {{ margin-top:{mm(1.6)}; }}
.figwrap {{ text-align:center; margin:{mm(2.0)} 0; text-indent:0; }}
.figwrap img, .gimg img {{ display:inline-block; }}
sup {{ font-size:70%; line-height:0; vertical-align:super; }}
sub {{ font-size:70%; line-height:0; vertical-align:sub; }}
.qhead {{ page-break-inside:avoid; page-break-after:avoid; }}
.grid {{ font-size:0; }}
.cell {{ display:inline-block; vertical-align:top; width:49.5%; page-break-inside:avoid;
         margin:0 0 {mm(3)} 0; text-align:center; }}
.gcap {{ font-size:{pt(11)}; text-align:left; margin:0 0 {mm(1)} {mm(2)}; }}
.gn {{ font-size:{pt(12)}; }}
"""


def main():
    title = FX.get('title') or META['title'] or '기출문제'
    date = FX.get('date') or META['date'] or ''
    sub = f'시험일 : {date} · 총 {len(P)}문항 · 문제만 수록 (정답 표시 없음)'
    body = '\n'.join(build_q(q) for q in P)
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
           f'<h1>{html.escape(title)}</h1><div class="sub">{html.escape(sub)}</div>{body}</body></html>')
    total = render_pdf(doc, WORK, OUT, title)
    verify(doc, WORK, OUT, total, [q['n'] for q in P])


MARGIN_PT = 11 / 25.4 * 72      # top/bottom page margin passed to wkhtmltopdf
KEEP_PASSES = 30   # re-render passes; each fixes the first split question of every page-break segment


def _splits(raw, n_q):
    """wkhtmltopdf ignores `page-break-inside:avoid` when the page boundary falls inside a
    figure, so a question that would fit on one page can still start at the bottom of a page
    and continue on the next. Returns the 0-based indices of such questions, in order."""
    import pymupdf
    d = pymupdf.open(raw)
    ph = d[0].rect.height
    usable = ph - 2 * MARGIN_PT
    pages, starts = [], []
    for k, p in enumerate(d):
        items = []        # (top, bottom, is_heading): headings = numbers, bylines, year/lecture titles
        for b in p.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for l in b['lines']:
                for s_ in l['spans']:
                    t = s_['text'].strip()
                    if not t:
                        continue
                    head = s_['color'] in (0x1a4f8a, 0x777777) or s_['size'] >= 18
                    items.append((s_['bbox'][1], s_['bbox'][3], head))
                    if s_['color'] == 0x1a4f8a and re.match(r'^\d{1,3}\.$', t):
                        starts.append((k, s_['bbox'][1]))
        items += [(im['bbox'][1], im['bbox'][3], False) for im in p.get_image_info()]
        pages.append(items)
    out = []
    if len(starts) != n_q:            # numbers not recognised reliably -> leave the layout alone
        return out
    for i, (k, y) in enumerate(starts):
        top = y - 22                  # room for the byline above the number
        if top < MARGIN_PT + 12 or k + 1 >= len(pages):
            continue                  # already at the top of a page, or last page
        nk, ny = starts[i + 1] if i + 1 < len(starts) else (len(pages), 0)
        if nk == k:                   # ends on its own page
            continue
        first = max(b for a, b, h in pages[k] if a >= y - 30) - top    # its height on this page
        if nk > k + 2 or (nk == k + 2 < len(pages) and any(b <= ny - 20 and not h for a, b, h in pages[nk])):
            # runs over three pages: taller than a page anyway, but don't start it with a
            # few stem lines at the foot of a page
            if first < 0.35 * usable:
                out.append(i)
            continue
        lim = ny - 20 if nk == k + 1 else ph
        spill = [b for a, b, h in pages[k + 1] if b <= lim and not h]   # headings belong to what follows
        if not spill:
            continue
        need = first + (max(spill) - MARGIN_PT)
        if need < usable - 12 or first < 0.35 * usable:
            out.append(i)
    return out


PB = '<div style="page-break-before:always"></div>'
YR = '<h2 class="yr"'     # year header of the lecture PDFs (tools/build_lectures.py)


def _stranded(raw, n_h):
    """0-based indices of year headers left as the last thing on their page
    (wkhtmltopdf ignores page-break-after:avoid when it moves the next question on)."""
    import pymupdf
    d = pymupdf.open(raw)
    out, j = [], -1
    for p in d:
        spans = [(s_['bbox'][1], s_['bbox'][3], s_['text'].strip(), s_['color'])
                 for b in p.get_text('dict')['blocks'] if b['type'] == 0
                 for l in b['lines'] for s_ in l['spans'] if s_['text'].strip()]
        imgs = [im['bbox'][1] for im in p.get_image_info()]
        for y0, y1, t, c in sorted(spans):
            if c == 0x1a4f8a and re.match(r'^\d{4}년', t):
                j += 1
                if not any(a > y1 + 1 for a, _, _, _ in spans) and not any(a > y1 for a in imgs):
                    out.append(j)
    return out if j + 1 == n_h else []


def _h2_break(doc, j):
    """Page break before the j-th year header (None if one is already there)."""
    at = list(re.finditer(re.escape(YR), doc))[j].start()
    before = doc[:at].rstrip()
    if before.endswith(PB) or doc.startswith(YR + ' style="page-break-before', at):
        return None
    return doc[:at] + PB + doc[at:]


def _break_before(doc, i):
    """Force a page break before the i-th question div (or the year header right above it).
    Returns None when that would only strand a lecture title or repeat a break."""
    ms = list(re.finditer(r'<div class="q[ "]', doc))
    at = ms[i].start()
    h2 = doc.rfind('<h2 class="yr"', 0, at)
    if h2 != -1 and re.fullmatch(r'\s*', re.sub(r'<h2 class="yr".*?</h2>', '', doc[h2:at], flags=re.S)):
        at = h2
    before = doc[:at].rstrip()
    if before.endswith(PB) or before.endswith('</div>') and re.search(r'<div class="sub">[^<]*</div>$', before):
        return None
    return doc[:at] + PB + doc[at:]


def render_pdf(doc, work, out, title):
    """HTML -> wkhtmltopdf -> 'n / N' page numbers. Returns page count."""
    doc, left = glyph_safe(doc)
    if left:
        print(f"note: font lacks {''.join(left)} -> drawn with a fallback font")
    hp = os.path.join(work, 'worksheet.html')
    raw = os.path.join(work, 'raw.pdf')
    n_q = len(re.findall(r'<div class="q[ "]', doc))
    pushed = 0
    for npass in range(KEEP_PASSES + 1):
        open(hp, 'w', encoding='utf-8').write(doc)
        subprocess.run(['wkhtmltopdf', '--enable-local-file-access', '-q', '--page-size', 'A4',
                        '-T', '11mm', '-B', '11mm', '-L', '12mm', '-R', '12mm', hp, raw],
                       check=True, stderr=subprocess.DEVNULL)
        if npass == KEEP_PASSES:
            break
        # a push only moves content up to the next forced page break, so the first split of
        # every such segment (lecture section, pushed question, image grid) can be fixed per pass
        hard = [m.start() for m in re.finditer(r'<div class="lect">|<div class="q flow|' + re.escape(PB), doc)]
        qpos = [m.start() for m in re.finditer(r'<div class="q[ "]', doc)]
        hpos = [m.start() for m in re.finditer(re.escape(YR), doc)]
        acts = sorted([(qpos[i], _break_before, i) for i in _splits(raw, n_q)]
                      + [(hpos[j], _h2_break, j) for j in (_stranded(raw, len(hpos)) if hpos else [])],
                      key=lambda t: t[0])
        done, new = set(), doc
        for pos, fn, idx in acts:
            seg = sum(1 for h in hard if h <= pos)
            if seg in done:
                continue
            nxt = fn(new, idx)
            if nxt:
                new = nxt; done.add(seg); pushed += 1
        if new == doc:
            break
        doc = new
    if pushed:
        print(f'keep-together: {pushed} question(s)/year header(s) moved to a new page')

    # page numbers (trailing empty pages from the last question's bottom margin are dropped)
    import pymupdf
    rd = pymupdf.open(raw)
    last = len(rd)
    while last > 1 and not rd[last - 1].get_text().strip() and not rd[last - 1].get_image_info():
        last -= 1
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.units import mm as MM
    pdfmetrics.registerFont(TTFont('PN', os.path.expanduser(f'~/.fonts/{FAMILY}-Regular.ttf')))
    src = PdfReader(raw); w = PdfWriter(); total = last
    for i, page in enumerate(src.pages[:last], 1):
        pw, ph = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(pw, ph))
        c.setFont('PN', 9); c.setFillGray(0.4); c.drawCentredString(pw / 2, 5.5 * MM, f'{i} / {total}')
        c.save(); buf.seek(0); page.merge_page(PdfReader(buf).pages[0]); w.add_page(page)
    w.add_metadata({'/Title': f'{title} — 문제'})
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    buf = io.BytesIO(); w.write(buf)
    with open(out, 'wb') as f:
        f.write(_stable_font_tags(buf.getvalue()))
    return total


def _stable_font_tags(data):
    """wkhtmltopdf names font subsets with a random 6-letter tag (QFHAAA+GichulTT-Bold), so the
    same document came out with different bytes every build. Renumber the tags in order of first
    appearance (same length, so xref offsets stay valid): unchanged content -> identical file,
    which keeps git from storing a new copy of every PDF on each rebuild."""
    seen = {}

    def tag(m):
        t = m.group(1)
        if t not in seen:
            i = len(seen); s_ = ''
            for _ in range(6):
                s_ = chr(65 + i % 26) + s_; i //= 26
            seen[t] = s_.encode()
        return b'/' + seen[t] + b'+'
    return re.sub(rb'/([A-Z]{6})\+', tag, data)


def verify(doc, work, out, total, numbers, report_fixes=True):
    """Checks on the finished PDF; `numbers` = question numbers that must appear."""
    import pymupdf
    d = pymupdf.open(out)
    txt = '\n'.join(p.get_text() for p in d)
    fonts = sorted({f[3].split('+')[-1] for p in d for f in p.get_fonts()})
    leaks = [txt[max(0, m.start() - 25):m.end() + 10].replace('\n', ' ')
             for m in re.finditer(r'정답|해설|오답노트|복수정답', txt)]
    leaks = [l for l in leaks if '정답 표시 없음' not in l]
    found = {int(x) for x in re.findall(r'^(\d{1,3})\.\s', txt, re.M)}
    missing = sorted(set(numbers) - found)
    html_leak = re.findall(r'ⓘ|오답노트|해설', re.sub(r'<div class="sub">.*?</div>', '', doc))
    os.makedirs(os.path.join(work, 'pv'), exist_ok=True)
    for f_ in os.listdir(os.path.join(work, 'pv')):
        os.remove(os.path.join(work, 'pv', f_))
    for i, p in enumerate(d):
        p.get_pixmap(dpi=96).save(os.path.join(work, 'pv', f'{i+1:02d}.png'))
    ok = (FAMILY + '-Bold' in fonts and FAMILY + '-Regular' in fonts) and not missing and not leaks and not html_leak
    print(f'output: {out}  pages: {total}')
    print(f"[{'OK' if FAMILY + '-Bold' in fonts and FAMILY + '-Regular' in fonts else 'FAIL'}] text layer fonts: {fonts}")
    print(f"[{'OK' if not missing else 'FAIL'}] question numbers in PDF text: {len(found)} (missing {missing})")
    print(f"[{'OK' if not leaks and not html_leak else 'FAIL'}] answer-leak scan: {leaks + html_leak or 'clean'}")
    # byline -> question-number gap must be the same for plain and box-first questions
    gaps = []
    for p in d:
        spans = sorted(((s_['bbox'][1], s_['bbox'][3], s_['text'].strip(), s_['color'])
                        for b in p.get_text('dict')['blocks'] if b['type'] == 0
                        for l in b['lines'] for s_ in l['spans'] if s_['text'].strip()))
        for i, sp in enumerate(spans):
            if sp[2].startswith('출제자'):
                nxt = next((x for x in spans[i + 1:] if re.match(r'^\d{1,3}\.$', x[2]) and x[3] == 0x1a4f8a), None)
                if nxt:
                    gaps.append((round(nxt[0] - sp[1], 1), nxt[2]))
    if gaps:
        lo, hi = min(g for g, _ in gaps), max(g for g, _ in gaps)
        odd = [q for g, q in gaps if abs(g - sorted(x for x, _ in gaps)[len(gaps) // 2]) > 1.0]
        print(f"[{'OK' if hi - lo <= 1.0 else 'FAIL'}] byline->number gap: {lo}-{hi} pt over {len(gaps)} bylines"
              + (f'  !! off: {odd}' if odd else ''))
    if not report_fixes:
        print(f'previews: {work}/pv/NN.png')
        return ok
    seen = sorted(set(APPLIED))
    unapplied = [f for f in FX.get('fixes', []) if (f[0], f[4]) not in seen]
    print(f'fixes applied: {len(seen)}' + (f'  !! NOT APPLIED (old text not found): {unapplied}' if unapplied else ''))
    for q, note in seen:
        print(f'  {q}번: {note}')
    print(f'previews: {work}/pv/NN.png  -> look at them before delivering')
    return ok


if __name__ == '__main__':
    load(sys.argv[1]); OUT = sys.argv[2]
    main()
