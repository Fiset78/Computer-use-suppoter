"""연속 장면(watch)과 내 PC 감시(hold_until)."""
from PIL import Image

from perception import diff


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def frames(*colors):
    imgs = [Image.new("RGB", (64, 36), (c, c, c)) for c in colors]
    it = iter(imgs)
    last = [imgs[-1]]
    return lambda: next(it, last[0])


def test_monitor_still_stops_when_screen_stops():
    clock = Clock()
    # 걷는 동안 계속 바뀌다가(0→60→120) 벽에 막혀 멈춤(120 유지)
    res = diff.monitor(frames(0, 60, 120, 120, 120, 120), "still", 10, 0.5, clock=clock, sleep=clock.sleep)
    assert res.met and res.elapsed == 2.0 and "멈춰" in res.describe("still")


def test_monitor_change_and_timeout():
    clock = Clock()
    res = diff.monitor(frames(0, 0, 0, 200), "change", 10, 0.5, clock=clock, sleep=clock.sleep)
    assert res.met and res.elapsed == 1.5
    clock2 = Clock()
    res2 = diff.monitor(frames(0), "change", 2, 0.5, clock=clock2, sleep=clock2.sleep)
    assert not res2.met and res2.elapsed == 2.0 and "시간 초과" in res2.describe("change")


def test_executor_watch_and_hold_until(monkeypatch):
    import pytest

    from actions.executor import Executor
    from safety.guard import Guard

    class Screen:
        def __init__(self):
            self.n = 0

        def capture(self):
            self.n += 1
            return Image.new("RGB", (1280, 720), (min(250, self.n * 40),) * 3)

    class Backend:
        def __init__(self):
            self.log = []

        def check_keys(self, keys):
            pass

        def key_down(self, k):
            self.log.append(("down", k))

        def key_up(self, k):
            self.log.append(("up", k))

    monkeypatch.setattr("time.sleep", lambda s: None)
    b = Backend()
    ex = Executor(screen=Screen(), guard=Guard(confirm=False), backend=b, action_delay=0)
    blocks = ex.do_watch({"frames": 3, "interval": 0.5})
    images = [x for x in blocks if x["type"] == "image"]
    assert len(images) == 3 and "3장" in blocks[0]["text"]

    out = ex.do_hold_until({"text": "w", "until": "change", "max_duration": 3})
    assert out.startswith("OK: w 키를 누른 채") and b.log == [("down", "w"), ("up", "w")]

    ex.stop_check = lambda: True   # 감시 중 정지하면 키를 떼고 멈춘다
    b.log.clear()
    from actions.backends import StopRequested
    with pytest.raises(StopRequested):
        ex.do_hold_until({"text": "w", "until": "still", "max_duration": 3})
    assert b.log == [("down", "w"), ("up", "w")]
