# pc-agent

Claude로 Windows PC를 조작하는 에이전트 하네스. 리서치/실험용. 엔진 두 가지:
- `sdk` (기본): Claude Agent SDK + Claude Code 구독 로그인. API 키 불필요. custom 도구 `computer`(행동 배열)를 in-process MCP로 제공
- `api`: Messages API의 computer use(`computer_toolset_20260801`)를 직접 구동. `ANTHROPIC_API_KEY` 필요
최종 목표: 순수 computer use 기준 성능을 먼저 측정한 뒤, 보조 기능(UIA 요소 트리, 화면 변화 감지 등)을 붙여 개선 폭을 비교한다. 이후 마인크래프트 에이전트로 확장할 예정이다.

## 실행
- `uv sync` 후 `uv run main.py "목표"`
- 실행 창(터미널 없이, 음성 입력): `uv run app.py`. 바탕화면 바로가기는 `install_shortcut.ps1` (pythonw로 콘솔 없이 실행)
- sdk 엔진은 미리 `claude`를 실행해 구독 계정으로 로그인해 둔다. api 엔진은 `ANTHROPIC_API_KEY` 필요
- 환경 변수: `PC_AGENT_ENGINE` (sdk, api), `PC_AGENT_WEB` (1이면 WebSearch/WebFetch 켜기, sdk 전용), `PC_AGENT_MODEL`, `PC_AGENT_MAX_STEPS`, `PC_AGENT_MAX_LONG_EDGE`, `PC_AGENT_MONITOR`, `PC_AGENT_ASSIST` (보조 도구: uia, wait, all), `PC_AGENT_CONTEXT` (server, prune, none), `PC_AGENT_INPUT` (pyautogui, directinput), `PC_AGENT_WHISPER_MODEL` (음성 인식 모델, 기본 large-v3-turbo), `PC_AGENT_HOTKEY` (실행 창 전역 단축키, 기본 ctrl+alt+space)
- 실행 기록: `runs/<시각>/` (스크린샷 PNG + actions.jsonl)
- 벤치마크: `uv run bench.py [--tasks a,b] [--repeat N] [--label 이름] [--assist uia,wait] [--context server|prune|none] [--input pyautogui|directinput] [--engine sdk|api] [--web on|off]` → `runs/bench-<시각>/` (results.jsonl, summary.json)
- 테스트: `uv run pytest` (순수 모듈만)

## 구조
- `main.py`: 진입점. DPI 설정을 가장 먼저 호출한다 (pyautogui import 전)
- `app.py`: 실행 창 (tkinter). 창은 최소화 상태를 유지하고(단축키·실행·대화상자 모두 창을 띄우지 않음) 상태는 화면 구석 알림(`Overlay`, 에이전트 실행 중에는 숨김)으로 보여 준다. 정지 버튼(`Executor.stop_check` → `StopRequested`), 위험 행동 확인 대화상자(`Guard(ask=)`), print를 창으로 돌림
- `voice/stt.py`: 마이크 녹음(sounddevice) + 음성 인식(faster-whisper, 로컬). `voice/text.py`: 인식 결과 정리, 단어 힌트(initial_prompt, 기본 단어 + `voice_words.txt`), 음량 맞추기 (순수). `voice/endpoint.py`: 말 끝 감지 (소음 측정 → 말 시작 → 1.2초 무음이면 종료, 순수). `voice/tts.py`: 결과 읽어 주기 (Windows System.Speech). `voice/hotkey.py`: 전역 단축키 (Win32 RegisterHotKey, ctypes. 새 DLL을 들이지 않으려고 라이브러리를 쓰지 않음)
- `bench.py`: 벤치마크 진입점. 과제 반복 실행, 자동/수동 판정, 결과 저장
- `agent/hidden.py`: 실행 창에서 Claude Code CLI를 띄울 때 콘솔 창이 뜨지 않게 `anyio.open_process`에 `CREATE_NO_WINDOW`를 끼워 넣음 (SDK에 옵션이 없어서)
- `agent/engine.py`: 엔진 선택 (`get_runner`). 엔진별 의존성은 고를 때만 import
- `agent/sdk_loop.py`: sdk 엔진. MCP 도구 등록, ClaudeSDKClient 실행, ResultMessage → `RunResult`
- `agent/batch.py`: sdk 엔진의 `computer` 도구 스키마와 배치 실행 규칙 (순수 모듈)
- `agent/loop.py`: api 엔진 에이전트 루프, 시스템 프롬프트, 배치 처리. `run()`은 `RunResult`(상태, 단계, 행동, 토큰, 캐시 토큰)를 반환
- `agent/context.py`: 컨텍스트 관리 (캐시 중단점, 서버 측 clearing 설정, 클라이언트 가지치기). 순수 모듈
- `benchmark/tasks.py`: 고정 과제 세트 (setup/check). 과제를 바꾸면 `TASK_SET_VERSION`을 올린다
- `benchmark/metrics.py`: 결과 집계와 표 출력 (순수 모듈)
- `perception/capture.py`: 캡처, 축소, 스크린샷↔화면 좌표 변환, zoom
- `actions/executor.py`: 17개 멤버 도구 → 입력 백엔드 호출 (pyautogui를 직접 부르지 않는다)
- `actions/backends.py`: 교체 가능한 입력 백엔드 (pyautogui / directinput = pydirectinput-rgx). 긴급 정지 판정 `is_failsafe`
- `actions/assist.py`: 보조 custom 도구 (list_ui_elements, click_element, wait_for_change) 정의와 실행
- `perception/uia.py`: UIA 트리 탐색 (Windows 전용, uia를 켤 때만 import)
- `perception/elements.py`, `perception/diff.py`: 요소 목록 형식, 화면 변화 판정 (순수 모듈)
- `actions/keys.py`: xdotool 스타일 키 이름 → pyautogui 키 이름 (순수 함수)
- `safety/guard.py`: 위험 키/텍스트 입력 전 y/n 확인
- `logs/recorder.py`: 실행 기록

## sdk 엔진 규칙
- 내장 도구는 기본적으로 `tools=[]`로 전부 끈다. `PC_AGENT_WEB=1`일 때만 `WebSearch`, `WebFetch`를 켠다 (Bash/Read 등 파일·셸 도구는 절대 켜지 않음). `allowed_tools`에는 우리 MCP 도구(`mcp__pc__*`)와 켜진 웹 도구만 넣고 `permission_mode="dontAsk"`
- `setting_sources=[]`로 사용자/프로젝트 설정과 CLAUDE.md를 읽지 않는다 (실험 격리)
- `env={"ANTHROPIC_API_KEY": ""}`로 API 키를 CLI에 넘기지 않는다 (구독 로그인 사용)
- `computer` 도구는 첫 실패 이후 행동을 실행하지 않고, 관찰 행동으로 끝나지 않은 배치에 스크린샷을 붙인다 (api 엔진과 같은 규칙)
- 긴급 정지는 도구 결과로 숨기지 않고 `_Tools.abort`에 담아 루프가 interrupt 후 다시 올린다
- MCP 이미지 형식은 `{"type": "image", "data", "mimeType"}` (`batch.to_mcp_content`로 변환)

## computer_toolset_20260801 규칙 (api 엔진) (어기면 API가 요청을 거부함)
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

## 컨텍스트 관리 규칙 (api 엔진. sdk 엔진은 Claude Code가 관리)
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

## 규칙
- 마우스/키보드 입력은 반드시 `executor.input`(입력 백엔드)을 통한다. 새 코드에서 pyautogui/pydirectinput를 직접 부르지 않는다
- 긴급 정지는 `backends.is_failsafe(err)`로 판정한다 (백엔드마다 예외 클래스가 다름). 실행 창의 정지 버튼(`StopRequested`)도 같은 경로로 처리된다
- 이 코드는 Windows에서만 실제로 동작한다. Linux/CI에서는 순수 모듈과, `tests/conftest.py`의 가짜 `pyautogui`로 루프 로직만 테스트한다 (`uv run pytest`).
- 사용자 메시지/주석/로그는 한국어로 작성한다.
