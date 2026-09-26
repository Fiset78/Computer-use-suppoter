import pytest

from config import parse_assist


def test_parse_assist():
    assert parse_assist(None) == []
    assert parse_assist("") == []
    assert parse_assist("none") == []
    assert parse_assist("wait, UIA") == ["uia", "wait"]
    assert parse_assist("all") == ["uia", "wait"]


def test_parse_assist_unknown():
    with pytest.raises(ValueError):
        parse_assist("uia,ocr")
