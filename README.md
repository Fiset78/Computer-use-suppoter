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
- **F12** 키를 누르면 눌려 있던 키/마우스 버튼을 즉시 전부 떼고 멈춥니다 (`PC_AGENT_KILL_KEY`로 변경, 게임에 포커스가 있어도 동작). API 응답을 기다리는 중이면 응답이 온 뒤 다음 행동 전에 멈춥니다.
- 마우스를 **화면 왼쪽 위 모서리**로 급히 옮겨도 멈춥니다. 단, 커서를 붙잡아 두는 게임에서는 동작하지 않으니 F12를 쓰세요.
- 터미널에서 `Ctrl+C`로도 멈출 수 있습니다.
- 어떤 이유로 끝나든 종료할 때 눌린 채로 남은 키/버튼을 전부 뗍니다.

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
- 백엔드에는 상대 마우스 이동(`move_rel`)도 있습니다. 1인칭 게임의 시점 회전용이며, `game` 보조 도구가 씁니다.

## 게임 보조 도구 (`game`)

1인칭 게임은 커서를 화면 중앙에 붙잡아 두므로 `mouse_move`로는 시점을 돌릴 수 없고, 이동·캐기처럼 여러 입력을 동시에 누르고 있어야 하는 동작이 많습니다. 이를 위한 custom 도구입니다.

| 도구 | 설명 |
|---|---|
| `look` | `yaw`(+오른쪽), `pitch`(+위) 각도만큼 시점 회전 |
| `look_at` | 스크린샷의 `[x, y]` 지점이 화면 중앙(조준점)에 오도록 회전. 시야각으로 픽셀을 각도로 바꿈 |
| `hold` | `keys`와 `mouse` 버튼을 동시에 `duration`초(최대 10초) 누름. `look`을 주면 그동안 고르게 회전 (예: 달리며 방향 틀기) |

```powershell
$env:PC_AGENT_INPUT = "directinput"   # 게임에서는 필수 (pyautogui로 켜면 경고가 나옴)
$env:PC_AGENT_ASSIST = "game"
uv run main.py "마인크래프트에서 가장 가까운 나무를 찾아가서 나무 블록 하나를 캐줘"
```

준비 (마인크래프트 Java 기준):
- **창 모드나 테두리 없는 창 모드**로, 게임이 캡처 중인 모니터 전체를 채우게 합니다. `look_at`은 조준점이 스크린샷 정중앙에 있다고 가정합니다.
- 비디오 설정의 **FOV를 `PC_AGENT_GAME_FOV`(기본 70)와 맞추고**, "FOV 효과"는 0%로 끕니다 (달리기·물약으로 FOV가 바뀌면 조준이 어긋남).
- 마우스 감도가 기본값(100%)이 아니면 `PC_AGENT_GAME_COUNTS_PER_DEG`를 바꿉니다. 1 count당 회전 = 1.2 × (감도×0.6 + 0.2)³ 도 (감도는 0~1 내부값, 100% 표시 = 0.5) → 기본 6.667 count/도.
- 보정 확인: `uv run main.py "look 도구로 yaw 360도를 돌린 뒤 처음과 같은 방향인지 확인해줘"`. 방향이 어긋나면 count/도 값을 조정합니다.

## 테스트

GUI 없이 돌릴 수 있는 로직만 테스트합니다: 키 변환, 시점 회전 계산과 game 도구, 긴급 정지, 결과 집계, 요소 목록 형식, 화면 변화 판정, 컨텍스트 관리, 그리고 입력 백엔드, 가짜 `pyautogui`/`pydirectinput`와 가짜 API 클라이언트로 에이전트 루프의 tool_result 규칙과 요청 형태.

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
| `PC_AGENT_ASSIST` | (없음) | 켤 보조 도구: `uia`, `wait`, `game`, `all` |
| `PC_AGENT_CONTEXT` | `server` | 컨텍스트 전략: `server`, `prune`, `none` |
| `PC_AGENT_INPUT` | `pyautogui` | 입력 백엔드: `pyautogui`, `directinput` |
| `PC_AGENT_KILL_KEY` | `f12` | 긴급 정지 단축키 (F1~F24, `pause`, `scrolllock`). 빈 값이면 끔 |
| `PC_AGENT_GAME_FOV` | `70` | game 도구: 게임의 세로 시야각(도) |
| `PC_AGENT_GAME_COUNTS_PER_DEG` | `6.667` | game 도구: 시점 1도당 마우스 이동량 (마인크래프트 기본 감도) |
| `PC_AGENT_PROMPT_CACHE` | `1` | `0`이면 캐시 중단점을 넣지 않음 |
| `PC_AGENT_CLEAR_TRIGGER` / `_KEEP` / `_AT_LEAST` | `40000` / `6` / `10000` | server 전략: 발동 입력 토큰 / 남길 도구 결과 수 / 한 번에 최소로 지울 토큰 |
| `PC_AGENT_PRUNE_KEEP` / `_BATCH` | `3` / `10` | prune 전략: 남길 스크린샷 수 / 몰아서 지울 단위 |
