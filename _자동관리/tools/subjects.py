"""과목 이름 ↔ 폴더 이름.

보이는 폴더(문제지·해설지·학습자료·올리기·자료실)의 과목 폴더는 「순서 번호. 과목 이름」 (예: `01. 진단의 기본`).
_자동관리/ 안(분류·해설·작업기록·원본·과목정보)과 프로그램 인자는 짧은 과목 키(`진단의기본`)를 쓴다.
프로그램에는 키·폴더 이름·띄어 쓴 이름 무엇을 넣어도 key() 가 키로 바꿔 준다.

새 과목이 생기면 ORDER 맨 끝에 (키, 보이는 이름) 을 더한다 → 다음 번호가 붙는다.

    python3 _자동관리/tools/subjects.py        # 표 보기
"""
import re

ORDER = [                      # 앱 왼쪽 과목 순서
    ('진단의기본', '진단의 기본'),
    ('치료의기본', '치료의 기본'),
    ('인체감염학', '인체감염학'),
    ('정신건강의학', '정신건강의학'),
    ('신경학', '신경학'),
    ('호흡기·알레르기병학', '호흡기·알레르기병학'),
    ('사례바탕의료인문1', '사례바탕의료인문1'),
]


def _norm(t):
    return re.sub(r'\s+', '', re.sub(r'^\d+\s*[.)_-]?\s*', '', str(t).strip().strip('/')))


def key(name):
    """'01. 진단의 기본' / '진단의 기본' / '진단의기본' → '진단의기본' (모르는 과목은 번호·띄어쓰기만 뺀 것)"""
    n = _norm(name)
    for k, show in ORDER:
        if n in (_norm(k), _norm(show)):
            return k
    return n


def folder(name):
    """과목 → 보이는 폴더 이름 '01. 진단의 기본' (ORDER 에 없으면 키 그대로)"""
    k = key(name)
    for i, (kk, show) in enumerate(ORDER, 1):
        if kk == k:
            return f'{i:02d}. {show}'
    return k


if __name__ == '__main__':
    for k, _ in ORDER:
        print(f'{k:<14} → {folder(k)}')
