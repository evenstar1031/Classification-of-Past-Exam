"""학습자료 PDF 이름에 단계를 붙인다: …_학습자료.pdf → …_학습자료(수업 전).pdf / …_학습자료(수업 후).pdf

    python3 _자동관리/tools/study_names.py        # 앱 현황 갱신(app-index.yml) 이 매번 돌림

단계는 PDF 표지로 판단한다(수업 전판 표지에는 「수업 전 자료」 줄이 있다). 한 수업에 수업 후판이 있으면 수업 전판은 지운다.
예전 이름으로 만들어진 파일(옛 study.py, 다른 사람의 오래된 브랜치)도 여기서 맞춰진다.
"""
import glob, os, re, sys
import pymupdf

PAT = re.compile(r'^(\d{2})_(.*)_학습자료(\(수업 [전후]\))?\.pdf$')


def stage(path):
    try:
        return 'pre' if '수업 전 자료' in pymupdf.open(path)[0].get_text() else 'post'
    except Exception:
        return None


def main():
    changed = 0
    for sdir in sorted(glob.glob('학습자료/*/*/')):
        by_lid = {}
        for x in sorted(os.listdir(sdir)):
            m = PAT.match(x)
            if m and os.path.isfile(sdir + x):
                by_lid.setdefault(m.group(1), []).append((x, m))
        for lid, files in by_lid.items():
            info = []
            for x, m in files:
                st = stage(sdir + x)
                if st:
                    info.append((x, m, st))
            if any(st == 'post' for _, _, st in info):          # 수업 후판이 있으면 수업 전판은 필요 없음
                for x, _, st in info:
                    if st == 'pre':
                        os.remove(sdir + x); print(f'지움(수업 후판이 있음): {sdir}{x}'); changed += 1
                info = [t for t in info if t[2] == 'post']
            for x, m, st in info:
                want = f"{m.group(1)}_{m.group(2)}_학습자료({'수업 전' if st == 'pre' else '수업 후'}).pdf"
                if x == want:
                    continue
                if os.path.exists(sdir + want):                 # 같은 단계 파일이 둘: 예전 이름 쪽을 지움
                    os.remove(sdir + x); print(f'지움(중복): {sdir}{x}')
                else:
                    os.rename(sdir + x, sdir + want); print(f'이름 바꿈: {sdir}{x} → {want}')
                changed += 1
    print(f'학습자료 이름 정리: {changed}개 바뀜')


if __name__ == '__main__':
    main()
