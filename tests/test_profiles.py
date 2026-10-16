"""프로필: 불러오기, 검증, config 적용, 모드별 시스템 프롬프트, 새 프로필, 시작 메뉴."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
from agent import loop, profiles

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(monkeypatch):
    """config의 값을 테스트마다 원래대로 되돌린다."""
    for attr in ("MODEL", "MAX_STEPS", "WINDOW", "INPUT_BACKEND", "ASSIST", "MEMORY_FILE", "REFS", "GAME_FOV",
                 "GAME_COUNTS_PER_DEG", "CLICK_SETTLE", "CLICK_HOLD", "MODE", "PROFILE_NAME", "PROFILE_PROMPT",
                 "CONTEXT", "KILL_KEY"):
        monkeypatch.setattr(config, attr, getattr(config, attr))
    return config


def write(tmp_path, text, name="p.toml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_shipped_profiles_load_and_apply(cfg):
    keys = {p.key: p for p in profiles.list_profiles(ROOT / "profiles")}
    assert {"desktop", "minecraft"} <= set(keys)
    profiles.apply(keys["minecraft"], cfg)
    assert cfg.MODE == "game" and cfg.WINDOW == "Minecraft" and cfg.INPUT_BACKEND == "directinput"
    assert cfg.ASSIST == ["game", "minecraft"] and cfg.GAME_FOV == 70 and cfg.CLICK_HOLD == 0.05
    profiles.apply(keys["desktop"], cfg)
    assert cfg.MODE == "desktop" and cfg.ASSIST == [] and cfg.INPUT_BACKEND == "pyautogui"


def test_game_mode_defaults_and_untouched_keys(cfg, tmp_path):
    cfg.MAX_STEPS = 30
    p = profiles.load(write(tmp_path, 'name = "테라리아"\nmode = "game"\nwindow = "Terraria"\n'))
    applied = profiles.apply(p, cfg)
    assert cfg.INPUT_BACKEND == "directinput" and cfg.ASSIST == ["game"]  # game 모드 기본값
    assert cfg.MAX_STEPS == 30  # 프로필에 없으면 그대로
    assert "max_steps" not in applied and cfg.PROFILE_NAME == "테라리아"


@pytest.mark.parametrize("text,msg", [
    ('mode = "console"', "mode"),
    ('windw = "x"', "windw"),
    ('[camera]\nfoV = 1', "camera.foV"),
    ('assist = "game"', "목록"),
    ('name = ', "형식 오류"),
])
def test_invalid_profiles_are_rejected(tmp_path, text, msg):
    with pytest.raises(ValueError, match=msg):
        profiles.load(write(tmp_path, text))


def test_unknown_assist_group_rejected_on_apply(cfg, tmp_path):
    p = profiles.load(write(tmp_path, 'assist = ["ocr"]'))
    with pytest.raises(ValueError):
        profiles.apply(p, cfg)


def test_system_prompt_by_mode(cfg):
    cfg.MODE, cfg.PROFILE_PROMPT, cfg.PROFILE_NAME = "desktop", "", ""
    assert loop.build_system_prompt(None) == loop.SYSTEM_PROMPT
    cfg.MODE, cfg.PROFILE_NAME, cfg.PROFILE_PROMPT = "game", "마인크래프트", "- 인벤토리는 e"
    hint = SimpleNamespace(names=["look"], prompt_hints=lambda: "- 힌트")
    text = loop.build_system_prompt(hint)
    assert text.startswith(loop.GAME_SYSTEM_PROMPT)
    assert "마인크래프트 안내:\n- 인벤토리는 e" in text and text.endswith("보조 도구:\n- 힌트\n")


def test_new_profile_template(tmp_path):
    path = profiles.new_profile("terraria", tmp_path, "game", "Terraria")
    p = profiles.load(path)
    assert p.mode == "game" and p.data["window"] == "Terraria" and p.name == "terraria"
    with pytest.raises(FileExistsError):
        profiles.new_profile("terraria", tmp_path)
    with pytest.raises(ValueError):
        profiles.new_profile("a/b", tmp_path)
    desk = profiles.load(profiles.new_profile("office", tmp_path, "desktop"))
    assert desk.mode == "desktop" and "window" not in desk.data


def test_find_and_template_files_hidden(tmp_path):
    assert profiles.find("minecraft", "profiles") == Path("profiles/minecraft.toml")
    assert profiles.find("x/y.toml", "profiles") == Path("x/y.toml")
    with pytest.raises(ValueError, match="있는 프로필: a"):
        write(tmp_path, 'name = "보임"', "a.toml")
        profiles.load(tmp_path / "nope.toml")
    write(tmp_path, 'name = "숨김"', "_template.toml")
    assert [p.name for p in profiles.list_profiles(tmp_path)] == ["보임"]


def test_pick_menu(tmp_path):
    write(tmp_path, 'name = "Windows 조작"\nmode = "desktop"', "desktop.toml")
    write(tmp_path, 'name = "마인크래프트"\nmode = "game"', "minecraft.toml")
    printed = []

    def run(*answers, current=""):
        it = iter(answers)
        return profiles.pick(tmp_path, current, input_fn=lambda _: next(it), print_fn=printed.append)

    assert run("2").key == "minecraft"
    assert run("9", "MINECRAFT").key == "minecraft"
    assert run("0") is None
    assert run("", current="desktop").key == "desktop"
    assert run("") is None
    assert any("[게임 조작]" in p for p in printed) and any("다시 입력하세요" in p for p in printed)


def test_main_profile_then_cli_overrides(cfg, monkeypatch, tmp_path):
    import main

    write(tmp_path, 'name = "게임"\nmode = "game"\nmemory = "memory/g.md"\nrefs = ["refs/a.md"]', "g.toml")
    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path))
    args = main.parse_args(["--profile", "g", "--memory", "none", "목표"])
    main.choose_profile(args, interactive=False)
    main.choose_files(args, interactive=False)
    assert cfg.MODE == "game" and cfg.MEMORY_FILE == "" and cfg.REFS == ["refs/a.md"]


def test_main_new_profile(monkeypatch, tmp_path, capsys):
    import main

    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["main.py", "--new-profile", "terraria", "--window", "Terraria"])
    main.main()
    assert (tmp_path / "terraria.toml").exists()
    assert "프로필을 만들었습니다" in capsys.readouterr().out
