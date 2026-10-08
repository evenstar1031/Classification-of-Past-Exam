#!/usr/bin/env python3
"""과목별 3개년 비교 HTML → 과목정보/<과목>.json (수업 목록 + 연도별 담당교수).

usage: python3 tools/make_subject_info.py [과목정보/본1-2학기_3개년비교.html]

HTML 안의 <script>에 들어 있는 COURSES 데이터를 node로 평가해서 꺼낸다.
이미 있는 과목정보 JSON의 수업 id·keywords·memo·exam·show_name·merged_into 는 수업 이름이 같으면
그대로 유지하고, 과목의 file_marks 도 유지한다 (새 학년도 비교 파일로 다시 돌려도 분류 기록이 깨지지 않게).
"""
import glob, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, '과목정보')
NAME_RE = re.compile(r'[가-힣]{2,4}')
NOT_NAMES = {'없음', '미정', '조별', '교수', '교수님', '담당', '각과', '합동', '전체', '전임의'}


def load_courses(html_path):
    t = open(html_path, encoding='utf-8').read()
    s = t.find('<script>') + len('<script>')
    e = t.find('const ALLY')
    if s < len('<script>') or e < 0:
        sys.exit('HTML 구조가 예상과 다릅니다 (<script> … const ALLY 를 찾지 못함)')
    js = t[s:e] + '\nprocess.stdout.write(JSON.stringify(COURSES));'
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
    try:
        out = subprocess.run(['node', f.name], capture_output=True, text=True, check=True).stdout
    finally:
        os.unlink(f.name)
    return json.loads(out)


def profs(p):
    if not p:
        return []
    return [n for n in NAME_RE.findall(p) if n not in NOT_NAMES]


def slug(name):
    return re.sub(r'\s+', '', name)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUTDIR, '본1-2학기_3개년비교.html')
    courses = load_courses(src)
    os.makedirs(OUTDIR, exist_ok=True)
    for c in courses:
        subj = slug(c['name'])
        path = os.path.join(OUTDIR, f'{subj}.json')
        old, old_info = {}, {}
        if os.path.exists(path):
            old_info = json.load(open(path, encoding='utf-8'))
            for L in old_info['lectures']:
                old[L['name']] = L
        lectures, cat, years = [], None, set()
        for r in c.get('rows') or []:
            if 'cat' in r:
                cat = r['cat']; continue
            y = {k: v for k, v in (r.get('y') or {}).items() if v}
            years |= set(y)
            L = {
                'id': None,
                'name': r['n'],
                'category': cat,
                'kind': r.get('c'),
                'profs': {k: profs(v.get('p')) for k, v in sorted(y.items())},
                'hours': {k: v.get('hs') for k, v in sorted(y.items())},
                # 실습은 보통 지필시험에 안 나오므로 자동 분류 후보에서 뺀다 (직접 지정은 가능)
                'exam': not (cat and '실습' in cat),
                'keywords': [],
                'memo': '',
            }
            if r['n'] in old:
                L['id'] = old[r['n']]['id']
                L['keywords'] = old[r['n']].get('keywords', [])
                L['memo'] = old[r['n']].get('memo', '')
                L['exam'] = old[r['n']].get('exam', L['exam'])
                for k in ('show_name', 'merged_into'):   # 사용자가 정한 표시 이름·수업 합치기
                    if old[r['n']].get(k):
                        L[k] = old[r['n']][k]
            lectures.append(L)
        used = {L['id'] for L in lectures if L['id']}
        k = 1
        for L in lectures:
            if not L['id']:
                while f'{k:02d}' in used:
                    k += 1
                L['id'] = f'{k:02d}'; used.add(L['id']); k += 1
        info = {
            'subject': subj,
            'name': c['name'],
            'code': c.get('code'),
            'years': sorted(int(y) for y in years),
            'source': os.path.relpath(src, ROOT),
            'lectures': lectures,
        }
        if old_info.get('file_marks'):
            info['file_marks'] = old_info['file_marks']
        json.dump(info, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        allp = sorted({p for L in lectures for v in L['profs'].values() for p in v})
        print(f'{subj}: 수업 {len(lectures)}개, 연도 {info["years"]}, 교수 {len(allp)}명 -> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
