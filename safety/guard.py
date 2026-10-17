"""안전장치.

1. 긴급 정지: 마우스를 화면 왼쪽 위 모서리로 급히 옮기면 pyautogui가 FailSafeException을
   일으켜 즉시 멈춘다. 터미널에서 Ctrl+C로도 멈출 수 있다.
2. 위험 행동 확인: 되돌리기 어려운 키 입력/텍스트는 실행 전에 사용자에게 y/n 확인을 받는다.
"""
import re

# 실행 전 확인이 필요한 키 조합 (pyautogui 키 이름 기준, 정렬된 튜플)
DANGEROUS_COMBOS = {
    ("delete", "shift"),        # 휴지통 거치지 않고 영구 삭제
    ("alt", "f4"),              # 창/프로그램 종료
    ("alt", "ctrl", "delete"),
}

# 입력하려는 텍스트에 이런 패턴이 있으면 확인 (셸 명령 등)
DANGEROUS_TEXT = re.compile(
    r"(\brm\s+-rf\b|\bdel\s+/[sq]\b|\bformat\s+[a-z]:|\bshutdown\b|Remove-Item.+-Recurse)",
    re.IGNORECASE,
)


class Guard:
    def __init__(self, confirm: bool = True):
        self.confirm = confirm

    def _ask(self, what: str) -> bool:
        if not self.confirm:
            return True
        ans = input(f"\n⚠️  위험할 수 있는 행동: {what}\n   실행할까요? [y/N] ").strip().lower()
        return ans == "y"

    def check_key(self, combo: list[str]) -> None:
        if tuple(sorted(combo)) in DANGEROUS_COMBOS and not self._ask(f"키 입력 {'+'.join(combo)}"):
            raise PermissionError("사용자가 이 키 입력을 거부했습니다. 다른 방법을 찾으세요.")

    def check_text(self, text: str) -> None:
        if DANGEROUS_TEXT.search(text) and not self._ask(f"텍스트 입력 {text!r}"):
            raise PermissionError("사용자가 이 텍스트 입력을 거부했습니다. 다른 방법을 찾으세요.")
