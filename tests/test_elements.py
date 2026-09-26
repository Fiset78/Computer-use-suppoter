from perception.elements import UIElement, filter_elements, format_elements


def el(kind="ButtonControl", name="저장", rect=(100, 100, 200, 140), **kw):
    return UIElement(kind=kind, name=name, rect=rect, **kw)


def test_filter_drops_unknown_kinds_unnamed_and_tiny():
    items = [
        el(),
        el(kind="PaneControl", name="패널"),        # 목록에 안 넣는 종류
        el(name=""),                                # 이름 없는 버튼
        el(kind="EditControl", name=""),            # 이름 없어도 입력칸은 유지
        el(name="작음", rect=(0, 0, 1, 1)),
    ]
    out = filter_elements(items)
    assert [(e.kind, e.name) for e in out] == [("ButtonControl", "저장"), ("EditControl", "")]


def test_filter_query_matches_name_or_value_case_insensitive():
    items = [el(name="Save"), el(name="열기"), el(kind="EditControl", name="", value="hello SAVE")]
    out = filter_elements(items, "save")
    assert [e.name for e in out] == ["Save", ""]


def test_filter_dedupes_and_respects_view():
    items = [el(), el(), el(name="밖", rect=(5000, 0, 5100, 40))]
    out = filter_elements(items, in_view=lambda x, y: x < 1920)
    assert len(out) == 1


def test_format_uses_shot_coordinates_and_ids():
    items = [el(), el(kind="EditControl", name="검색", value="abc", enabled=False)]
    text = format_elements(items, to_shot=lambda x, y: (x // 2, y // 2), window_title="메모장", total=5)
    lines = text.splitlines()
    assert lines[0] == '활성 창: "메모장"'
    assert lines[1] == '[1] 버튼 "저장" (75,60)'
    assert lines[2] == '[2] 입력칸 "검색" 값="abc" (비활성) (75,60)'
    assert "3개 생략" in lines[3]


def test_format_empty():
    assert "없습니다" in format_elements([], to_shot=lambda x, y: (x, y))
