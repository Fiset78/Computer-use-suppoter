"""실행 기록.

runs/<시각>/ 폴더에 단계별 스크린샷(PNG)과 행동 로그(actions.jsonl)를 남긴다.
실패 원인 분석과, 나중에 보조 기능을 붙였을 때 전후 비교에 쓴다.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image


class Recorder:
    def __init__(self, base_dir: str, goal: str, name: str | None = None):
        # name을 주지 않으면 시각으로 폴더 이름을 정한다 (벤치마크는 과제별 이름을 넘김)
        self.dir = Path(base_dir) / (name or time.strftime("%Y%m%d-%H%M%S"))
        self.dir.mkdir(parents=True, exist_ok=True)
        self._log = open(self.dir / "actions.jsonl", "a", encoding="utf-8")
        self._img_count = 0
        # 기록용 PNG 저장(장당 약 0.1초)은 에이전트를 기다리게 하지 않도록 뒤에서 한다
        self._saver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recorder")
        self.event("start", goal=goal)

    def event(self, kind: str, **data) -> None:
        rec = {"t": round(time.time(), 3), "kind": kind, **data}
        self._log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._log.flush()

    def image(self, img: Image.Image, label: str) -> str:
        self._img_count += 1
        name = f"{self._img_count:04d}_{label}.png"
        self._saver.submit(img.copy().save, self.dir / name)
        return name

    def close(self) -> None:
        self._saver.shutdown(wait=True)  # 남은 스크린샷을 다 저장한 뒤 닫는다
        self._log.close()
