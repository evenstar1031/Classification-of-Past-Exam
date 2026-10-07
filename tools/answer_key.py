#!/usr/bin/env python3
"""원본 PDF의 정답 표시와 오답노트를 해설/<과목>/<시험id>.json 으로 옮긴다.

usage: python3 tools/answer_key.py <과목> [<시험id> ...]     (시험id 생략 = 분류된 시험 전부)

입력: work/<시험id>/parsed.json (extract.py 결과: 보기별 정답 표시 mk_num / mk_lines, 오답노트 notes,
      주관식 답 answer_text), work/<시험id>/fixes.json (regroup 으로 바뀐 보기 순서)
출력: 해설/<과목>/<시험id>.json
  {"exam": {...}, "questions": {"12": {"answer": [3], "answer_by": "원본", "answer_text": "",
                                     "source_note": "…", "explanation": "…"}}}

- answer       최종 보기 번호(1부터). regroup 후의 번호로 계산한다.
- answer_by    "원본" = 원본 PDF의 색·크기 표시에서 읽음 / "직접" = 사람이 고친 값 (다시 돌려도 유지)
- explanation  해설. 이 스크립트는 절대 덮어쓰지 않는다 (비어 있으면 빈 문자열로 만든다).
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from build_lectures import ensure_work  # noqa: E402  (work/ 가 없으면 원본에서 다시 만든다)

NOTE_HEAD = re.compile(r'^\s*ⓘ\s*(오답노트|해설)\s*$')


def final_answers(q, regroup):
    """정답 보기 번호 목록 (regroup 반영). 보기 글자가 색/크기로 표시됐거나 번호 자체가 표시된 보기."""
    cs = q['choices']
    marked_lines = {l for c in cs for l in c.get('mk_lines', [])}
    rg = regroup.get(str(q['n']), {})
    final = [rg.get(str(i + 1), c['lines']) for i, c in enumerate(cs)]
    by_line = {i + 1 for i, ls in enumerate(final) if any(l in marked_lines for l in ls)}
    by_num = {i + 1 for i, c in enumerate(cs) if c.get('mk_num')}
    return sorted(by_line | by_num)


def note_text(lines):
    body = [l.strip() for l in lines if l.strip() and not NOTE_HEAD.match(l)]
    return '\n'.join(body)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    subj = sys.argv[1]
    base = os.path.join(ROOT, '분류', subj)
    exams = sys.argv[2:] or sorted(f[:-5] for f in os.listdir(base) if f.endswith('.json'))
    for ex_id in exams:
        cls = json.load(open(os.path.join(base, f'{ex_id}.json'), encoding='utf-8'))
        work = ensure_work(subj, cls['exam'])
        parsed = json.load(open(os.path.join(work, 'parsed.json'), encoding='utf-8'))
        if parsed and 'notes' not in parsed[0]:
            sys.exit(f'!! {ex_id}: parsed.json 이 예전 형식입니다. work/{ex_id} 를 지우고 다시 돌리세요.')
        fixes = json.load(open(os.path.join(work, 'fixes.json'), encoding='utf-8'))
        out_p = os.path.join(ROOT, '해설', subj, f'{ex_id}.json')
        old = json.load(open(out_p, encoding='utf-8')) if os.path.exists(out_p) else {}
        oldq = old.get('questions', {})
        out = {'exam': {k: cls['exam'][k] for k in ('id', 'subject', 'title', 'date', 'year')}, 'questions': {}}
        odd = []
        for q in parsed:
            n = str(q['n'])
            prev = oldq.get(n, {})
            e = {'answer': final_answers(q, fixes.get('regroup', {})), 'answer_by': '원본',
                 'answer_text': ' / '.join(q.get('answer_text', [])),
                 'source_note': note_text(q.get('notes', [])),
                 'explanation': prev.get('explanation', '')}
            if prev.get('answer_by') == '직접':
                e['answer'], e['answer_by'] = prev['answer'], '직접'
            if not e['answer'] and not e['answer_text']:
                odd.append(f'{n}번(정답 표시 없음)')
            out['questions'][n] = e
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        json.dump(out, open(out_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        qs = out['questions']
        print(f"{ex_id}: {len(qs)}문항, 정답 {sum(1 for e in qs.values() if e['answer'] or e['answer_text'])}, "
              f"복수정답 {sum(1 for e in qs.values() if len(e['answer']) > 1)}, "
              f"원본 오답노트 {sum(1 for e in qs.values() if e['source_note'])}, "
              f"해설 작성됨 {sum(1 for e in qs.values() if e['explanation'])}"
              + (f'  !! {odd}' if odd else ''))


if __name__ == '__main__':
    main()
