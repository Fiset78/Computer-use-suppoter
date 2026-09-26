# pc-agent

Claude가 화면을 보고 마우스/키보드로 Windows PC를 조작하는 에이전트입니다 (1단계: 최소 루프).

## 시작하기 (Windows)

```powershell
# 1. uv 설치 (처음 한 번)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. 의존성 설치
cd pc-agent
uv sync

# 3. API 키 설정 (현재 터미널에서만 유효)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 4. 실행
uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
```

## 긴급 정지
- 마우스를 **화면 왼쪽 위 모서리**로 급히 옮기면 즉시 멈춥니다.
- 터미널에서 `Ctrl+C`로도 멈출 수 있습니다.

## 첫 테스트 추천 과제
1. `메모장을 열고 '안녕하세요'라고 입력해줘` (실행, 한글 입력)
2. `계산기를 열어서 123 곱하기 45를 계산해줘` (클릭 정확도)
3. `파일 탐색기에서 문서 폴더를 열어줘` (탐색)

실행이 끝나면 `runs/` 폴더에서 단계별 스크린샷과 행동 로그를 확인할 수 있습니다.

## 설정 (환경 변수)
| 변수 | 기본값 | 설명 |
|---|---|---|
| `PC_AGENT_MODEL` | `claude-sonnet-5` | 사용할 모델 |
| `PC_AGENT_MAX_STEPS` | `30` | 최대 반복 수 |
| `PC_AGENT_MAX_LONG_EDGE` | `1280` | 스크린샷 긴 변 최대 픽셀 |
| `PC_AGENT_MONITOR` | `1` | 캡처할 모니터 (1 = 주 모니터) |
