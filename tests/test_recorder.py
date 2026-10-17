"""실행 기록: 스크린샷을 뒤에서 저장해도 close() 뒤에는 모두 파일로 남는다."""
import json

from PIL import Image

from logs.recorder import Recorder


def test_images_saved_in_background(tmp_path):
    rec = Recorder(str(tmp_path), "목표", name="r")
    names = [rec.image(Image.new("RGB", (64, 32), (i, 0, 0)), "shot") for i in range(5)]
    rec.event("done", ok=True)
    rec.close()
    for n in names:
        assert (rec.dir / n).exists()
    assert Image.open(rec.dir / names[3]).getpixel((0, 0)) == (3, 0, 0)
    kinds = [json.loads(line)["kind"] for line in (rec.dir / "actions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds == ["start", "done"]
