"""경험 기억: 교훈 저장·중복 갱신·관련 교훈 고르기·성공/실패 반영."""
from agent import memory


def sample():
    lessons = []
    lessons, mc, _ = memory.add(lessons, "마인크래프트 게임 화면에서 시점 돌리기",
                                "mouse_move로는 시점이 돌지 않음", "look 행동으로 delta [300, 0]씩 돌린다",
                                ["마인크래프트", "시점"], now=1)
    lessons, chat, _ = memory.add(lessons, "마인크래프트 채팅으로 명령어 입력",
                                  "/ 키로 열고 /give를 또 입력해 슬래시가 두 개가 됨",
                                  "t로 채팅창을 연 뒤 /give ... 를 입력한다", ["마인크래프트", "명령어", "채팅"], now=2)
    lessons, note, _ = memory.add(lessons, "메모장에 한글 입력", "type이 느림", "type은 클립보드로 붙여 넣으니 그대로 쓴다",
                                  ["메모장"], now=3)
    return lessons, mc, chat, note


def test_tokens_handle_korean_particles():
    assert tokens_overlap("마인크래프트에서", "마인크래프트를")


def tokens_overlap(a, b):
    return memory.tokens(a) & memory.tokens(b)


def test_pick_relevant_first():
    lessons, mc, chat, note = sample()
    picked = memory.pick(lessons, "마인크래프트에서 /give 명령어로 나무를 받아줘")
    assert picked[0]["id"] == chat["id"] and note["id"] not in [l["id"] for l in picked]
    assert memory.pick(lessons, "계산기 열어줘") == []          # 관련 없으면 넣지 않는다
    text = memory.as_prompt(picked)
    assert text.startswith("[이전 실행에서 배운 점]") and "t로 채팅창" in text


def test_duplicate_updates_instead_of_adding():
    lessons, mc, chat, note = sample()
    lessons2, updated, was_update = memory.add(lessons, "마인크래프트 게임 화면에서 시점 돌리기",
                                               "mouse_move로는 시점이 돌지 않음", "look delta [150, 0]이 90도쯤",
                                               ["감도"], now=9)
    assert was_update and len(lessons2) == 3
    assert updated["id"] == mc["id"] and updated["revisions"] == 2 and "감도" in updated["keywords"]
    assert "150" in updated["solution"]


def test_feedback_changes_ranking(tmp_path):
    lessons, mc, chat, note = sample()
    lessons = memory.feedback(lessons, [chat["id"]], succeeded=False)
    lessons = memory.feedback(lessons, [chat["id"]], succeeded=False)
    lessons = memory.feedback(lessons, [mc["id"]], succeeded=True)
    by_id = {l["id"]: l for l in lessons}
    assert by_id[chat["id"]]["failure"] == 2 and by_id[mc["id"]]["success"] == 1
    assert memory.trust(by_id[mc["id"]]) > memory.trust(by_id[chat["id"]])
    f = tmp_path / "lessons.json"
    memory.save(f, lessons)
    assert [l["id"] for l in memory.load(f)] == [l["id"] for l in lessons]


def test_prune_keeps_trusted():
    lessons = []
    for i in range(5):
        lessons, l, _ = memory.add(lessons, f"상황{i} 고유어{i}{i}", f"문제{i}", "해결", now=i)
    lessons = memory.feedback(lessons, [lessons[4]["id"]], succeeded=True)
    kept = memory.prune(lessons, limit=2)
    assert len(kept) == 2 and lessons[4]["id"] in [l["id"] for l in kept]


def test_sdk_remember_tool(tmp_path, monkeypatch):
    import asyncio

    import pytest
    pytest.importorskip("claude_agent_sdk")
    import config
    from agent import sdk_loop
    from agent.loop import RunResult
    from tests.test_batch import FakeExecutor, FakeRecorder

    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path))
    tools = sdk_loop._Tools(FakeExecutor(), FakeRecorder(), RunResult(), assist=None, remember=True)
    assert "remember_lesson" in [t.name for t in tools.build()]
    args = {"situation": "마인크래프트 채팅", "problem": "슬래시 두 개", "solution": "t로 열고 /give 입력",
            "keywords": ["마인크래프트"]}
    out = asyncio.run(tools.remember_tool(args))
    assert "새로 저장" in out["content"][1]["text"]
    out2 = asyncio.run(tools.remember_tool({**args, "solution": "t로 열고 슬래시 하나로 입력"}))
    assert "고쳐 썼습니다" in out2["content"][1]["text"]
    saved = memory.load(tmp_path / "lessons.json")
    assert len(saved) == 1 and saved[0]["solution"] == "t로 열고 슬래시 하나로 입력"
    assert "remember_lesson" in sdk_loop.system_prompt(None, False, remember=True)
