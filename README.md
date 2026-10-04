# pc-agent

Claude가 화면을 보고 마우스/키보드로 Windows PC를 조작하는 에이전트입니다 (1단계: 최소 루프).

## 시작하기 (Windows)

```powershell
# 1. uv 설치 (처음 한 번)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. 의존성 설치
cd pc-agent
uv sync

# 3. Claude 구독 계정으로 로그인 (처음 한 번)
#    Claude Code를 설치하고 실행한 뒤 /login 으로 Pro/Max 계정에 로그인합니다.
irm https://claude.ai/install.ps1 | iex
claude

# 4. 실행
uv run main.py "메모장을 열고 '안녕하세요'라고 입력해줘"
```

### 엔진: 구독(sdk) / API(api)
기본 엔진은 `sdk`입니다. Claude Agent SDK가 Claude Code를 띄워 루프를 돌리므로 **API 키 없이 구독 사용량**으로 동작합니다.
`ANTHROPIC_API_KEY`가 설정돼 있어도 sdk 엔진은 이를 넘기지 않습니다 (API로 과금되지 않도록).

예전처럼 API를 직접 쓰려면 (computer_toolset_20260801, 비교용):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:PC_AGENT_ENGINE = "api"
```

sdk 엔진의 차이점:
- computer 툴셋은 API 전용이라 쓸 수 없어서, 같은 17개 행동을 배열로 받는 custom 도구 `computer`로 대신합니다 (첫 실패 후 중단, 자동 스크린샷 규칙은 같음).
- 컨텍스트 관리는 Claude Code가 자동으로 합니다 (`PC_AGENT_CONTEXT`, 프롬프트 캐시 설정은 무시됨).
- 토큰 수는 Claude Code가 보고한 값입니다. 구독 사용량 한도에 포함됩니다.

### 웹 검색 (sdk 엔진, 선택)
기본은 꺼져 있습니다. 켜면 브라우저를 조작하지 않고 Claude Code의 WebSearch/WebFetch로 바로 검색합니다.
순수 화면 조작 성능을 잴 때는 끄세요.
```powershell
$env:PC_AGENT_WEB = "1"
uv run main.py "오늘 서울 날씨를 검색해서 메모장에 정리해줘"
```

## 실행 창 (터미널 없이, 음성 입력)
목표를 입력하거나 말로 시킬 수 있는 작은 창입니다. 처음 한 번 바탕화면 바로가기를 만듭니다.
```powershell
uv sync
powershell -ExecutionPolicy Bypass -File install_shortcut.ps1
```
이후에는 바탕화면의 **pc-agent** 아이콘을 더블클릭합니다 (터미널에서 켜려면 `uv run app.py`).
- **🎤 말하기** → 말하고 → **■ 멈추기**. 알아들은 문장이 입력칸에 들어가면 확인하고 **실행**을 누릅니다.
- **단축키 Ctrl+Alt+Space**: 어느 창에서든 한 번 누르고 말하면 끝입니다. 말을 마치고 2초 조용하면 자동으로 멈추고,
  알아들은 문장을 2초 보여 준 뒤 자동으로 실행합니다. 그 2초 안에 Esc나 단축키를 누르면 취소됩니다.
  녹음 중에 단축키를 누르면 바로 멈추고, 실행 중에 누르면 정지합니다. 두 자동 기능은 창의 체크 상자로 끌 수 있습니다. Ctrl+Alt+Space를 다른 프로그램이 쓰고 있으면 Ctrl+Alt+F9 → Ctrl+Shift+F9 → Ctrl+Alt+F12 순서로 자동으로 바꾸고, 창 아래쪽에 실제 단축키를 보여 줍니다. 직접 정하려면 `PC_AGENT_HOTKEY` (예: `ctrl+shift+f10`). 실행 창은 하나만 켜집니다.
- 처음 말할 때 음성 인식 모델 `large-v3-turbo`(약 1.6GB)를 내려받습니다. 인식이 느리면 `PC_AGENT_WHISPER_MODEL`을 `medium`이나 `small`로 낮추세요.
- 자주 틀리는 단어(프로그램 이름 등)는 프로젝트 폴더의 `voice_words.txt`에 적어 두면 그 단어로 맞춰 듣습니다. 저장하면 다음 인식부터 반영됩니다.
- 실행 중에는 창이 최소화되고, 끝나도 최소화된 채로 있습니다. 창이 최소화돼 있으면 듣는 중·알아들은 문장·2초 카운트다운·결과를
  화면 오른쪽 아래 작은 알림으로 보여 줍니다 (에이전트가 화면을 보는 동안에는 알림을 숨김). 멈추려면 단축키를 누르거나,
  작업 표시줄에서 창을 열어 **정지**를 누릅니다.
- 위험 행동 확인은 대화상자로 묻습니다. **결과 읽어 주기**를 체크하면 끝난 뒤 결과를 소리로 읽어 줍니다 (기본 꺼짐).

### 남은 사용량 바
실행 창 아래쪽에 구독의 **5시간 한도**, **주간 한도**가 얼마나 남았는지 막대로 보여 줍니다 (초기화 시각 포함).
Claude Code가 실행 중에 알려 주는 값이라, 한 번 실행해야 나타나고 "마지막 확인" 시각 기준입니다 (`runs/usage.json`에 저장).

### 속도
- 단계마다 기록 칸에 `(생각 4.2초)`, `(행동 1.1초)`처럼 시간이 찍히고, 끝나면 합계가 나옵니다. 대부분은 Claude가 생각하는 시간입니다.
- 창의 **생각: 빠르게/보통/깊게**로 생각 깊이를 고릅니다 (터미널은 `PC_AGENT_EFFORT=low|medium|high`, 기본 medium). 빠르게일수록 어려운 작업에서 실수가 늘 수 있습니다.
- 첫 단계는 Claude Code를 켜는 시간이 더해져서 더 깁니다.

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

## 보조 도구 (5단계)

순수 computer use에 더해 Claude가 쓸 수 있는 custom 도구입니다. 기본은 꺼져 있고(기준 성능), 환경 변수나 `--assist`로 켭니다.

| 묶음 | 도구 | 설명 |
|---|---|---|
| `uia` | `list_ui_elements` | 활성 창의 버튼, 입력칸, 메뉴 등을 Windows UI Automation으로 읽어 `[id] 종류 "이름" (x,y)` 목록으로 돌려줌 |
| `uia` | `click_element` | 목록의 id로 요소를 클릭 (클릭 직전에 위치를 다시 읽음) |
| `wait` | `wait_for_change` | 마지막 스크린샷과 달라질 때까지 기다렸다가, 화면이 멈추면 새 스크린샷을 돌려줌 |

```powershell
$env:PC_AGENT_ASSIST = "uia,wait"      # 또는 all
uv run main.py "계산기를 열어서 123 곱하기 45를 계산해줘"

# 기준 성능과 비교
uv run bench.py --repeat 3 --label baseline
uv run bench.py --repeat 3 --label assist --assist all
```

## 컨텍스트 관리 (6단계)

스크린샷은 한 장에 입력 토큰 약 1,000~1,800개라 단계가 길어질수록 비용이 커집니다. 두 가지를 적용합니다.

- **prompt caching (항상 켜짐):** system과 최근 user 메시지 3개에 캐시 중단점을 둡니다. 이전 대화는 캐시에서 읽으므로(정가의 약 0.1배) 동작은 같고 비용만 줄어듭니다.
- **오래된 스크린샷 정리 (`PC_AGENT_CONTEXT`):**

| 전략 | 방식 | 비고 |
|---|---|---|
| `server` (기본) | 서버 측 tool result clearing. 입력이 40,000토큰을 넘으면 최근 도구 결과 6개만 남기고 서버가 지움 | 모든 모델에서 안전 |
| `prune` | 스크린샷이 13장을 넘으면 최근 3장만 남기고 클라이언트가 지움 (몰아서 지워 캐시를 덜 깸) | Opus 5.5 / Fable 5.1에서는 자동으로 `server`로 바뀜 |
| `none` | 지우지 않음 | 비교용 |

```powershell
uv run bench.py --repeat 3 --label ctx-server --context server
uv run bench.py --repeat 3 --label ctx-none --context none
```

벤치마크 요약 표에 캐시 읽기/쓰기 토큰이 함께 나옵니다.

## 입력 백엔드 (7단계)

마우스/키보드 입력을 보내는 부분을 바꿀 수 있습니다 (`PC_AGENT_INPUT`, `bench.py --input`).

| 백엔드 | 용도 | 방식 |
|---|---|---|
| `pyautogui` (기본) | 일반 데스크톱 앱 | pyautogui |
| `directinput` | 게임 (마인크래프트 등) | `pydirectinput-rgx`의 SendInput + 스캔 코드. DirectX 게임은 일반 가상 키 입력을 무시하는 경우가 많음 |

```powershell
$env:PC_AGENT_INPUT = "directinput"
uv run main.py "마인크래프트에서 앞으로 3초 걸어가줘"
```

- 두 백엔드 모두 모르는 키 이름은 조용히 무시하지 않고 오류로 Claude에게 알려줍니다 (예: `directinput`에는 한/영 키가 없음).
- 한글 같은 비ASCII 텍스트는 어느 백엔드든 클립보드 붙여넣기(Ctrl+V)로 입력합니다. 게임 채팅창처럼 붙여넣기를 막는 곳에서는 입력되지 않습니다.
- 긴급 정지(마우스를 왼쪽 위 모서리로)는 두 백엔드 모두 동작합니다.
- 백엔드에는 상대 마우스 이동(`move_rel`)도 있습니다. 1인칭 게임의 시점 회전용이며, 아직 Claude가 쓸 도구로는 노출하지 않았습니다.

## 테스트

GUI 없이 돌릴 수 있는 로직만 테스트합니다: 키 변환, 결과 집계, 요소 목록 형식, 화면 변화 판정, 컨텍스트 관리, 그리고 입력 백엔드, 가짜 `pyautogui`/`pydirectinput`와 가짜 API 클라이언트로 에이전트 루프의 tool_result 규칙과 요청 형태.

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
| `PC_AGENT_ASSIST` | (없음) | 켤 보조 도구: `uia`, `wait`, `all` |
| `PC_AGENT_CONTEXT` | `server` | 컨텍스트 전략: `server`, `prune`, `none` |
| `PC_AGENT_INPUT` | `pyautogui` | 입력 백엔드: `pyautogui`, `directinput` |
| `PC_AGENT_PROMPT_CACHE` | `1` | `0`이면 캐시 중단점을 넣지 않음 |
| `PC_AGENT_CLEAR_TRIGGER` / `_KEEP` / `_AT_LEAST` | `40000` / `6` / `10000` | server 전략: 발동 입력 토큰 / 남길 도구 결과 수 / 한 번에 최소로 지울 토큰 |
| `PC_AGENT_PRUNE_KEEP` / `_BATCH` | `3` / `10` | prune 전략: 남길 스크린샷 수 / 몰아서 지울 단위 |
