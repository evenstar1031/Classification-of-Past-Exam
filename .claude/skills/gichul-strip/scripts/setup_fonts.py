#!/usr/bin/env python3
"""Install the exam font (any Korean font: one regular + one bold file) for wkhtmltopdf.

wkhtmltopdf draws @font-face webfonts and CFF-flavoured OTF fonts as vector
outlines, so the PDF ends up with no text layer (unsearchable, and the final
answer-leak scan can't run).  The two files are therefore converted to TrueType
outlines (if needed) and registered under one internal family name, GichulTT,
which build.py and the worksheet template use.

Which file is which is decided from the file name:
  bold    = name contains bold / semibold / demibold / extrabold / heavy / black
  regular = everything else (medium preferred over regular/book; light/thin avoided)
e.g. AppleSDGothicNeo-Medium.ttf + AppleSDGothicNeo-SemiBold.ttf,
     KoPubWorld Batang Pro Medium.otf + KoPubWorld Batang Pro Bold.otf

usage: setup_fonts.py [FONT_DIR]   (default: fonts)
"""
import glob, os, re, shutil, subprocess, sys

FAMILY = 'GichulTT'
FONTDIR = os.path.expanduser('~/.fonts')


def need(pkg, mod=None):
    try:
        __import__(mod or pkg)
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', pkg,
                        '--break-system-packages', '-q'], check=True)


def otf2ttf(src, dst, style):
    from fontTools.ttLib import TTFont, newTable
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    f = TTFont(src)
    if 'CFF ' in f:
        gs, order = f.getGlyphSet(), f.getGlyphOrder()
        glyf = newTable('glyf'); glyf.glyphOrder = order; glyf.glyphs = {}
        for name in order:
            pen = TTGlyphPen(gs)
            try:
                gs[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
            except Exception:
                pass
            glyf.glyphs[name] = pen.glyph()
        f['glyf'] = glyf; f['loca'] = newTable('loca')
        maxp = newTable('maxp'); maxp.tableVersion = 0x00010000
        for k in ('maxZones', 'maxTwilightPoints', 'maxStorage', 'maxFunctionDefs',
                  'maxInstructionDefs', 'maxStackElements', 'maxSizeOfInstructions',
                  'maxComponentElements'):
            setattr(maxp, k, 0)
        maxp.maxZones = 1
        f['maxp'] = maxp
        f['head'].indexToLocFormat = 0; f['head'].glyphDataFormat = 0
        del f['CFF ']
        if 'VORG' in f:
            del f['VORG']
        f['post'].formatType = 3.0
        f.sfntVersion = '\x00\x01\x00\x00'
    for r in f['name'].names:
        if r.nameID in (1, 16, 21):
            r.string = FAMILY
        elif r.nameID in (2, 17, 22):
            r.string = style
        elif r.nameID == 4:
            r.string = f'{FAMILY} {style}'
        elif r.nameID == 6:
            r.string = f'{FAMILY}-{style}'
    bold = style == 'Bold'
    f['OS/2'].usWeightClass = 700 if bold else 400
    f['OS/2'].fsSelection = (f['OS/2'].fsSelection & ~0b1100001) | (0b100000 if bold else 0b1000000)
    f['head'].macStyle = 1 if bold else 0
    f.save(dst)


BOLD = ('extrabold', 'semibold', 'demibold', 'ultrabold', 'bold', 'heavy', 'black')
REG_PREF = ('medium', 'regular', 'book', 'normal', 'roman')
THIN = ('extralight', 'ultralight', 'light', 'thin', 'hairline')


def weight_of(base):
    key = re.sub(r'[^a-z]', '', base.lower())
    for w in BOLD:
        if w in key:
            return 'Bold', w, key.replace(w, '')
    for w in REG_PREF + THIN:
        if w in key:
            return 'Regular', w, key.replace(w, '')
    return 'Regular', '', key


def main():
    up = sys.argv[1] if len(sys.argv) > 1 else 'fonts'
    need('fonttools', 'fontTools'); need('pymupdf'); need('pypdf'); need('reportlab')
    os.makedirs(FONTDIR, exist_ok=True)
    files = [p for p in glob.glob(os.path.join(up, '*')) if p.lower().endswith(('.otf', '.ttf'))]
    if not files:
        sys.exit(f'!! {up}/ 에 폰트 파일(.otf/.ttf)이 없습니다. 보통체 1개 + 굵은체 1개를 올려 주세요.')
    cand = {'Regular': [], 'Bold': []}
    fams = set()
    for p in files:
        role, w, fam = weight_of(os.path.basename(os.path.splitext(p)[0]))
        fams.add(re.sub(r'\d+$', '', fam))
        cand[role].append((p, w))
    if len(fams) > 1:
        sys.exit('!! fonts/ 에 서로 다른 폰트가 섞여 있습니다. 한 가지 폰트의 보통체+굵은체 두 파일만 남겨 주세요:\n   '
                 + '\n   '.join(os.path.basename(p) for p in sorted(files)))
    order = {'Regular': REG_PREF + ('',) + THIN, 'Bold': ('bold', 'semibold', 'demibold', 'extrabold', 'ultrabold', 'heavy', 'black')}
    found = {}
    for role, lst in cand.items():
        if lst:
            found[role] = sorted(lst, key=lambda t: order[role].index(t[1]) if t[1] in order[role] else 99)[0][0]
    if len(found) < 2:
        sys.exit(f'!! 보통체와 굵은체가 둘 다 필요합니다 (파일 이름에 Bold/SemiBold 가 들어간 굵은체). 찾은 것: '
                 + str({k: os.path.basename(v) for k, v in found.items()}))
    for role, p in found.items():
        print(f'{role:7s} <- {os.path.basename(p)}')
    for old in glob.glob(os.path.join(FONTDIR, f'{FAMILY}-*.ttf')):
        os.remove(old)
    for style, src in found.items():
        otf2ttf(src, os.path.join(FONTDIR, f'{FAMILY}-{style}.ttf'), style)
    subprocess.run(['fc-cache', '-f'], check=True, capture_output=True)
    out = subprocess.run(['fc-list'], capture_output=True, text=True).stdout
    ok = [l for l in out.splitlines() if FAMILY in l]
    print('\n'.join(ok))
    if len(ok) < 2:
        sys.exit('TT family not registered')
    # glyph coverage report for characters the builder uses
    from fontTools.ttLib import TTFont
    cm = TTFont(os.path.join(FONTDIR, f'{FAMILY}-Regular.ttf')).getBestCmap()
    chars = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫²³⁺⁻₀₁₂₃₄₅öé×−℃·→↑↓'
    missing = [c for c in chars if ord(c) not in cm]
    print('missing glyphs (build.py substitutes sub/superscripts, · and − automatically; others fall back to a system font):',
          ''.join(missing) or 'none')


if __name__ == '__main__':
    main()
