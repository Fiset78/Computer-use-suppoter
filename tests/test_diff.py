from PIL import Image, ImageDraw

from perception.diff import change_ratio, is_changed, wait_for_change


def blank(color=(255, 255, 255), size=(640, 360)):
    return Image.new("RGB", size, color)


def with_box(box=(100, 100, 300, 200)):
    img = blank()
    ImageDraw.Draw(img).rectangle(box, fill=(0, 0, 0))
    return img


def test_identical_images_unchanged():
    assert change_ratio(blank(), blank()) == 0
    assert not is_changed(blank(), blank())


def test_caret_sized_change_ignored():
    img = blank()
    ImageDraw.Draw(img).line((50, 50, 50, 60), fill=(0, 0, 0))  # 깜빡이는 커서 정도
    assert not is_changed(blank(), img)


def test_dialog_sized_change_detected():
    assert is_changed(blank(), with_box())


def test_size_mismatch_counts_as_changed():
    assert change_ratio(blank(), blank(size=(100, 100))) == 1.0


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def run_frames(frames, baseline, timeout=5.0):
    clock = FakeClock()
    it = iter(frames)
    last = [None]

    def grab():
        last[0] = next(it, last[0])
        return last[0]

    return wait_for_change(grab, baseline, timeout, settle=0.6, poll=0.2, clock=clock, sleep=clock.sleep)


def test_wait_detects_change_then_settles():
    frames = [blank(), blank(), with_box()]  # 0.4초에 바뀌고 그대로 유지
    r = run_frames(frames, baseline=blank())
    assert r.changed and r.settled
    assert r.changed_after == 0.4
    assert r.elapsed < 2.0


def test_wait_times_out_without_change():
    r = run_frames([blank()], baseline=blank(), timeout=1.0)
    assert not r.changed
    assert r.elapsed >= 1.0
    assert "변화가 없었습니다" in r.describe()


def test_wait_already_changed_returns_after_settle():
    r = run_frames([with_box()], baseline=blank())
    assert r.changed and r.changed_after == 0.0
    assert r.elapsed < 1.5


def test_wait_keeps_changing_until_timeout():
    frames = [with_box((i * 20, 0, i * 20 + 200, 200)) for i in range(40)]
    r = run_frames(frames, baseline=blank(), timeout=2.0)
    assert r.changed and not r.settled
    assert "계속 바뀌는 중" in r.describe()
