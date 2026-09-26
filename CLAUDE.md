# pc-agent

Claude API의 computer use(`computer_toolset_20260801`)를 직접 구동하는 Windows용 에이전트 하네스. 리서치/실험용.
최종 목표: 순수 computer use 기준 성능을 먼저 측정한 뒤, 보조 기능(UIA 요소 트리, 화면 변화 감지 등)을 붙여 개선 폭을 비교한다. 이후 마인크래프트 에이전트로 확장할 예정이다.

## 실행
- `uv sync` 후 `uv run main.py "목표"`
- 환경 변수: `ANTHROPIC_API_KEY` (필수), `PC_AGENT_MODEL`, `PC_AGENT_MAX_STEPS`, `PC_AGENT_MAX_LONG_EDGE`, `PC_AGENT_MONITOR`, `PC_AGENT_ASSIST` (보조 도구: uia, wait, all)
- 실행 기록: `runs/<시각>/` (스크린샷 PNG + actions.jsonl)
- 벤치마크: `uv run bench.py [--tasks a,b] [--repeat N] [--label 이름] [--assist uia,wait]` → `runs/bench-<시각>/` (results.jsonl, summary.json)
- 테스트: `uv run pytest` (순수 모듈만)

## 구조
- `main.py`: 진입점. DPI 설정을 가장 먼저 호출한다 (pyautogui import 전)
- `bench.py`: 벤치마크 진입점. 과제 반복 실행, 자동/수동 판정, 결과 저장
- `agent/loop.py`: 에이전트 루프, 시스템 프롬프트, 배치 처리. `run()`은 `RunResult`(상태, 단계, 행동, 토큰)를 반환
- `benchmark/tasks.py`: 고정 과제 세트 (setup/check). 과제를 바꾸면 `TASK_SET_VERSION`을 올린다
- `benchmark/metrics.py`: 결과 집계와 표 출력 (순수 모듈)
- `perception/capture.py`: 캡처, 축소, 스크린샷↔화면 좌표 변환, zoom
- `actions/executor.py`: 17개 멤버 도구 → pyautogui 동작
- `actions/assist.py`: 보조 custom 도구 (list_ui_elements, click_element, wait_for_change) 정의와 실행
- `perception/uia.py`: UIA 트리 탐색 (Windows 전용, uia를 켤 때만 import)
- `perception/elements.py`, `perception/diff.py`: 요소 목록 형식, 화면 변화 판정 (순수 모듈)
- `actions/keys.py`: xdotool 스타일 키 이름 → pyautogui 키 이름 (순수 함수)
- `safety/guard.py`: 위험 키/텍스트 입력 전 y/n 확인
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

## 개발 로드맵
1. [x] 최소 루프 (스크린샷 → Claude → 실행)
2. [x] 좌표 보정 (DPI 인식, 축소 비율 역변환)
3. [x] 안전장치 + 로그 (기본형)
4. [ ] 기준 성능 측정: 고정 과제 세트를 만들어 성공률/단계 수/토큰 기록 (측정 도구 완료, Windows에서 실측 필요)
5. [ ] 보조 도구: `uiautomation`으로 UI 요소 목록 + `click_element` 커스텀 도구, `wait_for_change` (구현 완료, Windows에서 동작 확인과 기준 성능 대비 비교 필요)
6. [ ] 컨텍스트 관리: 스크린샷 누적 대응 (Opus 5.5/Fable 5.1은 클라이언트 측 가지치기 대신 서버 측 tool result clearing 권장)
7. [ ] 입력 백엔드 교체 가능하게 (게임용 `pydirectinput`)

## 규칙
- 이 코드는 Windows에서만 실제로 동작한다. Linux/CI에서는 순수 모듈과, `tests/conftest.py`의 가짜 `pyautogui`로 루프 로직만 테스트한다 (`uv run pytest`).
- 사용자 메시지/주석/로그는 한국어로 작성한다.
