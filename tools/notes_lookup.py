#!/usr/bin/env python3
"""작년 필기본에서 문항 핵심어를 찾아, 애매한 문항을 어느 수업으로 보낼지 근거를 준다.

  python3 tools/notes_lookup.py find <과목> 용어1 용어2 ...   # 수업별 맞은 횟수 + 쪽·문맥
  python3 tools/notes_lookup.py list <과목>                   # 어느 수업에 몇 년 필기본이 있는지
  옵션: --year 2025  (기본: 올해-1 = 작년, 없는 수업은 가장 가까운 해)

필기본: 학습자료/<과목>/<id>_<수업명>/필기본/필기본_<연도>.pdf
글자 추출은 work/notes/<과목>/ 에 저장해 두고 다시 쓴다 (커밋하지 않음).
"""
import argparse, datetime, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def notes_for(subject, year):
    out = {}
    for d in sorted(glob.glob(os.path.join(ROOT, '학습자료', subject, '*', '필기본'))):
        lec = os.path.basename(os.path.dirname(d))
        have = {}
        for p in glob.glob(os.path.join(d, '필기본_*.pdf')):
            m = re.search(r'필기본_(\d{4})', os.path.basename(p))
            if m:
                have[int(m.group(1))] = p
        if not have:
            continue
        y = year if year in have else min(have, key=lambda k: (abs(k - year), -k))
        out[lec] = (y, have[y])
    return out


def pages(subject, lec, year, path):
    cache_dir = os.path.join(ROOT, 'work', 'notes', subject)
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f'{lec}_{year}.json')
    mt = os.path.getmtime(path)
    if os.path.exists(cache):
        c = json.load(open(cache, encoding='utf-8'))
        if c.get('mtime') == mt:
            return c['pages']
    import pymupdf
    doc = pymupdf.open(path)
    ps = [pg.get_text() for pg in doc]
    json.dump({'mtime': mt, 'pages': ps}, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return ps


def norm(s):
    return re.sub(r'\s+', '', s).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['find', 'list'])
    ap.add_argument('subject')
    ap.add_argument('terms', nargs='*')
    ap.add_argument('--year', type=int, default=datetime.date.today().year - 1)
    a = ap.parse_args()
    notes = notes_for(a.subject, a.year)
    if not notes:
        print(f'[없음] 학습자료/{a.subject}/*/필기본/ 에 필기본이 없다 → 일반 지식으로 판단')
        return
    if a.cmd == 'list':
        lec_dirs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, '학습자료', a.subject, '*'))
                          if os.path.isdir(p))
        for lec in lec_dirs:
            if lec in notes:
                y, p = notes[lec]
                n = len(''.join(pages(a.subject, lec, y, p)))
                print(f'{lec:34} {y}  글자 {n:6}' + ('  (글자 적음: 쪽 그림을 직접 볼 것)' if n < 6000 else ''))
            else:
                print(f'{lec:34} 필기본 없음')
        return
    if not a.terms:
        sys.exit('찾을 용어를 하나 이상 준다 (질환·병원체·약·검사 이름 등)')
    terms = [(t, norm(t)) for t in a.terms]
    rows = []
    for lec, (y, p) in notes.items():
        ps = pages(a.subject, lec, y, p)
        hits, found = [], set()
        for i, txt in enumerate(ps):
            n = norm(txt)
            got = [t for t, k in terms if k and k in n]
            if got:
                found.update(got)
                flat = re.sub(r'\s+', ' ', txt)
                k = got[0]
                j = flat.lower().find(k.lower())
                ctx = flat[max(0, j - 40): j + 60] if j >= 0 else flat[:100]
                hits.append((i + 1, got, ctx))
        if hits:
            rows.append((len(found), sum(len(h[1]) for h in hits), lec, y, hits))
    if not rows:
        print('[필기에 없음] 어느 수업 필기에도 이 용어가 없다 → 일반 지식으로 판단')
        return
    rows.sort(key=lambda r: (-r[0], -r[1]))
    print(f'용어 {len(terms)}개 · 맞은 용어 수 → 맞은 횟수 순')
    for nfound, nhit, lec, y, hits in rows[:8]:
        print(f'\n{lec}  (필기 {y}) 용어 {nfound}/{len(terms)}, {nhit}회')
        for pg, got, ctx in hits[:3]:
            print(f'   p.{pg} [{", ".join(got)}] …{ctx}…')


if __name__ == '__main__':
    main()
