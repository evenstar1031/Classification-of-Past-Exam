#!/usr/bin/env python3
"""본1 1학기 강의 및 실습 교육계획표(HWP, 2023~2026) → 앱 「1학기 계획서」 탭 데이터.

  pip install pyhwp beautifulsoup4 lxml
  python3 tools/sem1_plan_from_hwp.py <HWP가 있는 폴더> [--inject]

폴더 안의 HWP 파일 이름에 연도(2023 …)가 들어 있어야 한다. HWP 원본(교수 연락처·메일 포함)은 저장소에 올리지 않는다.
결과: app/sem1_plan.json, --inject 를 주면 app/app.html 의 `/*SEM1PLAN:start*/ … /*SEM1PLAN:end*/` 사이도 바꾼다.

과목마다 뽑는 것
  · 교육과정표: 책임/부책임교수, 강의기간, 학점, 이론·실습 시수
  · 주간 시간표: 시험·총괄평가 날짜, 교수별 강의 시수(휴일·시험 제외, 3명 이상이 함께 하는 실습은 뺌, 2명이면 반씩)
수업 한 줄씩의 비교는 하지 않는다(연도마다 단원 이름이 달라 맞추기 어렵고, 자세할 필요가 없다고 했음).
"""
import datetime as dt, json, re, shutil, subprocess, sys, tempfile, warnings
from collections import OrderedDict
from pathlib import Path

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parent.parent
YEARS = (2023, 2024, 2025, 2026)
COURSES = [  # key, 탭 이름
    ('physio', '생리학'), ('anat', '해부학'), ('immu', '면역학'), ('patho', '병리학'),
    ('micro', '병원체학'), ('pharm', '약리학 총론'), ('final', '기초의학종합'),
]
KEYS = (('생리학', 'physio'), ('해부학', 'anat'), ('면역학', 'immu'), ('병리학', 'patho'),
        ('병원체학', 'micro'), ('약리학', 'pharm'), ('기초의학종합', 'final'))
WD = '월화수목금토일'
NOT_LECTURE = re.compile(r'공휴일|삼일절|어린이날|현충일|광복절|지방선거|석가탄신일|행운제|체육대회|개천절|한글날|추석|설날|성탄절|휴강')
EXAM = re.compile(r'시험|총괄평가|종합평가')
SKIP_EXAM = re.compile(r'피드백|feedback|형성평가|실습\s*시험|Tagging', re.I)


def sq(s): return re.sub(r'\s+', ' ', s).strip()


def hwp_to_xhtml(hwp, out):
    subprocess.run(['hwp5html', '--output', str(out), str(hwp)], check=True, capture_output=True)
    return out / 'index.xhtml'


def load_tables(xhtml):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(Path(xhtml).read_text('utf-8'), 'lxml')
    return [t for t in soup.find_all('table') if not t.find_parent('table')]


def txt(t): return sq(t.get_text(' ', strip=True))
def rows_of(t): return [[sq(c.get_text(' ', strip=True)) for c in tr.find_all(['td', 'th'], recursive=False)] for tr in t.find_all('tr')]


def ckey(name):
    n = re.sub(r'\s+', '', name)
    for k, key in KEYS:
        if k in n: return key


def curriculum(y, top):
    for t in top:
        if f'{y}학년도 의과대학 의학과 1학년 교육과정' in txt(t)[:60]:
            out = {}
            for r in rows_of(t)[3:]:
                if r and r[0] == '2': break
                r2 = r[1:] if r[0] == '1' else r
                if len(r2) < 8: continue
                name, code, cr, th, pr, period, dept, prof = r2[:8]
                k = ckey(name)
                if not k: continue
                m = re.findall(r'(\d+)\.\s*(\d+)\.', period)
                out[k] = dict(code=code, credit=int(cr), theory=int(th), prac=int(pr),
                              lead=re.sub(r'\s*,\s*', ', ', re.sub(r'\s*/\s*', ' / ', prof.strip())),
                              start=(int(m[0][0]), int(m[0][1])) if m else None,
                              end=(int(m[1][0]), int(m[1][1])) if len(m) > 1 else None)
            return out
    raise SystemExit(f'{y}: 교육과정표를 찾지 못함')


def weeks(y, top):
    items = []
    for t in top:
        if not re.match(r'^\d+(,\s*\d+)?\s*월\s*(\d+\s*)?주', txt(t)): continue
        trs = t.find_all('tr')

        def row(tr): return [(sq(c.get_text(' ', strip=True)), int(c.get('colspan') or 1)) for c in tr.find_all(['td', 'th'], recursive=False)]
        hdr = row(trs[1])
        if hdr[0][0] != '시간 날짜': continue
        pc, g = [], hdr[0][1]
        for _, sp in hdr[1:]:
            pc.append((g, g + sp)); g += sp
        i = 3
        while i < len(trs):
            r = row(trs[i])
            if len(r) >= 2 and re.match(r'^[월화수목금토일]$', r[0][0]) and re.match(r'^\d+/\s*\d+$', r[1][0]):
                mo, d = map(int, re.findall(r'\d+', r[1][0]))
                date = dt.date(y, mo, d)
                tops, g = [], 2
                for lab, sp in r[2:]:
                    tops.append((g, g + sp, lab)); g += sp
                profs = {}
                if i + 1 < len(trs):
                    r2 = row(trs[i + 1])
                    if not (len(r2) >= 2 and re.match(r'^[월화수목금토일]$', r2[0][0])):
                        g = 2
                        for lab, sp in r2: profs[g] = lab; g += sp
                        i += 1
                for a, b, lab in tops:
                    if not lab: continue
                    hours = len([1 for (s, e) in pc if s < b and e > a])
                    items.append(dict(date=date, hours=hours, topic=lab, prof=profs.get(a, '')))
            i += 1
    return items


def assign(y, cur, items):
    out = {k: [] for k in cur}
    for it in items:
        ks = [k for k, c in cur.items() if c['start'] and c['end'] and dt.date(y, *c['start']) <= it['date'] <= dt.date(y, *c['end'])]
        if len(ks) == 1: out[ks[0]].append(it)
    return out


def names_of(s):
    out = []
    for p in re.split(r'[,/·]|\s{2,}', s):
        p = re.sub(r'\(.*?\)', '', p)
        p = re.sub(r'\s+[A-Z가-힣]?$', lambda m: '' if re.fullmatch(r'\s+[A-Z]', m.group(0)) else m.group(0), p).strip()
        p = p.replace('.', ' ')
        for q in p.split():
            if re.fullmatch(r'[가-힣]{2,4}', q) and q not in ('방문교수', '조별', '교수', '전임의', '담당교수', '미정'): out.append(q)
    seen = []
    [seen.append(n) for n in out if n not in seen]
    return seen


def unit(topic):
    t = sq(topic)
    t = re.sub(r'\[\s*([^\]]*?)\s*\]', r'\1', t)
    t = re.sub(r'\(\s*\d+\s*/\s*\d+\s*\)', '', t)
    if re.match(r'^해부학\s*\(?\d+\)?\s*[:：]', t) or re.match(r'^해부학\s*실습\s*\(\d+\)', t): return '카데바 해부 실습'
    if re.match(r'^육안 해부 실습', t): return '카데바 해부 실습'
    t = re.sub(r'\s*[-–]\s*(\d+|[ⅠⅡⅢ]+)\s*$', '', t)
    t = re.sub(r'\s*[-–]\s*실습\s*[-–]?\s*\d*\s*$', ' 실습', t)
    t = re.sub(r'\s*\(\s*\d+\s*\)\s*$', '', t)
    t = re.sub(r'\s*\(.*$', '', t) if len(t) > 22 else t
    return t.strip(' :-')


def md(d): return f'{d.month}/{d.day}({WD[d.weekday()]})'


def build(folder):
    folder = Path(folder)
    per = {}
    tmp = Path(tempfile.mkdtemp(prefix='hwp-'))
    for y in YEARS:
        f = next((p for p in folder.glob('*.hwp') if str(y) in p.name), None)
        if not f: raise SystemExit(f'{y}년 HWP를 찾지 못함 ({folder})')
        x = hwp_to_xhtml(f, tmp / str(y))
        top = load_tables(x)
        cur = curriculum(y, top)
        per[y] = (cur, assign(y, cur, weeks(y, top)))
    shutil.rmtree(tmp, ignore_errors=True)

    courses = []
    for key, tab in COURSES:
        c = {'id': key, 'tab': tab, 'y': {}, 'profs': []}
        pm = OrderedDict()
        for y in YEARS:
            cur, asg = per[y]
            cc = cur[key]
            c.setdefault('code', cc['code']); c.setdefault('credit', cc['credit'])
            exams, seen = [], set()
            for it in asg[key]:
                if EXAM.search(it['topic']) and not SKIP_EXAM.search(it['topic']):
                    lab = unit(re.sub(r'\(.*?\)', '', it['topic']))[:16] or '시험'
                    k = (it['date'], lab)
                    if k not in seen: seen.add(k); exams.append([md(it['date']), lab])
                    continue
                if NOT_LECTURE.search(it['topic']) or not it['prof']: continue
                if EXAM.search(it['topic']) or re.search(r'오리엔|종강|추모|Tagging', it['topic']) and key != 'anat': continue
                ns = names_of(it['prof'])
                if not ns or len(ns) > 2: continue
                for n in ns:
                    d = pm.setdefault(n, {}).setdefault(y, {'h': 0.0, 'u': {}})
                    share = it['hours'] / len(ns)
                    d['h'] += share
                    u = unit(it['topic'])
                    d['u'][u] = d['u'].get(u, 0) + share
            c['y'][str(y)] = dict(
                lead=cc['lead'], theory=cc['theory'], prac=cc['prac'],
                period=f"{cc['start'][0]}/{cc['start'][1]} ~ {cc['end'][0]}/{cc['end'][1]}",
                exams=exams[:6])
        for n, ys in pm.items():
            row = {'n': n, 'y': {}}
            for y, d in ys.items():
                top3 = [u for u, _ in sorted(d['u'].items(), key=lambda kv: -kv[1])[:3]]
                row['y'][str(y)] = {'h': round(d['h'] * 2) / 2, 'u': top3}
            c['profs'].append(row)
        c['profs'].sort(key=lambda r: (-(r['y'].get('2026', {}).get('h', 0)), -sum(v['h'] for v in r['y'].values()), r['n']))
        courses.append(c)
    return {'years': list(YEARS), 'courses': courses}


def main():
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    data = build(a[0])
    out = ROOT / 'app' / 'sem1_plan.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', 'utf-8')
    print('wrote', out)
    if '--inject' in a:
        p = ROOT / 'app' / 'app.html'
        s = p.read_text('utf-8')
        m = re.search(r'/\*SEM1PLAN:start\*/.*?/\*SEM1PLAN:end\*/', s, re.S)
        if not m: raise SystemExit('app.html 에 SEM1PLAN 표시가 없음')
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        s = s[:m.start()] + '/*SEM1PLAN:start*/const SEM1PLAN=' + body + ';/*SEM1PLAN:end*/' + s[m.end():]
        p.write_text(s, 'utf-8')
        print('app.html 에 넣음')


if __name__ == '__main__':
    main()
