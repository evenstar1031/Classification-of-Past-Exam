"""앱(본과 1학년 웹앱)·아티팩트의 「기출·학습자료」 탭이 읽는 수업별 현황 → app/gichul_index.json
usage: python3 tools/make_app_index.py            (저장소 맨 위에서)
.github/workflows/app-index.yml 이 main 에 올라올 때마다 돌린다.
"""
import glob, json, os, re, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import build_lectures as BL  # noqa: E402  (safe, lname — 학습자료 폴더 이름 규칙)

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
date = subprocess.run(['git', 'log', '-1', '--format=%cs'], capture_output=True, text=True).stdout.strip()

def ls(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else []

out = []
for f in sorted(glob.glob('과목정보/*.json')):
    info = json.load(open(f, encoding='utf8'))
    subj = info['subject']
    q_files, a_files, s_files = ls(f'문제지/{subj}'), ls(f'해설지/{subj}'), ls(f'학습자료/{subj}')
    exams, counts = [], {}
    for cf in sorted(glob.glob(f'분류/{subj}/*.json')):
        c = json.load(open(cf, encoding='utf8'))
        ex = c['exam']; exams.append({'id': ex['id'], 'year': ex['year'], 'date': ex.get('date')})
        for qn, q in c['questions'].items():
            lid = str(q.get('lecture') or '')
            counts.setdefault(lid, {}).setdefault(str(ex['year']), 0)
            counts[lid][str(ex['year'])] += 1
    def pick(files, lid, suffix):
        for x in files:
            if x.startswith(lid + '_') and x.endswith(suffix) and not x.endswith('(수정)' + suffix.replace('(수정)', '')):
                return x
        for x in files:
            if x.startswith(lid + '_') and x.endswith(suffix):
                return x
        return None
    lectures = []
    for L in info['lectures']:
        lid = L['id']
        q = next((x for x in q_files if x.startswith(lid + '_') and x.endswith('.pdf')), None)
        a = next((x for x in a_files if x.startswith(lid + '_') and x.endswith('_정답해설.pdf')), None)
        s = next((x for x in s_files if x.startswith(lid + '_') and x.endswith('_학습자료.pdf')), None)
        one = next((x for x in s_files if x.startswith(lid + '_') and x.endswith('_한장정리.pdf')), None)
        sdir = next((x for x in s_files if x.startswith(lid + '_') and os.path.isdir(f'학습자료/{subj}/{x}')), None)
        lectures.append({
            'id': lid, 'name': L['name'], 'cat': L.get('category'), 'exam': L.get('exam', True),
            'n': counts.get(lid, {}),
            'q': f'문제지/{subj}/{q}' if q else None,
            'a': f'해설지/{subj}/{a}' if a else None,
            's': f'학습자료/{subj}/{s}' if s else None,
            'one': f'학습자료/{subj}/{one}' if one else None,
            'dir': f'학습자료/{subj}/{sdir}' if sdir else None,
            'folder': f"학습자료/{subj}/{lid}_{BL.safe(BL.lname(L))}",
            'show': BL.lname(L),
        })
    extra = counts.get('99', {})
    whole_q = next((x for x in q_files if x.startswith('00_전체') and x.endswith('.pdf')), None)
    whole_a = next((x for x in a_files if x.startswith('00_전체') and x.endswith('.pdf')), None)
    out.append({
        'subject': subj, 'name': info['name'], 'code': info.get('code'),
        'exams': exams, 'etc': extra, 'lectures': lectures,
        'whole_q': f'문제지/{subj}/{whole_q}' if whole_q else None,
        'whole_a': f'해설지/{subj}/{whole_a}' if whole_a else None,
    })
res = {'repo': 'evenstar1031/Classification-of-Past-Exam', 'sha': sha, 'date': date, 'subjects': out}
os.makedirs('app', exist_ok=True)
with open('app/gichul_index.json', 'w', encoding='utf8') as f:
    json.dump(res, f, ensure_ascii=False, separators=(',', ':'))
print('app/gichul_index.json', sum(len(s['lectures']) for s in out), '수업')
