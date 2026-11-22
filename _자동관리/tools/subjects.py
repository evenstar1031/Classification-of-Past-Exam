"""과목 이름 ↔ 폴더 이름.

보이는 폴더(문제지·해설지·학습자료·올리기·자료실)의 과목 폴더는 「학기/순서 번호. 과목 이름」
(예: `2학기/01. 진단의 기본`, `1학기/01. 생리학`). 번호는 학기마다 01부터.
_자동관리/ 안(분류·해설·작업기록·원본·과목정보)과 프로그램 인자는 짧은 과목 키(`진단의기본`)를 쓴다.
프로그램에는 키·폴더 이름·띄어 쓴 이름·학기 붙은 경로 무엇을 넣어도 key() 가 키로 바꿔 준다.

새 과목이 생기면 그 학기 목록 맨 끝에 (키, 보이는 이름) 을 더한다 → 다음 번호가 붙는다.

    python3 _자동관리/tools/subjects.py        # 표 보기
"""
import re

ORDER = {                      # 앱 과목 순서 (1학기는 강의계획서 탭 순서)
    1: [
        ('생리학', '생리학'),
        ('해부학', '해부학'),
        ('면역학', '면역학'),
        ('병리학', '병리학'),
        ('병원체학', '병원체학'),
        ('약리학총론', '약리학 총론'),
        ('기초의학종합', '기초의학종합'),
    ],
    2: [
        ('진단의기본', '진단의 기본'),
        ('치료의기본', '치료의 기본'),
        ('인체감염학', '인체감염학'),
        ('정신건강의학', '정신건강의학'),
        ('신경학', '신경학'),
        ('호흡기·알레르기병학', '호흡기·알레르기병학'),
        ('사례바탕의료인문1', '사례바탕의료인문1'),
    ],
}


def _norm(t):
    t = str(t).strip().strip('/').split('/')[-1]          # '2학기/01. 진단의 기본' → '01. 진단의 기본'
    return re.sub(r'\s+', '', re.sub(r'^\d+\s*[.)_-]?\s*', '', t))


def _find(name):
    n = _norm(name)
    for sem, lst in ORDER.items():
        for i, (k, show) in enumerate(lst, 1):
            if n in (_norm(k), _norm(show)):
                return sem, i, k, show
    return None


def key(name):
    """'2학기/01. 진단의 기본' / '진단의 기본' / '진단의기본' → '진단의기본' (모르는 과목은 번호·띄어쓰기만 뺀 것)"""
    f = _find(name)
    return f[2] if f else _norm(name)


def semester(name):
    """과목의 학기 (1 또는 2, 모르면 None)"""
    f = _find(name)
    return f[0] if f else None


def folder(name):
    """과목 → 보이는 폴더 '2학기/01. 진단의 기본' (목록에 없으면 키 그대로)"""
    f = _find(name)
    if not f:
        return _norm(name)
    sem, i, _, show = f
    return f'{sem}학기/{i:02d}. {show}'


if __name__ == '__main__':
    for sem, lst in ORDER.items():
        for k, _ in lst:
            print(f'{k:<14} → {folder(k)}')
