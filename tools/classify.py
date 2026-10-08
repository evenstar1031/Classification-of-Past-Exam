#!/usr/bin/env python3
"""기출 문항 → 수업 분류.

  classify.py auto  <과목> <시험id>            출제자+연도로 자동 분류 (직접 정한 것은 보존)
  classify.py show  <과목> <시험id> [--all]     확인이 필요한 문항을 지문과 함께 출력
  classify.py set   <과목> <시험id> 12=09 13=09 [--why "근거"]   수업 직접 지정 (99 = 기타)
  classify.py check <과목> [<시험id>]          빠진 문항 없는지 + 수업별 문항 수 표

입력: work/<시험id>/meta.json, parsed.json, fixes.json (gichul-strip extract 결과)
      과목정보/<과목>.json
출력: 분류/<과목>/<시험id>.json

분류 근거(by):
  출제자        그 해 담당교수 목록과 출제자가 정확히 한 수업에서 일치
  출제자-이어짐  이 문항엔 출제자 표시가 없어 바로 앞 문항의 출제자를 이어받음 → 내용 확인 필요
  미정          후보가 여러 개거나 없음 → Claude가 내용을 보고 `set` 으로 정함
  내용 / 직접    Claude(내용 판단) 또는 사용자가 정한 것 — auto 를 다시 돌려도 유지됨
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME_RE = re.compile(r'[가-힣]{2,4}')
KEEP = {'내용', '직접'}
OTHER = {'id': '99', 'name': '기타 (수업 특정 불가)'}


def info(subj):
    p = os.path.join(ROOT, '과목정보', f'{subj}.json')
    if not os.path.exists(p):
        sys.exit(f'과목정보/{subj}.json 이 없습니다. 있는 과목: '
                 + ', '.join(f[:-5] for f in sorted(os.listdir(os.path.join(ROOT, '과목정보'))) if f.endswith('.json')))
    return json.load(open(p, encoding='utf-8'))


def lect_map(inf):
    m = {L['id']: L for L in inf['lectures']}
    m[OTHER['id']] = OTHER
    return m


def out_path(subj, exam):
    return os.path.join(ROOT, '분류', subj, f'{exam}.json')


def load_out(subj, exam):
    p = out_path(subj, exam)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def save_out(subj, exam, d):
    p = out_path(subj, exam)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def names(author):
    a = re.sub(r'교수님?|선생님?', ' ', author or '')
    return [n for n in NAME_RE.findall(a)]


def exam_year(meta, fixes, exam):
    date = (fixes or {}).get('date') or meta.get('date') or ''
    m = re.match(r'(20\d\d)', date)
    if m:
        return int(m.group(1)), date
    m = re.search(r'(?<!\d)(2[0-9])(\d{2})(\d{2})(?!\d)', exam + ' ' + (meta.get('title') or ''))
    if m:
        return 2000 + int(m.group(1)), f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
    m = re.search(r'(20[2-3]\d)', exam + ' ' + (meta.get('title') or ''))
    if m:
        return int(m.group(1)), date
    return None, date


def candidates(inf, who, year):
    """who: list of names. returns (lecture ids, note)."""
    exam_lects = [L for L in inf['lectures'] if L.get('exam', True) and not L.get('merged_into')]
    same = [L['id'] for L in exam_lects if any(n in L['profs'].get(str(year), []) for n in who)]
    if same:
        return same, ''
    # 그 해 자료가 없거나(예: 2024) 그 해 명단에 없을 때: 가장 가까운 해의 담당 수업
    best, dist = [], None
    for L in exam_lects:
        ys = [int(y) for y, ps in L['profs'].items() if any(n in ps for n in who)]
        if not ys:
            continue
        d = min(abs(y - year) for y in ys)
        if dist is None or d < dist:
            best, dist = [L['id']], d
        elif d == dist:
            best.append(L['id'])
    if best:
        return best, f'{year}년 담당 명단엔 없음 → {dist}년 차이 나는 해의 담당 수업으로 매칭'
    return [], '수업 목록의 어느 해 담당교수와도 일치하지 않음'


def plain(lines):
    return ' '.join(l.strip() for l in lines if l.strip())


def q_text(q, width=150):
    stem = ' / '.join(plain(b['lines']) for b in q['blocks'] if b['t'] in ('text', 'box') and b.get('lines'))
    ch = ' | '.join(f'{i+1}) ' + plain(c['lines'])[:40] for i, c in enumerate(q['choices']))
    return stem[:width], ch[:width]


# ----------------------------------------------------------------- commands
def cmd_auto(a):
    inf = info(a.subject)
    work = os.path.join(ROOT, 'work', a.exam)
    meta = json.load(open(os.path.join(work, 'meta.json'), encoding='utf-8'))
    parsed = json.load(open(os.path.join(work, 'parsed.json'), encoding='utf-8'))
    fx_p = os.path.join(work, 'fixes.json')
    fixes = json.load(open(fx_p, encoding='utf-8')) if os.path.exists(fx_p) else {}
    year, date = exam_year(meta, fixes, a.exam)
    if a.year:
        year = a.year
    if not year:
        sys.exit('시험 연도를 알 수 없습니다. --year 2025 처럼 지정하세요.')
    auth = fixes.get('authors')
    authors = meta.get('authors', {}) if auth is None else (auth or {})
    old = load_out(a.subject, a.exam) or {}
    oldq = old.get('questions', {})
    src = a.source or os.path.relpath(os.path.abspath(meta.get('source', '')), ROOT)
    if not os.path.exists(os.path.join(ROOT, src)):
        alt = os.path.join('원본', a.subject, os.path.basename(src))
        if os.path.exists(os.path.join(ROOT, alt)):
            src = alt
        elif old.get('exam', {}).get('source'):
            src = old['exam']['source']
    out = {'exam': {'id': a.exam, 'subject': a.subject, 'title': fixes.get('title') or meta.get('title'),
                    'date': date, 'year': year, 'source': src},
           'questions': {}}
    prev = None
    for q in parsed:
        n = str(q['n'])
        if n in oldq and oldq[n].get('by') in KEEP:
            out['questions'][n] = oldq[n]
            prev = oldq[n].get('author') or prev
            continue
        author, by = authors.get(n), '출제자'
        if not author and prev:
            author, by = prev, '출제자-이어짐'
        if author:
            prev = author
        e = {'lecture': None, 'by': '미정', 'author': author, 'candidates': [], 'note': ''}
        if author:
            c, note = candidates(inf, names(author), year)
            e['candidates'], e['note'] = c, note
            if len(c) == 1:
                e['lecture'], e['by'] = c[0], by
            elif len(c) > 1:
                e['note'] = (note + ' / ' if note else '') + '같은 교수 담당 수업이 여러 개'
        else:
            e['note'] = '출제자 표시 없음'
        out['questions'][n] = e
    save_out(a.subject, a.exam, out)
    qs = out['questions']
    cnt = {k: sum(1 for v in qs.values() if v['by'] == k) for k in ('출제자', '출제자-이어짐', '미정', '내용', '직접')}
    print(f'{a.subject} / {a.exam}: {year}년, {len(qs)}문항 → ' + ', '.join(f'{k} {v}' for k, v in cnt.items() if v))
    print(f'저장: {os.path.relpath(out_path(a.subject, a.exam), ROOT)}')
    if cnt['미정'] or cnt['출제자-이어짐']:
        print(f'→ 다음: classify.py show {a.subject} {a.exam}  로 확인 후 set 으로 정하기')


def cmd_show(a):
    inf = info(a.subject); L = lect_map(inf)
    d = load_out(a.subject, a.exam) or sys.exit('분류 파일이 없습니다. 먼저 auto 를 돌리세요.')
    parsed = {str(q['n']): q for q in json.load(open(os.path.join(ROOT, 'work', a.exam, 'parsed.json'), encoding='utf-8'))}
    year = d['exam']['year']
    for n, e in d['questions'].items():
        if not a.all and e['by'] not in ('미정', '출제자-이어짐'):
            continue
        stem, ch = q_text(parsed[n]) if n in parsed else ('(parsed.json에 없음)', '')
        cur = f"{e['lecture']} {L.get(e['lecture'], {}).get('name', '')}" if e['lecture'] else '-'
        print(f"\n[{n}번] {e['by']} | 출제자 {e.get('author') or '없음'} | 현재 {cur}")
        if e.get('note'):
            print(f"  메모: {e['note']}")
        for c in e.get('candidates', []):
            print(f"  후보 {c} {L[c]['name']}  ({year}: {', '.join(L[c]['profs'].get(str(year), [])) or '-'})")
        print(f'  지문: {stem}')
        if ch:
            print(f'  보기: {ch}')
    print('\n수업 목록:')
    for x in inf['lectures']:
        if x.get('exam', True) and not x.get('merged_into'):
            print(f"  {x['id']} {x.get('show_name') or x['name']}  [{year}: {', '.join(x['profs'].get(str(year), [])) or '-'}]")
    print(f"  99 {OTHER['name']}")


def cmd_set(a):
    L = lect_map(info(a.subject))
    d = load_out(a.subject, a.exam) or sys.exit('분류 파일이 없습니다. 먼저 auto 를 돌리세요.')
    for pair in a.pairs:
        n, lid = pair.split('=')
        lid = lid.zfill(2)
        if lid not in L:
            sys.exit(f'수업 id {lid} 가 과목정보에 없습니다.')
        if L[lid].get('merged_into'):
            sys.exit(f"수업 {lid} 는 {L[lid]['merged_into']} 에 합쳐진 수업입니다. {L[lid]['merged_into']} 로 지정하세요.")
        if n not in d['questions']:
            sys.exit(f'{n}번 문항이 이 시험에 없습니다.')
        e = d['questions'][n]
        e['lecture'], e['by'] = lid, a.by
        if a.why:
            e['note'] = a.why
        print(f"{n}번 → {lid} {L[lid].get('show_name') or L[lid]['name']} ({a.by})")
    save_out(a.subject, a.exam, d)


def cmd_check(a):
    inf = info(a.subject); L = lect_map(inf)
    base = os.path.join(ROOT, '분류', a.subject)
    exams = [a.exam] if a.exam else sorted(f[:-5] for f in os.listdir(base) if f.endswith('.json')) if os.path.isdir(base) else []
    bad, table = [], {}
    for ex in exams:
        d = load_out(a.subject, ex)
        y = d['exam']['year']
        for n, e in d['questions'].items():
            if not e.get('lecture') or e['lecture'] not in L:
                bad.append(f'{ex} {n}번 ({e["by"]})')
            else:
                table.setdefault(e['lecture'], {}).setdefault(y, 0)
                table[e['lecture']][y] += 1
    years = sorted({y for v in table.values() for y in v}, reverse=True)
    print(f'{a.subject}: 시험 {len(exams)}개')
    print('수업'.ljust(34) + ''.join(str(y).rjust(6) for y in years) + '   합계')
    for lid in sorted(table):
        row = table[lid]
        print(f"{lid} {L[lid].get('show_name') or L[lid]['name']}"[:34].ljust(34) + ''.join(str(row.get(y, '')).rjust(6) for y in years)
              + str(sum(row.values())).rjust(7))
    print(f"[{'OK' if not bad else 'FAIL'}] 수업이 정해지지 않은 문항: {len(bad)}" + (f' → {bad}' if bad else ''))
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('auto'); p.add_argument('subject'); p.add_argument('exam')
    p.add_argument('--year', type=int); p.add_argument('--source'); p.set_defaults(f=cmd_auto)
    p = sp.add_parser('show'); p.add_argument('subject'); p.add_argument('exam')
    p.add_argument('--all', action='store_true'); p.set_defaults(f=cmd_show)
    p = sp.add_parser('set'); p.add_argument('subject'); p.add_argument('exam'); p.add_argument('pairs', nargs='+')
    p.add_argument('--why', default=''); p.add_argument('--by', default='내용', choices=['내용', '직접'])
    p.set_defaults(f=cmd_set)
    p = sp.add_parser('check'); p.add_argument('subject'); p.add_argument('exam', nargs='?'); p.set_defaults(f=cmd_check)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
