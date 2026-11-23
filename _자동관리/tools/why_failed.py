"""Claude 자동 실행이 왜 멈췄는지 알아내서 한국어로 알려 준다 (GitHub Actions 워크플로가 씀).

    python3 _자동관리/tools/why_failed.py <claude 실행 기록 json> [<기록2> …]

출력(GITHUB_OUTPUT 형식으로도 씀):
    kind=limit|overload|auth|turns|timeout|error|setup|ok
    title=<한 줄 제목>
    detail=<설명 한두 문장>
기록 파일이 없거나 비었으면 Claude 가 시작도 못 한 것(준비 단계 실패)으로 본다.
"""
import datetime, json, os, re, sys

KST = datetime.timezone(datetime.timedelta(hours=9))


def load(paths):
    msgs, raw = [], ''
    for p in paths:
        if not p or not os.path.isfile(p):
            continue
        t = open(p, encoding='utf-8', errors='replace').read()
        raw += t
        try:
            d = json.loads(t)
            msgs += d if isinstance(d, list) else [d]
        except Exception:
            for line in t.splitlines():
                try: msgs.append(json.loads(line))
                except Exception: pass
    return msgs, raw


def reset_time(text):
    m = re.search(r'limit reached\|(\d{9,})', text)          # "Claude AI usage limit reached|1732345200"
    if m:
        return datetime.datetime.fromtimestamp(int(m.group(1)), KST).strftime('%m/%d %H:%M')
    m = re.search(r'resets? (?:at )?([0-9]{1,2}(?::[0-9]{2})?\s*[ap]m)(?:\s*\(([^)]+)\))?', text, re.I)
    if m:
        return m.group(1) + (f' ({m.group(2)})' if m.group(2) else '')
    return None


def classify(paths, step_outcome=''):
    msgs, raw = load(paths)
    result = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get('type') == 'result'), None)
    text = raw[-4000:]          # 끝부분만 본다 (작업 내용 속 'limit' 같은 낱말에 속지 않게)
    rtext = json.dumps(result, ensure_ascii=False) if (result and result.get('is_error')) else ''
    low = (rtext + text).lower()
    if step_outcome == 'success' and not (result and result.get('is_error')):
        return 'ok', '정상 완료', ''
    if not msgs and step_outcome in ('failure', 'skipped', ''):
        return 'setup', '준비 단계에서 멈춤', 'Claude가 일을 시작하기 전(프로그램 설치·저장소 받기)에 실패했어요. 대개 GitHub 쪽 일시 오류예요.'
    if re.search(r'usage limit|limit reached|hit your (?:usage )?limit|rate.?limit|5-hour limit|weekly limit|exceeded your', low):
        t = reset_time(rtext + text)
        when = f' {t}에 한도가 풀려요.' if t else ''
        return 'limit', 'Claude 사용량 한도 초과', f'Claude 구독 사용량 한도에 닿아 멈췄어요.{when}'
    if re.search(r'overloaded|\b529\b|server error|\b50[234]\b|econnreset|socket hang up|network error', low):
        return 'overload', 'Claude 서버 혼잡·일시 오류', 'Claude 서버가 붐비거나 잠깐 연결이 끊겼어요.'
    if re.search(r'oauth token|invalid api key|authentication_error|authentication failed|\b401\b|unauthorized|token (?:has )?expired', low):
        return 'auth', 'Claude 로그인(토큰) 만료', '저장소 Secret 의 CLAUDE_CODE_OAUTH_TOKEN 이 만료됐어요. 노트북 터미널에서 `claude setup-token` 으로 새 토큰을 받아 Settings → Secrets 에서 바꿔 주세요(_자동관리/README.md 「Claude 자동 실행 설정」).'
    if result and result.get('subtype') == 'error_max_turns':
        return 'turns', '정해진 작업 횟수를 다 씀', '일이 길어서 정해진 횟수(턴) 안에 못 끝냈어요. 중간까지 한 것은 작업 브랜치에 남아 있어요.'
    if step_outcome == 'cancelled' or 'timed out' in low or 'timeout' in low[-3000:]:
        return 'timeout', '작업 시간 초과', '작업 시간(약 5시간)을 넘겨 멈췄어요. 중간까지 한 것은 작업 브랜치에 남아 있어요.'
    last = ''
    if result and result.get('result'):
        last = str(result['result']).strip().splitlines()[-1][:300]
    else:
        errs = re.findall(r'(?:Error|error|오류)[^\n"]{0,200}', raw[-20000:])
        last = errs[-1][:300] if errs else ''
    return 'error', '작업 중 오류', f'작업 중 오류로 멈췄어요. 마지막 메시지: {last or "(기록 없음)"}'


if __name__ == '__main__':
    args = sys.argv[1:]
    outcome = os.environ.get('STEP_OUTCOME', '')
    kind, title, detail = classify(args, outcome)
    print(f'kind={kind}\ntitle={title}\ndetail={detail}')
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(f'kind={kind}\ntitle={title}\n')
            f.write('detail<<EOF_DETAIL\n' + detail + '\nEOF_DETAIL\n')
