from actions.keys import normalize_key, parse_combo, parse_modifiers


def test_normalize_named_keys():
    assert normalize_key("Return") == "enter"
    assert normalize_key("Escape") == "esc"
    assert normalize_key("super") == "win"
    assert normalize_key("Page_Down") == "pagedown"


def test_normalize_function_and_keypad():
    assert normalize_key("F5") == "f5"
    assert normalize_key("KP_7") == "num7"


def test_normalize_single_char_lowercased():
    assert normalize_key("A") == "a"


def test_parse_combo():
    assert parse_combo("ctrl+s") == ["ctrl", "s"]
    assert parse_combo("ctrl+shift+T") == ["ctrl", "shift", "t"]
    assert parse_combo("alt+Tab") == ["alt", "tab"]


def test_parse_combo_plus_key():
    assert parse_combo("+") == ["+"]
    assert parse_combo("ctrl++") == ["ctrl", "+"]


def test_parse_modifiers_empty():
    assert parse_modifiers(None) == []
    assert parse_modifiers("") == []
    assert parse_modifiers("shift") == ["shift"]
