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

## 기준 성능 측정 (벤치마크)

고정 과제 세트(`benchmark/tasks.py`)를 실행해서 성공률, 단계 수, 토큰, 시간을 기록합니다.
보조 기능을 붙이기 전에 먼저 측정해 두고, 이후 같은 과제로 다시 돌려 비교합니다.

```powershell
uv run bench.py --list                 # 과제 목록
uv run bench.py --repeat 3 --label baseline
uv run bench.py --tasks calc_multiply  # 일부 과제만
```

- 과제마다 준비 안내가 나오고, Enter를 누르면 시작합니다 (`s` 건너뛰기, `q` 종료).
- 성공 여부는 가능한 과제는 자동 판정합니다 (파일 존재, 클립보드, 창 제목, 보고 내용). 나머지는 y/n으로 직접 판정합니다.
- 결과는 `runs/bench-<시각>-<label>/`에 저장됩니다. `summary.json`에는 과제별·전체 요약과 실행 조건(모델, 스크린샷 크기 등)이 들어 있습니다.
- 과제는 `%USERPROFILE%\pc-agent-bench\` 폴더 안에서만 파일을 만들고 지웁니다.

## 테스트

GUI 없이 돌릴 수 있는 순수 모듈(`actions/keys.py`, `benchmark/metrics.py`)만 테스트합니다.

```powershell
uv run pytest
```

## 설정 (환경 변수)
| 변수 | 기본값 | 설명 |
|---|---|---|
| `PC_AGENT_MODEL` | `claude-sonnet-5` | 사용할 모델 |
| `PC_AGENT_MAX_STEPS` | `30` | 최대 반복 수 |
| `PC_AGENT_MAX_LONG_EDGE` | `1280` | 스크린샷 긴 변 최대 픽셀 |
| `PC_AGENT_MONITOR` | `1` | 캡처할 모니터 (1 = 주 모니터) |
