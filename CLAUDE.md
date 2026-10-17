# pc-agent

Claude API의 computer use(`computer_toolset_20260801`)를 직접 구동하는 Windows용 에이전트 하네스. 리서치/실험용.
최종 목표: 순수 computer use 기준 성능을 먼저 측정한 뒤, 보조 기능(UIA 요소 트리, 화면 변화 감지 등)을 붙여 개선 폭을 비교한다. 이후 마인크래프트 에이전트로 확장할 예정이다.

## 실행
- `uv sync` 후 `uv run main.py [--profile 이름] [--memory 파일] [--ref 파일 ...] [--pick|--no-pick] "목표"` (시작 메뉴: 프로필 → 메모 → 참고 자료)
- 프로필: `profiles/<이름>.toml` (mode = desktop | game). 새 프로필은 `uv run main.py --new-profile 이름 --mode game --window 창제목`
- 환경 변수: `ANTHROPIC_API_KEY` (필수), `PC_AGENT_MODEL`, `PC_AGENT_MAX_STEPS`, `PC_AGENT_MAX_LONG_EDGE`, `PC_AGENT_MONITOR`, `PC_AGENT_ASSIST` (보조 도구: uia, wait, game, minecraft, all), `PC_AGENT_CONTEXT` (server, prune, none), `PC_AGENT_INPUT` (pyautogui, directinput), `PC_AGENT_WINDOW` (이 제목의 창만 캡처/조작), `PC_AGENT_MEMORY` (지식 메모 파일), `PC_AGENT_REFS` (참고 자료, 쉼표 구분), `PC_AGENT_KILL_KEY` (기본 f12), `PC_AGENT_CLICK_SETTLE`/`_HOLD` (게임 클릭 타이밍), `PC_AGENT_GAME_FOV`, `PC_AGENT_GAME_COUNTS_PER_DEG`
- 실행 기록: `runs/<시각>/` (스크린샷 PNG + actions.jsonl)
- 프로필 고르기 창: `uv run launcher.py` (tkinter, 고른 프로필로 새 콘솔에서 main.py 실행)
- 벤치마크: `uv run bench.py [--tasks a,b] [--repeat N] [--label 이름] [--assist uia,wait] [--context server|prune|none] [--input pyautogui|directinput]` → `runs/bench-<시각>/` (results.jsonl, summary.json)
- 테스트: `uv run pytest` (순수 모듈만)

## 구조
- `main.py`: 진입점. DPI 설정을 가장 먼저 호출한다 (pyautogui import 전)
- `launcher.py`: 프로필 고르기 창 (tkinter). 목록/상세 보기/실행 명령은 순수 함수, 실행은 `--child`로 새 콘솔에서 main.py를 돌림
- `bench.py`: 벤치마크 진입점. 과제 반복 실행, 자동/수동 판정, 결과 저장
- `agent/loop.py`: 에이전트 루프, 시스템 프롬프트, 배치 처리. `run()`은 `RunResult`(상태, 단계, 행동, 토큰, 캐시 토큰)를 반환
- `agent/profiles.py`: 프로필 불러오기·검증·config 적용, 새 프로필 템플릿, 시작 메뉴. mode가 시스템 프롬프트(`loop.BASE_PROMPTS`)를 정함
- `agent/memory.py`: 지식 메모 (remember/forget 도구, Markdown 파일, 첫 메시지 주입 문구). 작업 후 정리는 `loop.reflect`
- `agent/refs.py`: 참고 자료 → content 블록(텍스트/이미지/PDF), 시작 메뉴 `pick()` (input/print 주입, 순수 로직)
- `agent/context.py`: 컨텍스트 관리 (캐시 중단점, 서버 측 clearing 설정, 클라이언트 가지치기). 순수 모듈
- `benchmark/tasks.py`: 고정 과제 세트 (setup/check). 과제를 바꾸면 `TASK_SET_VERSION`을 올린다
- `benchmark/metrics.py`: 결과 집계와 표 출력 (순수 모듈)
- `perception/capture.py`: 캡처, 축소, 스크린샷↔화면 좌표 변환, zoom. `region`을 주면 그 영역(게임 창)만 캡처
- `perception/window.py`: 창 찾기(`pick_window`는 순수 함수), 클라이언트 영역, 포커스. `open_screen()`이 main/bench의 Screen을 만든다
- `actions/executor.py`: 17개 멤버 도구 → 입력 백엔드 호출 (pyautogui를 직접 부르지 않는다)
- `actions/backends.py`: 교체 가능한 입력 백엔드 (pyautogui / directinput = pydirectinput-rgx). 긴급 정지 판정 `is_failsafe`
- `actions/assist.py`: 보조 custom 도구 (list_ui_elements, click_element, wait_for_change, look, look_at, hold, move_item, find_slots, click_slot) 정의와 실행
- `actions/camera.py`: 게임 시점 회전 계산 (스크린샷 좌표 → 각도 → 마우스 상대 이동량). 순수 모듈
- `perception/mc_slots.py`: 마인크래프트 인벤토리 계열 화면의 칸 배치(바닐라 좌표)와 판정(테두리 색으로 화면 종류·GUI 배율·레시피 책 찾기). 순수 모듈
- `perception/uia.py`: UIA 트리 탐색 (Windows 전용, uia를 켤 때만 import)
- `perception/elements.py`, `perception/diff.py`: 요소 목록 형식, 화면 변화 판정 (순수 모듈)
- `actions/keys.py`: xdotool 스타일 키 이름 → pyautogui 키 이름 (순수 함수)
- `safety/guard.py`: 위험 키/텍스트 입력 전 y/n 확인
- `safety/killswitch.py`: 긴급 정지 단축키 감시 (Windows GetAsyncKeyState), `check()`/`sleep()`이 `EmergencyStop`(KeyboardInterrupt 하위)을 던짐
- `logs/recorder.py`: 실행 기록

## computer_toolset_20260801 규칙 (어기면 API가 요청을 거부함)
- beta 헤더 없음. `client.messages.create`의 `tools=[{"type": "computer_toolset_20260801"}]`
- `name`, `display_width_px`, `display_height_px`, `display_number`, `enable_zoom`은 넣으면 안 됨
- 응답의 tool_use 블록은 `name`이 멤버 이름(left_click 등), `toolset_name == "computer"`, `input`에 `action` 필드 없음
- 한 응답의 모든 tool_use 블록을 순서대로 실행하고, 각각에 tool_result를 하나씩, 전부 다음 user 메시지에 담아 반환
- 모든 tool_result에 `"toolset_name": "computer"` 포함
- 첫 실패 이후 블록은 실행하지 않고 `is_error: true` + `"Not executed: an earlier computer action in this turn failed."`
- custom 도구(보조 도구)는 같은 `tools` 배열에 함께 선언한다. custom 도구의 tool_use에는 `toolset_name`이 없고, 그 tool_result에도 넣지 않는다
- 이 하네스는 custom 도구가 실패해도 이후 블록을 전부 실행하지 않는다 (뒤 동작은 앞 동작의 성공을 전제로 하므로)
- 좌표는 항상 우리가 보낸 스크린샷의 픽셀 좌표. 스크린샷은 직접 축소해서 보내야 함 (API가 줄여주지 않음)
- 문서: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool

## 컨텍스트 관리 규칙
- `system`과 `tools`는 실행 중에 절대 바꾸지 않는다 (캐시와 preserved thinking이 모두 깨짐)
- 캐시 중단점은 요청 직전 사본에만 붙인다 (`with_cache_breakpoints`). 최대 4개: system 1 + 최근 user 메시지 3
- 서버 측 clearing: `client.beta.messages.create(betas=["context-management-2025-06-27"], context_management={"edits": [clear_tool_uses_20250919]})`. 대화 기록 자체는 바뀌지 않으므로 모든 모델에서 안전
- 클라이언트 가지치기는 대화 기록을 고치므로 Opus 5.5 / Fable 5.1에서는 쓰지 않는다 (`resolve_strategy`가 server로 바꿈). 매 턴이 아니라 몰아서 지운다

## 개발 로드맵
1. [x] 최소 루프 (스크린샷 → Claude → 실행)
2. [x] 좌표 보정 (DPI 인식, 축소 비율 역변환)
3. [x] 안전장치 + 로그 (기본형)
4. [ ] 기준 성능 측정: 고정 과제 세트를 만들어 성공률/단계 수/토큰 기록 (측정 도구 완료, Windows에서 실측 필요)
5. [ ] 보조 도구: `uiautomation`으로 UI 요소 목록 + `click_element` 커스텀 도구, `wait_for_change` (구현 완료, Windows에서 동작 확인과 기준 성능 대비 비교 필요)
6. [ ] 컨텍스트 관리: 스크린샷 누적 대응 (Opus 5.5/Fable 5.1은 클라이언트 측 가지치기 대신 서버 측 tool result clearing 권장) (구현 완료, Windows에서 전략별 비용 비교 필요)
7. [ ] 입력 백엔드 교체 가능하게 (게임용 `pydirectinput`) (구현 완료, Windows/게임에서 동작 확인 필요)
8. [ ] 게임 보조 도구 `game` (look, look_at, hold) + 긴급 정지 단축키 + 종료 시 release_all (구현 완료, 마인크래프트에서 감도/FOV 보정과 동작 확인 필요)
9. [ ] 게임 창만 캡처 + 입력 전 포커스 되돌리기 (`PC_AGENT_WINDOW`) (구현 완료, Windows에서 확인 필요)
10. [ ] 지식 메모: 플레이 사이에 지식 저장/재사용 (`PC_AGENT_MEMORY`) (구현 완료, 메모 유무에 따른 회차별 비교 필요)
11. [ ] 참고 자료 고르기 + 시작 메뉴 (구현 완료)
12. [ ] 마인크래프트 칸 찾기 `minecraft` (find_slots, click_slot, move_item 칸 번호) (구현 완료, 실제 게임에서 확인 필요)
13. [x] 프로필: Windows 조작 / 게임 조작 선택, 게임별 설정·안내를 파일 하나로 (`profiles/`)
14. [ ] 이후: 생각하는 동안 일시정지, 게임 상태 도구, 게임 과제 세트

## 규칙
- 마우스/키보드 입력은 반드시 `executor.input`(입력 백엔드)을 통한다. 새 코드에서 pyautogui/pydirectinput를 직접 부르지 않는다
- 긴급 정지는 `backends.is_failsafe(err)`로 판정한다 (백엔드마다 예외 클래스가 다름). 단축키 정지는 `killswitch.EmergencyStop`
- 행동 실행 중 기다릴 때는 `time.sleep` 대신 `killswitch.sleep`을 쓴다 (긴급 정지 시 바로 깨어남). 실행이 끝나면 `backend.release_all()`로 눌린 입력을 전부 뗀다
- 입력을 보내는 새 도구는 실행 전에 `executor.ensure_focus()`를 거친다 (Executor는 `OBSERVE_ONLY` 외 전부, 보조 도구는 `INPUT_TOOLS`)
- 클릭은 `executor.press()`/`click_at()`을 쓴다 (백엔드의 `click_settle`/`click_hold`를 지킴). 게임 인벤토리 조작은 드래그가 아니라 집기·놓기 클릭이다
- 이 코드는 Windows에서만 실제로 동작한다. Linux/CI에서는 순수 모듈과, `tests/conftest.py`의 가짜 `pyautogui`로 루프 로직만 테스트한다 (`uv run pytest`).
- 참고 자료(읽기 전용)와 지식 메모는 첫 user 메시지에만 넣는다. prune은 참고 이미지를 `protect`로 지키지 않으면 지워 버린다
- 시작 메뉴는 게임 창 포커스 전에 띄운다 (`window.open_screen`보다 먼저)
- 지식 메모는 첫 user 메시지에만 넣는다 (system/tools는 실행 중 고정). 작업 후 정리 단계에서는 remember/forget 외 도구를 실행하지 않는다
- 새 게임은 코드가 아니라 프로필로 추가한다. 특정 게임 전용 코드가 필요하면 보조 도구 묶음으로 만들고 프로필의 assist로 켠다
- 프로필 항목을 추가하면 `profiles.SIMPLE_KEYS`/`TABLE_KEYS`, 템플릿, README 표를 함께 고친다
- 사용자 메시지/주석/로그는 한국어로 작성한다.
