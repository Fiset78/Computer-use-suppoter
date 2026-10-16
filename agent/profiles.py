"""프로필: 무엇을 조작할지(Windows 데스크톱 / 특정 게임)와 그에 맞는 설정을 파일 하나로 묶는다.

profiles/<이름>.toml 예:

    name = "마인크래프트"
    mode = "game"                   # desktop = Windows 조작, game = 게임 조작
    window = "Minecraft"
    assist = ["game", "minecraft"]
    prompt = "- 인벤토리는 e 키"
    [camera]
    fov = 70

- mode가 시스템 프롬프트의 기본 문구를 정한다 (loop.build_system_prompt). game 모드는 따로 적지 않으면
  입력 백엔드를 directinput으로, 보조 도구를 game으로 둔다.
- 적용 순서: 명령줄 옵션 > 프로필 > 환경 변수 > 기본값. 프로필에 없는 항목은 그대로 둔다.
- 오타를 조용히 넘기지 않도록 모르는 항목이 있으면 오류를 낸다.
- 게임 전용 코드(예: 마인크래프트 칸 찾기)는 보조 도구 묶음으로 두고 프로필의 assist로 켠다.

파일 입출력 말고는 GUI 의존성이 없어 Linux에서도 테스트한다.
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MODES = {"desktop": "Windows 조작", "game": "게임 조작"}

# 프로필 키 → (config 속성, 변환 함수)
_FLOAT = float
_INT = int
_STR = str
SIMPLE_KEYS = {
    "model": ("MODEL", _STR),
    "max_steps": ("MAX_STEPS", _INT),
    "max_long_edge": ("MAX_LONG_EDGE", _INT),
    "monitor": ("MONITOR_INDEX", _INT),
    "action_delay": ("ACTION_DELAY", _FLOAT),
    "window": ("WINDOW", _STR),
    "input": ("INPUT_BACKEND", lambda v: str(v).strip().lower()),
    "context": ("CONTEXT", lambda v: str(v).strip().lower()),
    "memory": ("MEMORY_FILE", _STR),
    "kill_key": ("KILL_KEY", lambda v: str(v).strip().lower()),
}
TABLE_KEYS = {
    "camera": {"fov": ("GAME_FOV", _FLOAT), "counts_per_deg": ("GAME_COUNTS_PER_DEG", _FLOAT)},
    "click": {"settle": ("CLICK_SETTLE", _FLOAT), "hold": ("CLICK_HOLD", _FLOAT)},
}
OTHER_KEYS = {"name", "mode", "prompt", "assist", "refs"}

# game 모드에서 프로필이 따로 정하지 않았을 때의 기본값
GAME_DEFAULTS = {"input": "directinput", "assist": ["game"]}


@dataclass
class Profile:
    key: str                  # 파일 이름 (확장자 제외)
    path: Path
    name: str
    mode: str
    prompt: str = ""
    data: dict = field(default_factory=dict)


def load(path: str | Path) -> Profile:
    path = Path(path)
    if not path.is_file():
        others = sorted(p.stem for p in path.parent.glob("*.toml") if not p.name.startswith("_"))
        raise ValueError(f"프로필이 없습니다: {path}" + (f" (있는 프로필: {', '.join(others)})" if others else ""))
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise ValueError(f"프로필 {path} 형식 오류: {err}") from err
    unknown = sorted(set(data) - set(SIMPLE_KEYS) - set(TABLE_KEYS) - OTHER_KEYS)
    for table, keys in TABLE_KEYS.items():
        if table in data:
            if not isinstance(data[table], dict):
                raise ValueError(f"프로필 {path}: [{table}]는 표여야 합니다")
            unknown += [f"{table}.{k}" for k in sorted(set(data[table]) - set(keys))]
    if unknown:
        raise ValueError(f"프로필 {path}: 모르는 항목 {', '.join(unknown)}")
    mode = str(data.get("mode", "desktop")).strip().lower()
    if mode not in MODES:
        raise ValueError(f"프로필 {path}: mode는 {' 또는 '.join(MODES)}여야 합니다 (지금: {mode})")
    if "assist" in data and not isinstance(data["assist"], list):
        raise ValueError(f"프로필 {path}: assist는 목록이어야 합니다 (예: [\"game\"])")
    if "refs" in data and not isinstance(data["refs"], list):
        raise ValueError(f"프로필 {path}: refs는 목록이어야 합니다")
    return Profile(path.stem, path, str(data.get("name", path.stem)), mode,
                   str(data.get("prompt", "")).strip(), data)


def find(key_or_path: str, folder: str | Path) -> Path:
    """"minecraft" → profiles/minecraft.toml. 경로를 주면 그대로."""
    p = Path(key_or_path)
    if p.suffix == ".toml" or p.parent != Path("."):
        return p
    return Path(folder) / f"{key_or_path}.toml"


def list_profiles(folder: str | Path) -> list[Profile]:
    d = Path(folder)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.toml"), key=lambda p: p.name.lower()):
        if p.name.startswith("_"):
            continue  # _template.toml 같은 파일은 목록에서 뺀다
        out.append(load(p))
    return out


def apply(profile: Profile, cfg) -> list[str]:
    """프로필 값을 config 모듈(cfg)에 쓴다. 적용한 항목 이름 목록을 돌려준다."""
    data = dict(profile.data)
    if profile.mode == "game":
        for k, v in GAME_DEFAULTS.items():
            data.setdefault(k, v)
    applied = []
    for key, (attr, conv) in SIMPLE_KEYS.items():
        if key in data:
            setattr(cfg, attr, conv(data[key]))
            applied.append(key)
    for table, keys in TABLE_KEYS.items():
        for key, (attr, conv) in keys.items():
            if key in data.get(table, {}):
                setattr(cfg, attr, conv(data[table][key]))
                applied.append(f"{table}.{key}")
    if "assist" in data:
        cfg.ASSIST = cfg.parse_assist(",".join(str(a) for a in data["assist"]) or "none")
        applied.append("assist")
    if "refs" in data:
        cfg.REFS = [str(r) for r in data["refs"]]
        applied.append("refs")
    cfg.MODE = profile.mode
    cfg.PROFILE_NAME = profile.name
    cfg.PROFILE_PROMPT = profile.prompt
    return applied


# ---------- 새 프로필 ----------
TEMPLATE = '''\
# pc-agent 프로필. 필요 없는 줄은 지우거나 # 로 막아 두면 기본값(환경 변수)을 씁니다.
name = "{name}"
mode = "{mode}"                     # desktop = Windows 조작, game = 게임 조작
{window_line}
# input = "directinput"             # 게임은 directinput (game 모드 기본값), 일반 앱은 pyautogui
# assist = ["game"]                 # 보조 도구: uia, wait, game, minecraft (game 모드 기본값: ["game"])
# memory = "memory/{key}.md"        # 지식 메모 (플레이하며 배운 것을 저장)
# refs = ["refs/{key}/조작법.md"]    # 참고 자료 (읽기 전용)
# max_steps = 80
# model = "claude-sonnet-5"

# Claude에게 줄 이 게임/작업만의 안내 (조작법, 규칙, 주의할 점)
prompt = """
-
"""

# [camera]                          # game 도구의 시점 회전 (1인칭 게임)
# fov = 70                          # 세로 시야각(도)
# counts_per_deg = 6.667            # 시점 1도당 마우스 이동량

# [click]                           # 클릭이 씹히면 늘린다 (초)
# settle = 0.05
# hold = 0.05
'''


def new_profile(key: str, folder: str | Path, mode: str = "game", window: str = "") -> Path:
    if mode not in MODES:
        raise ValueError(f"mode는 {' 또는 '.join(MODES)}여야 합니다")
    if not key or any(c in key for c in '\\/:*?"<>| .'):
        raise ValueError(f"프로필 이름에 쓸 수 없는 문자가 있습니다: {key!r}")
    path = Path(folder) / f"{key}.toml"
    if path.exists():
        raise FileExistsError(f"이미 있는 프로필입니다: {path}")
    window_line = (f'window = "{window}"' if window else f'# window = "{key}"') + \
        "                   # 이 문자열이 제목에 들어간 창만 캡처·조작"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.format(name=key, key=key, mode=mode, window_line=window_line), encoding="utf-8")
    load(path)  # 템플릿이 올바른지 확인
    return path


# ---------- 시작 메뉴 ----------
def pick(folder: str | Path, current: str = "", input_fn=input, print_fn=print) -> Profile | None:
    """프로필 하나를 번호로 고른다. Enter는 current(파일 이름) 유지, 0은 프로필 없이 (환경 변수만)."""
    profiles = list_profiles(folder)
    if not profiles:
        return None
    print_fn(f"\n=== 프로필 ({folder}/) — 무엇을 조작할지 ===")
    for i, p in enumerate(profiles, 1):
        mark = " (현재)" if p.key == current else ""
        print_fn(f"  {i}. {p.name} [{MODES[p.mode]}]{mark}")
    keep = next((p for p in profiles if p.key == current), None)
    print_fn("  0. 프로필 없이 (환경 변수 설정)   |   Enter → " + (f"{keep.name}" if keep else "프로필 없이"))
    while True:
        ans = input_fn("프로필 선택: ").strip()
        if not ans:
            return keep
        if ans == "0":
            return None
        if ans.isdigit() and 1 <= int(ans) <= len(profiles):
            return profiles[int(ans) - 1]
        match = next((p for p in profiles if p.key.lower() == ans.lower()), None)
        if match:
            return match
        print_fn(f"  다시 입력하세요: 1~{len(profiles)} 또는 프로필 파일 이름")
