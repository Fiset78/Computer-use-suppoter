"""화면 캡처와 좌표 변환.

Claude는 '우리가 보낸 스크린샷'의 픽셀 좌표로 행동을 지시한다.
실제 화면이 더 크면 스크린샷을 축소해서 보내고, 돌아온 좌표는 다시 확대해서 적용한다.
"""
import base64
import ctypes
import io

import mss
from PIL import Image


def enable_dpi_awareness() -> None:
    """Windows 디스플레이 배율(125%, 150% 등) 때문에 클릭이 어긋나는 문제를 막는다.
    pyautogui 등 GUI 관련 모듈을 import 하기 전에 가장 먼저 호출해야 한다."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _to_pil(raw) -> Image.Image:
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


class Screen:
    def __init__(self, max_long_edge: int = 1280, monitor_index: int = 1):
        self._sct = mss.mss()
        self.monitor = self._sct.monitors[monitor_index]
        self.left = self.monitor["left"]
        self.top = self.monitor["top"]
        self.width = self.monitor["width"]
        self.height = self.monitor["height"]

        # 긴 변 기준 축소 비율 (확대는 하지 않음)
        self.scale = min(1.0, max_long_edge / max(self.width, self.height))
        self.shot_w = round(self.width * self.scale)
        self.shot_h = round(self.height * self.scale)

    # ---------- 좌표 변환 ----------
    def in_bounds(self, x: float, y: float) -> bool:
        return 0 <= x < self.shot_w and 0 <= y < self.shot_h

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """스크린샷 좌표 -> 실제 화면(가상 데스크톱) 좌표"""
        sx = min(self.width - 1, max(0, round(x / self.scale)))
        sy = min(self.height - 1, max(0, round(y / self.scale)))
        return self.left + sx, self.top + sy

    def to_shot(self, sx: int, sy: int) -> tuple[int, int]:
        """실제 화면 좌표 -> 스크린샷 좌표"""
        return round((sx - self.left) * self.scale), round((sy - self.top) * self.scale)

    # ---------- 캡처 ----------
    def capture(self) -> Image.Image:
        img = _to_pil(self._sct.grab(self.monitor))
        if self.scale < 1.0:
            img = img.resize((self.shot_w, self.shot_h), Image.LANCZOS)
        return img

    def capture_region(self, region: list[int]) -> Image.Image:
        """zoom 도구용: 스크린샷 좌표 영역을 원본 해상도로 잘라서,
        비율을 유지한 채 스크린샷 크기 안에 맞춰 반환한다."""
        x0, y0, x1, y1 = region
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"잘못된 zoom 영역: {region}")
        sx0, sy0 = self.to_screen(x0, y0)
        sx1, sy1 = self.to_screen(x1, y1)
        box = {"left": sx0, "top": sy0, "width": max(1, sx1 - sx0), "height": max(1, sy1 - sy0)}
        img = _to_pil(self._sct.grab(box))
        ratio = min(self.shot_w / img.width, self.shot_h / img.height)
        new_size = (max(1, round(img.width * ratio)), max(1, round(img.height * ratio)))
        return img.resize(new_size, Image.LANCZOS)


def to_image_block(img: Image.Image) -> dict:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(buf.getvalue()).decode(),
        },
    }
