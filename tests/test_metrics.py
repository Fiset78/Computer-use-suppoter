from benchmark.metrics import aggregate, format_table, summarize


def rec(task, success, steps=5, inp=1000, out=100, seconds=10.0):
    return {"task": task, "success": success, "status": "done", "steps": steps,
            "actions": steps * 2, "action_errors": 0, "input_tokens": inp,
            "output_tokens": out, "seconds": seconds}


def test_aggregate_success_rate_and_means():
    agg = aggregate([rec("a", True, steps=4), rec("a", False, steps=30)])
    assert agg["runs"] == 2
    assert agg["success_rate"] == 0.5
    assert agg["avg_steps"] == 17
    assert agg["avg_steps_success"] == 4


def test_unjudged_runs_excluded_from_rate():
    agg = aggregate([rec("a", True), rec("a", None)])
    assert agg["runs"] == 2
    assert agg["judged"] == 1
    assert agg["success_rate"] == 1.0


def test_no_judged_runs():
    agg = aggregate([rec("a", None)])
    assert agg["success_rate"] is None
    assert agg["avg_steps_success"] is None


def test_summarize_groups_by_task_in_order():
    s = summarize([rec("b", True), rec("a", False), rec("b", False)])
    assert list(s["tasks"]) == ["b", "a"]
    assert s["tasks"]["b"]["success_rate"] == 0.5
    assert s["overall"]["runs"] == 3


def test_format_table_contains_rows():
    table = format_table(summarize([rec("calc", True), rec("note", None)]))
    assert "calc" in table and "note" in table and "(전체)" in table
    assert "100%" in table
