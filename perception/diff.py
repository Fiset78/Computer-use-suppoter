"""화면 변화 감지. GUI 의존성이 없는 순수 모듈이다 (PIL만 사용).

wait_for_change 도구가 '바뀔 때까지 기다렸다가, 멈추면 반환'하는 데 쓴다.
"""
import time
from dataclasses import dataclass
from typing import Callable

from PIL import Image, ImageChops

# 축소 후 픽셀 밝기 차이가 이 값 이상이면 '바뀐 픽셀'로 본다 (압축 잡음, 안티에일리어싱 무시)
PIXEL_THRESHOLD = 24
# 바뀐 픽셀 비율이 이 값을 넘으면 화면이 바뀐 것으로 본다 (깜빡이는 커서 정도는 무시)
CHANGE_RATIO = 0.001


def change_ratio(a: Image.Image, b: Image.Image, width: int = 320) -> float:
    """두 이미지에서 바뀐 픽셀의 비율 (0~1). 크기가 다르면 1.0."""
    if a.size != b.size:
        return 1.0
    w = max(1, min(width, a.width))
    h = max(1, round(a.height * w / a.width))
    ga = a.convert("L").resize((w, h), Image.BILINEAR)
    gb = b.convert("L").resize((w, h), Image.BILINEAR)
    hist = ImageChops.difference(ga, gb).histogram()
    return sum(hist[PIXEL_THRESHOLD:]) / (w * h)


def is_changed(a: Image.Image, b: Image.Image) -> bool:
    return change_ratio(a, b) > CHANGE_RATIO


@dataclass
class WaitResult:
    changed: bool                 # 기준 화면과 달라졌는지
    settled: bool                 # 마지막에 화면이 멈춰 있었는지
    changed_after: float | None   # 처음 변화를 감지한 시각(초)
    elapsed: float
    image: Image.Image            # 마지막으로 캡처한 화면

    def describe(self) -> str:
        if not self.changed:
            return f"{self.elapsed:.1f}초 동안 화면 변화가 없었습니다."
        if self.settled:
            return (f"{self.changed_after:.1f}초 후 화면이 바뀌었고, "
                    f"{self.elapsed:.1f}초에 안정되었습니다.")
        return (f"{self.changed_after:.1f}초 후 화면이 바뀌었지만, "
                f"제한 시간({self.elapsed:.1f}초)까지 계속 바뀌는 중입니다.")


def wait_for_change(grab: Callable[[], Image.Image], baseline: Image.Image, timeout: float,
                    settle: float = 0.6, poll: float = 0.2,
                    clock: Callable[[], float] = time.perf_counter,
                    sleep: Callable[[float], None] = time.sleep) -> WaitResult:
    """baseline과 달라질 때까지 기다린 뒤, settle초 동안 더 바뀌지 않으면 반환한다.

    baseline은 보통 Claude에게 마지막으로 보낸 스크린샷이다. 그래서 이 도구를 부르기 전에
    이미 화면이 바뀌었다면 바로 '변화'로 판정하고, 안정될 때까지만 기다린다.
    """
    start = clock()
    changed_after = None
    stable_since = None
    prev = None
    while True:
        img = grab()
        now = clock() - start
        if changed_after is None and is_changed(baseline, img):
            changed_after = now
        if prev is not None and not is_changed(prev, img):
            if stable_since is None:
                stable_since = now
        else:
            stable_since = None
        settled = stable_since is not None and now - stable_since >= settle
        if (changed_after is not None and settled) or now >= timeout:
            return WaitResult(changed_after is not None, settled, changed_after, now, img)
        prev = img
        sleep(poll)


# ---------- 내 PC에서 짧은 간격으로 감시하기 (hold_until) ----------
# 게임 화면은 물·몹·구름 때문에 늘 조금씩 바뀌므로, 판정 기준을 wait_for_change보다 넉넉하게 잡는다
MONITOR_CHANGE = 0.03   # 시작 화면 대비 바뀐 픽셀 비율이 이보다 크면 '크게 바뀜'
MONITOR_STILL = 0.01    # 직전 화면 대비 바뀐 비율이 이보다 작으면 '멈춤'
STILL_SAMPLES = 2       # 멈춤이 이만큼 연속돼야 멈춘 것으로 본다 (걷다 잠깐 끊긴 것과 구분)


@dataclass
class MonitorResult:
    met: bool          # 조건을 만족해서 멈췄는지 (아니면 시간 초과)
    elapsed: float
    samples: int
    ratio: float       # 마지막 판정에 쓴 변화 비율
    image: Image.Image

    def describe(self, until: str) -> str:
        what = "화면이 크게 바뀌어" if until == "change" else "화면이 멈춰"
        if self.met:
            return f"{self.elapsed:.1f}초 만에 {what} 멈췄습니다 (변화 비율 {self.ratio:.3f}, 확인 {self.samples}회)."
        return (f"{self.elapsed:.1f}초 동안 조건이 맞지 않아 시간 초과로 멈췄습니다 "
                f"(마지막 변화 비율 {self.ratio:.3f}, 확인 {self.samples}회).")


def monitor(grab: Callable[[], Image.Image], until: str, max_duration: float, interval: float = 0.5,
            threshold: float | None = None, clock: Callable[[], float] = time.perf_counter,
            sleep: Callable[[float], None] = time.sleep) -> MonitorResult:
    """interval초마다 화면을 찍어 비교한다.
    until="change": 처음 화면과 비교해 threshold(기본 MONITOR_CHANGE)보다 많이 바뀌면 멈춘다.
    until="still":  바로 앞 화면과 비교해 threshold(기본 MONITOR_STILL)보다 덜 바뀐 상태가
                    STILL_SAMPLES번 이어지면 멈춘다 (예: 걷다가 벽에 막힘, 로딩 끝)."""
    if until not in ("change", "still"):
        raise ValueError(f"알 수 없는 조건: {until} (change 또는 still)")
    limit = threshold if threshold is not None else (MONITOR_CHANGE if until == "change" else MONITOR_STILL)
    start = clock()
    first = prev = grab()
    samples, still_run, ratio = 0, 0, 0.0
    while True:
        sleep(interval)
        img = grab()
        samples += 1
        now = clock() - start
        if until == "change":
            ratio = change_ratio(first, img)
            if ratio > limit:
                return MonitorResult(True, now, samples, ratio, img)
        else:
            ratio = change_ratio(prev, img)
            still_run = still_run + 1 if ratio < limit else 0
            if still_run >= STILL_SAMPLES:
                return MonitorResult(True, now, samples, ratio, img)
        if now >= max_duration:
            return MonitorResult(False, now, samples, ratio, img)
        prev = img
