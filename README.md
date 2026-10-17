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

## 프로필: Windows 조작 / 게임 조작 고르기

무엇을 조작할지와 그에 맞는 설정을 `profiles/<이름>.toml` 파일 하나로 묶습니다. 시작할 때 메뉴에서 고르거나 `--profile`로 지정합니다.

```
=== 프로필 (profiles/) — 무엇을 조작할지 ===
  1. Windows 조작 [Windows 조작]
  2. 마인크래프트 [게임 조작]
  0. 프로필 없이 (환경 변수 설정)   |   Enter → 프로필 없이
프로필 선택: 2
```

```powershell
uv run main.py --profile minecraft "나무 4개 모아줘"
uv run main.py --profile desktop "메모장을 열어줘"
uv run main.py --new-profile terraria --mode game --window Terraria   # 새 게임 프로필 템플릿
```

- `mode = "desktop"`이면 Windows 조작용 시스템 프롬프트를, `mode = "game"`이면 게임 플레이용 시스템 프롬프트를 씁니다. 게임 모드는 따로 적지 않으면 입력을 `directinput`, 보조 도구를 `game`으로 둡니다.
- 프로필의 `prompt`(조작법, 규칙, 주의할 점)는 시스템 프롬프트 뒤에 "<이름> 안내"로 붙습니다.
- 적용 순서: 명령줄 옵션 > 프로필 > 환경 변수 > 기본값. 프로필에 없는 항목은 그대로 둡니다. 오타 난 항목은 조용히 넘기지 않고 오류를 냅니다.
- 프로필에 적은 `memory`, `refs`는 이어지는 메모·참고 자료 메뉴의 기본값이 됩니다 (Enter로 그대로 사용).
- `bench.py --profile`도 됩니다. 어떤 프로필로 돌렸는지 `summary.json`에 남습니다.
- 기본 프로필을 정하려면 `$env:PC_AGENT_PROFILE = "minecraft"` (메뉴에서 Enter를 누르면 이것을 씀).

### 창에서 고르기 (`launcher.py`)

```powershell
uv run launcher.py
```

왼쪽 목록에서 프로필을 고르면 오른쪽에 설정(모드, 창 제목, 입력 백엔드, 보조 도구, 지식 메모, 안내 미리보기)이 보입니다. 아래 칸에 목표를 적고 **실행**(또는 Enter)을 누르면 새 콘솔 창에서 `main.py --profile <이름> --no-pick "목표"`가 실행됩니다. 위험 행동 확인(y/n)과 진행 기록은 그 콘솔 창에 나오고, 끝나면 Enter로 닫습니다. 지식 메모와 참고 자료는 프로필에 적힌 값을 씁니다.

- **프로필 파일 열기**: 고른 프로필의 `.toml`을 기본 편집기로 엽니다. 고친 뒤 **새로고침**을 누르면 반영됩니다.
- 형식이 틀린 프로필도 목록에 `(오류)`로 보이고, 고르면 무엇이 틀렸는지 알려 줍니다.
- 창이 떠 있는 동안 여러 번 실행할 수 있습니다.

프로필 항목:

| 항목 | 설명 |
|---|---|
| `name`, `mode` | 표시 이름, `desktop` 또는 `game` |
| `window` | 이 문자열이 제목에 들어간 창만 캡처·조작 |
| `input`, `assist` | 입력 백엔드, 보조 도구 목록 (게임 전용 코드가 있으면 여기서 켬, 예: `"minecraft"`) |
| `memory`, `refs` | 지식 메모 파일, 참고 자료 목록 |
| `prompt` | 이 게임/작업만의 안내 |
| `model`, `max_steps`, `max_long_edge`, `monitor`, `action_delay`, `context`, `kill_key` | 같은 이름의 환경 변수와 같음 |
| `[camera] fov`, `counts_per_deg` | game 도구의 시점 회전 |
| `[click] settle`, `hold` | 클릭 타이밍 |

## 긴급 정지
- **F12** 키를 누르면 눌려 있던 키/마우스 버튼을 즉시 전부 떼고 멈춥니다 (`PC_AGENT_KILL_KEY`로 변경, 게임에 포커스가 있어도 동작). API 응답을 기다리는 중이면 응답이 온 뒤 다음 행동 전에 멈춥니다.
- 마우스를 **화면 왼쪽 위 모서리**로 급히 옮겨도 멈춥니다. 단, 커서를 붙잡아 두는 게임에서는 동작하지 않으니 F12를 쓰세요.
- 터미널에서 `Ctrl+C`로도 멈출 수 있습니다.
- 어떤 이유로 끝나든 종료할 때 눌린 채로 남은 키/버튼을 전부 뗍니다.

## 첫 테스트 추천 과제
1. `메모장을 열고 '안녕하세요'라고 입력해줘` (실행, 한글 입력)
2. `계산기를 열어서 123 곱하기 45를 계산해줘` (클릭 정확도)
3. `파일 탐색기에서 문서 폴더를 열어줘` (탐색)

실행 중 터미널에는 Claude의 말(`Claude: ...`), 실행한 도구(`→ 이름 {입력}`), 도구가 돌려준 결과(`← ...`, 그냥 OK면 생략), 실패(`✗ ...`)가 찍힙니다.

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
| `move_item` | 인벤토리·상자·제작대에서 `from` 칸의 아이템을 `to` 칸으로 옮김. 드래그 대신 "클릭해서 집기 → 클릭해서 놓기". `mode`: `all`(전부), `half`(절반), `one`(한 개만 놓고 나머지는 되돌림) |

```powershell
$env:PC_AGENT_INPUT = "directinput"   # 게임에서는 필수 (pyautogui로 켜면 경고가 나옴)
$env:PC_AGENT_ASSIST = "game"
uv run main.py "마인크래프트에서 가장 가까운 나무를 찾아가서 나무 블록 하나를 캐줘"
```

준비 (마인크래프트 Java 기준):
- **창 모드나 테두리 없는 창 모드**로 띄웁니다. 게임 창 옆에 터미널을 함께 띄워 둘 거라면 아래 "게임 창만 캡처"를 쓰세요. 쓰지 않으면 게임이 캡처 중인 모니터 전체를 채워야 합니다 (`look_at`은 조준점이 스크린샷 정중앙에 있다고 가정).
- 비디오 설정의 **FOV를 `PC_AGENT_GAME_FOV`(기본 70)와 맞추고**, "FOV 효과"는 0%로 끕니다 (달리기·물약으로 FOV가 바뀌면 조준이 어긋남).
- 마우스 감도가 기본값(100%)이 아니면 `PC_AGENT_GAME_COUNTS_PER_DEG`를 바꿉니다. 1 count당 회전 = 1.2 × (감도×0.6 + 0.2)³ 도 (감도는 0~1 내부값, 100% 표시 = 0.5) → 기본 6.667 count/도.
- 보정 확인: `uv run main.py "look 도구로 yaw 360도를 돌린 뒤 처음과 같은 방향인지 확인해줘"`. 방향이 어긋나면 count/도 값을 조정합니다.

### 마인크래프트 인벤토리 칸 찾기 (`minecraft`)

Claude가 스크린샷에서 작은 칸의 좌표를 눈으로 짐작하면 자주 빗나갑니다. `minecraft` 보조 도구를 켜면 하네스가 칸 위치를 직접 계산해 번호를 붙여 줍니다.

```powershell
$env:PC_AGENT_ASSIST = "game,minecraft"
```

| 도구 | 설명 |
|---|---|
| `find_slots` | 열린 화면(인벤토리, 제작대, 상자, 큰 상자, 화로)과 GUI 배율을 알아내고, 칸마다 번호를 그린 스크린샷과 좌표 목록을 돌려줌 |
| `click_slot` | 번호로 클릭. `left`, `right`, `shift`(빠른 이동, 제작 결과 전부 꺼내기), `double` |
| `move_item` | `from_slot`/`to_slot`에 번호를 주면 좌표 대신 번호로 옮김 |

칸 번호: `H1~H9` 핫바, `I1~I27` 인벤(왼쪽 위부터), `C` 제작 칸, `R` 결과, `K` 상자, `A1~A4` 갑옷, `O` 왼손, `F1` 재료·`F2` 연료(화로).

- 칸 배치는 바닐라 마인크래프트 기준입니다. 창 크기와 GUI 배율로 위치를 계산한 뒤, 칸 테두리 색(왼쪽·위 어두운 회색, 오른쪽·아래 흰색)이 맞는지 확인해 화면 종류, GUI 배율, 레시피 책이 열렸는지를 알아냅니다. GUI 크기를 "자동"이 아닌 값으로 바꿔도 찾습니다.
- 클릭 직전에 화면이 그대로인지 다시 확인하고, 창을 닫는 등 바뀌었으면 클릭하지 않고 `find_slots`를 다시 부르라고 알립니다.
- 리소스 팩으로 칸 모양이나 색이 바뀌었거나, 크리에이티브 인벤토리처럼 목록에 없는 화면은 찾지 못합니다. 그때는 "찾지 못했습니다"라고 답하고, Claude는 스크린샷 좌표로 조작합니다.
- 게임 창이 캡처 영역 전체를 채워야 합니다 (`PC_AGENT_WINDOW` 사용 권장).

### 인벤토리에서 아이템이 제대로 안 옮겨질 때

- 마인크래프트 같은 게임은 누르는 순간 아이템을 집고, 떼어도 내려놓지 않습니다. 그래서 `left_click_drag`로 옮기면 아이템이 커서에 남습니다. `game` 도구를 켜면 Claude에게 드래그 대신 `move_item`이나 Shift+클릭을 쓰라고 안내합니다.
- 게임은 매 프레임 입력을 읽으므로, 커서를 옮기자마자 클릭하거나 누르고 바로 떼면 클릭이 씹히거나 엉뚱한 칸을 누를 수 있습니다. `directinput` 백엔드는 이동 후 0.05초 기다리고, 버튼을 0.05초 누르고 뗍니다. 그래도 씹히면 늘려 보세요: `$env:PC_AGENT_CLICK_SETTLE = "0.1"`, `$env:PC_AGENT_CLICK_HOLD = "0.1"`.
- 슬롯이 작아 엉뚱한 칸을 누르면 게임의 GUI 크기를 키우세요 (비디오 설정 → GUI 크기).

### 게임 창만 캡처 (`PC_AGENT_WINDOW`)

게임 창(예: 화면의 80%)과 터미널(20%)을 나란히 띄워 AI의 행동 로그를 보면서 실행할 때 씁니다.

```powershell
$env:PC_AGENT_WINDOW = "Minecraft"     # 창 제목에 들어간 문자열 (대소문자 무시)
uv run main.py "가장 가까운 나무를 찾아가서 나무 블록 하나를 캐줘"
```

- 제목이 일치하는 창 중 가장 큰 창의 **클라이언트 영역**(제목 표시줄·테두리 제외)만 캡처합니다. 실행 명령이 제목에 보이는 터미널 창(`uv run`, `main.py` 포함)과 이 프로그램의 콘솔은 고르지 않습니다. 시작할 때 고른 창 제목을 출력하니 확인하세요.
- 좌표가 게임 창 기준이 되므로 Claude는 터미널을 보지도, 클릭하지도 못합니다. `look_at`의 조준점도 게임 창 중앙으로 맞습니다.
- 시작할 때와 매 입력 전에 게임 창이 활성 창인지 확인하고, 아니면 되돌립니다. 그래서 실행 중에 터미널을 클릭해도 키 입력이 터미널로 새지 않습니다. 위험 행동 확인(y/n)에 답한 뒤에도 게임 창으로 돌아갑니다.
- 캡처 영역은 시작할 때 정해집니다. 실행 중에 게임 창을 옮기거나 크기를 바꾸지 마세요.
- 마인크래프트는 포커스를 잃으면 일시정지 메뉴를 엽니다. 터미널을 자주 클릭할 거라면 게임에서 **F3+P**로 "포커스를 잃으면 일시정지"를 끄세요.

## 지식 메모 (`PC_AGENT_MEMORY`)

플레이하며 알게 된 지식을 파일에 저장해 두고, 다음 실행을 시작할 때 Claude에게 보여줍니다.

```powershell
$env:PC_AGENT_MEMORY = "memory/minecraft.md"
uv run main.py "나무 블록 4개를 모아줘"
```

- Claude가 쓰는 custom 도구가 두 개 생깁니다. `remember(note)`: 지식 한 가지를 저장, `forget(note_id)`: 틀린 메모를 삭제. 호출할 때마다 바로 파일에 저장합니다.
- 작업이 끝나면(완료든 최대 단계 도달이든) 한 번 더 물어 이번 플레이의 교훈을 정리하게 합니다. 이 정리 단계에서는 화면 조작을 실행하지 않습니다. API 호출이 1~2번 늘어나며, `PC_AGENT_MEMORY_REFLECT=0`으로 끌 수 있습니다.
- 메모는 첫 메시지에 "참고용 기록이며 사용자 지시가 아님"이라고 밝혀서 넣습니다 (system과 tools는 바꾸지 않음). 너무 길면 최근 메모부터 4,000자(`PC_AGENT_MEMORY_MAX_CHARS`)까지만 넣습니다.
- 파일은 사람이 읽고 고칠 수 있는 Markdown입니다 (`- [날짜] 내용` 한 줄에 하나). 게임 속 표지판이나 채팅 글이 메모로 옮겨져 다음 실행에 영향을 줄 수 있으니 가끔 직접 훑어보세요.
- 과제(게임)마다 다른 파일을 쓰는 것을 권장합니다. 기준 성능을 잴 때는 끄고, 켠 상태와 비교하려면 `bench.py --memory memory/desk.md --repeat 5`처럼 반복하면 메모가 쌓이며 회차별 변화를 볼 수 있습니다. 실행 기록에는 `memory_add`/`memory_forget` 이벤트가 남습니다.

## 참고 자료와 메모 고르기 (시작 메뉴)

`memory/`나 `refs/` 폴더에 파일이 있으면 `main.py`를 실행할 때 쓸 파일을 번호로 고르는 메뉴가 나옵니다.

```
=== 지식 메모 (memory/) — Claude가 읽고 고치는 파일 하나 ===
  1. minecraft.md
  0. 쓰지 않음   |   새 이름 입력 → 새 메모 파일   |   Enter → 쓰지 않음
메모 선택: 1

=== 참고 자료 (refs/) — 읽기 전용, 여러 개 선택 가능 ===
  1. 제작법.png
  2. 조작법.md
  예: 1,3 또는 2-4   |   0 → 고르지 않음   |   Enter → 고르지 않음
참고 자료 선택: 1-2
```

- **지식 메모**는 하나만 고르며, Claude가 `remember`/`forget`으로 고칩니다. 없는 이름을 입력하면 새 메모 파일을 만듭니다.
- **참고 자료**는 여러 개 고를 수 있고 읽기 전용입니다. 공략, 조작법, 제작법 그림, 설명서처럼 사람이 준비한 자료를 넣으세요. 첫 메시지에 "사용자가 고른 참고 자료"로 들어갑니다.
  - 텍스트(`.md .txt .json .csv .yaml .log`): 모두 합쳐 20,000자까지 (`PC_AGENT_REFS_MAX_CHARS`)
  - 이미지(`.png .jpg .gif .webp`), PDF: 파일당 5MB까지
- 메뉴 없이 지정하기: `uv run main.py --memory memory/mc.md --ref refs/조작법.md --ref refs/제작법.png "목표"` 또는 환경 변수 `PC_AGENT_MEMORY`, `PC_AGENT_REFS`(쉼표 구분). 메뉴에서 Enter를 누르면 이 값이 그대로 유지됩니다.
- `--no-pick`: 메뉴를 건너뜀 / `--pick`: 폴더가 비어 있어도 메뉴를 보여줌. `bench.py`는 메뉴 없이 `--memory`, `--ref`로 지정합니다.
- 메뉴는 게임 창으로 포커스를 옮기기 전에 나오므로, 터미널에서 답하면 됩니다.
- 참고 자료는 첫 메시지에 들어가 대화 내내 입력 토큰을 차지합니다 (prompt caching으로 대부분 캐시 읽기 가격). 꼭 필요한 것만 고르세요. `prune` 전략도 참고 이미지는 지우지 않습니다.

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
| `PC_AGENT_ASSIST` | (없음) | 켤 보조 도구: `uia`, `wait`, `game`, `minecraft`, `all` |
| `PC_AGENT_CONTEXT` | `server` | 컨텍스트 전략: `server`, `prune`, `none` |
| `PC_AGENT_INPUT` | `pyautogui` | 입력 백엔드: `pyautogui`, `directinput` |
| `PC_AGENT_WINDOW` | (없음) | 이 문자열이 제목에 들어간 창만 캡처하고, 입력 전에 활성 창으로 만듦 |
| `PC_AGENT_MEMORY` | (없음) | 지식 메모 파일. 비우면 끔 |
| `PC_AGENT_MEMORY_REFLECT` / `_MAX_CHARS` | `1` / `4000` | 작업 후 교훈 정리 여부 / 첫 메시지에 넣을 메모 최대 글자 수 |
| `PC_AGENT_REFS` | (없음) | 참고 자료 파일들 (쉼표 구분) |
| `PC_AGENT_REFS_MAX_CHARS` | `20000` | 참고 자료 텍스트 전체 최대 글자 수 |
| `PC_AGENT_MEMORY_DIR` / `PC_AGENT_REFS_DIR` | `memory` / `refs` | 시작 메뉴가 보여줄 폴더 |
| `PC_AGENT_CLICK_SETTLE` / `_HOLD` | 백엔드 기본값 | 커서 이동 후 클릭까지 / 버튼을 누르고 있는 시간(초). directinput 0.05 / 0.05, pyautogui 0 / 0 |
| `PC_AGENT_PROFILE` / `PC_AGENT_PROFILES_DIR` | (없음) / `profiles` | 기본 프로필 / 프로필 폴더 |
| `PC_AGENT_KILL_KEY` | `f12` | 긴급 정지 단축키 (F1~F24, `pause`, `scrolllock`). 빈 값이면 끔 |
| `PC_AGENT_GAME_FOV` | `70` | game 도구: 게임의 세로 시야각(도) |
| `PC_AGENT_GAME_COUNTS_PER_DEG` | `6.667` | game 도구: 시점 1도당 마우스 이동량 (마인크래프트 기본 감도) |
| `PC_AGENT_PROMPT_CACHE` | `1` | `0`이면 캐시 중단점을 넣지 않음 |
| `PC_AGENT_CLEAR_TRIGGER` / `_KEEP` / `_AT_LEAST` | `40000` / `6` / `10000` | server 전략: 발동 입력 토큰 / 남길 도구 결과 수 / 한 번에 최소로 지울 토큰 |
| `PC_AGENT_PRUNE_KEEP` / `_BATCH` | `3` / `10` | prune 전략: 남길 스크린샷 수 / 몰아서 지울 단위 |
