"""1인칭 게임의 시점 회전 계산 (게임 보조 도구용). GUI 의존성이 없는 순수 모듈이다.

- 각도 단위는 도(degree). yaw 양수 = 오른쪽, pitch 양수 = 위쪽.
- 마우스 상대 이동량(count)은 x 양수 = 오른쪽, y 양수 = 아래쪽 (Windows 기준).
- 스크린샷 좌표 → 각도 변환은 핀홀 카메라 모델을 쓴다. 게임 화면이 캡처 화면 전체를 채우고,
  조준점이 화면 정중앙에 있다고 가정한다 (전체화면 또는 테두리 없는 창 모드).
"""
import math


def focal_px(shot_h: int, vfov_deg: float) -> float:
    """세로 시야각(FOV)으로 스크린샷 픽셀 단위 초점 거리를 구한다. 마인크래프트의 FOV 설정은 세로 기준이다."""
    if not 1 <= vfov_deg <= 179:
        raise ValueError(f"잘못된 FOV: {vfov_deg}")
    return (shot_h / 2) / math.tan(math.radians(vfov_deg) / 2)


def shot_to_angles(x: float, y: float, shot_w: int, shot_h: int, vfov_deg: float) -> tuple[float, float]:
    """스크린샷의 한 점을 화면 중앙(조준점)으로 가져오려면 돌려야 할 (yaw, pitch).

    yaw로 먼저 돌린 뒤 pitch를 맞춘다고 보고 pitch는 sqrt(f² + dx²) 기준으로 계산한다.
    시점이 이미 많이 위/아래를 보고 있으면 오차가 생기므로, 정밀 조준은 한 번 더 보정하면 된다.
    """
    f = focal_px(shot_h, vfov_deg)
    dx = x - shot_w / 2
    dy = shot_h / 2 - y  # 위쪽이 양수
    yaw = math.degrees(math.atan2(dx, f))
    pitch = math.degrees(math.atan2(dy, math.hypot(f, dx)))
    return yaw, pitch


def angles_to_counts(yaw: float, pitch: float, counts_per_deg: float) -> tuple[int, int]:
    """각도 → 마우스 상대 이동량. pitch가 위(양수)면 마우스는 위(음수)로 움직인다."""
    if counts_per_deg <= 0:
        raise ValueError(f"잘못된 counts_per_deg: {counts_per_deg}")
    return round(yaw * counts_per_deg), round(-pitch * counts_per_deg)


def split_counts(total: int, parts: int) -> list[int]:
    """정수 total을 parts개로 고르게 나눈다. 합은 정확히 total이다 (반올림 오차가 쌓이지 않음)."""
    if parts < 1:
        raise ValueError("parts는 1 이상이어야 합니다")
    return [round(total * (i + 1) / parts) - round(total * i / parts) for i in range(parts)]


def chunk_moves(dx: int, dy: int, max_step: int = 120) -> list[tuple[int, int]]:
    """큰 이동을 한 번에 max_step count 이하의 조각으로 나눈다 (한 번에 크게 움직이면 잘리는 게임이 있음)."""
    n = max(1, math.ceil(max(abs(dx), abs(dy)) / max_step))
    return list(zip(split_counts(dx, n), split_counts(dy, n)))
