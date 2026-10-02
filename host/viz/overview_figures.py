# overview_figures.py — 보고서 Ⅱ. 개요의 개념도 두 장을 SVG 로 만든다 (수치 그림이 아니라 설명도).
#
# 사용: uv run python host/viz/overview_figures.py            → build/plots/overview_fig_*.svg
# 승격: 사람이 docs/results/plots/ 로 복사한다 (CONTRIBUTING — 생산 스크립트는 docs 에 직접 쓰지 않는다)
#
#   overview_fig_fresh_reference.svg  §2 문제 정의 — 쓰던 칩 안의 신품 섹터가 기준이 된다 (섹터 지도 + 역산 흐름 4단)
#   overview_fig_system_block.svg     §3 시스템 원리 — PL 위상 스윕 · PS 마모 엔진 · 호스트 · 열화 환경
#
# 글꼴은 SVG 에 박지 않는다 — 워드/브라우저가 가진 한글 글꼴로 그린다. 확인 렌더는 headless chromium 으로.

from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "build" / "plots"
FONT = "Pretendard, Noto Sans KR, Malgun Gothic, Apple SD Gothic Neo, sans-serif"
RED, RED_D = "#b23a3a", "#7a1f1f"
ORG, ORG_D = "#e9c6a0", "#b98a55"
BLU, BLU_D = "#d7e8f7", "#7fa6cc"
GRN_D = "#4f8a4f"
ARROW = '<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#444"/></marker></defs>'


class Svg:
    def __init__(self, w, h, font_size=14):
        self.w, self.h = w, h
        self.s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}" font-size="{font_size}">',
                  f'<rect width="{w}" height="{h}" fill="white"/>', ARROW]

    def text(self, x, y, t, size=None, weight=None, fill="#222"):
        a = f' font-size="{size}"' if size else ""
        b = f' font-weight="{weight}"' if weight else ""
        self.s.append(f'<text x="{x}" y="{y}"{a}{b} fill="{fill}">{escape(t)}</text>')

    def rect(self, x, y, w, h, fill, stroke, rx=8, sw=1.5):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def box(self, x, y, w, h, title, lines, fill="#f6f6f6", stroke="#444", size=13):
        self.rect(x, y, w, h, fill, stroke)
        self.text(x + 12, y + 23, title, weight=700)
        for j, ln in enumerate(lines):
            self.text(x + 12, y + 44 + j * 19, ln, size=size, fill="#333")

    def arrow(self, x1, y1, x2, y2, color="#444", sw=2):
        self.s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" marker-end="url(#ah)"/>')

    def path(self, d, color="#444", sw=2):
        self.s.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" marker-end="url(#ah)"/>')

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text("\n".join(self.s + ["</svg>"]), encoding="utf-8")
        return OUT / name


def fig_fresh_reference():
    # 글자 폭은 한글 1자 = 1em 으로 잡고 상자 안폭의 85% 안에 들게 줄을 끊는다 (맑은 고딕 등 넓은 글꼴 대비)
    g = Svg(1100, 560, 15)
    gx, gy, cell, gap, cols = 50, 92, 22, 3, 16
    g.text(gx, 50, "진단할 칩 (W25Q64, 섹터 128개)", size=19, weight=700)
    g.text(gx, 72, "마모는 칩 전체가 아니라 지운 섹터에만 쌓인다", fill="#555", size=14)
    for i in range(128):
        r, c = divmod(i, cols)
        x, y = gx + c * (cell + gap), gy + r * (cell + gap)
        fill, stroke = (RED, RED_D) if i <= 6 else (ORG, ORG_D) if i <= 31 else (BLU, BLU_D)
        g.rect(x, y, cell, cell, fill, stroke, rx=3, sw=1)
    grid_right = gx + cols * (cell + gap) - gap
    ly = gy + 8 * (cell + gap) + 18
    for k, (col, txt) in enumerate([
            (RED, "섹터 0-6: 반복 소거 영역 → 닳은 값 e"),
            (ORG, "섹터 7-31: 같은 128KB, 소거 교란 → 제외"),
            (BLU, "섹터 32-127: 거의 안 지움 → 신품값 e₀ · 부류")]):
        y = ly + k * 24
        g.rect(gx, y - 13, 16, 16, col, "#666", rx=3, sw=1)
        g.text(gx + 24, y, txt, size=14)
    bx, bw = 540, 520
    g.box(bx, 40, bw, 84, "① 신품값과 부류 — 섹터 32-127 을 한 번 지운다",
          ["소거 시간 중앙값 = 이 칩의 신품값 e₀", "e₀ 가 40ms 미만이면 빠른 무리, 아니면 느린 무리"], fill="#eef4fb", stroke=BLU_D)
    g.box(bx, 146, bw, 64, "② 닳은 값 — 섹터 0-6 을 한 번 지운다",
          ["소거 시간 7개 e → 배율 e / e₀"], fill="#fbeeee", stroke=RED)
    g.box(bx, 232, bw, 142, "③ 이력을 아는 칩들의 곡선과 확률적으로 비교",
          ["같은 무리의 교정 칩 × 섹터 곡선이 구성원",
           "구간마다 '이 값이 나올 확률'을 매겨 정규화",
           "칩마다 다른 노화 속도는 배율 r ∈ [½, 2] 로 적분"], fill="#f3f3f3")
    g.box(bx, 396, bw, 84, "④ 답 — 누적 P/E 횟수 x 의 범위",
          ["가장 그럴듯한 구간(MAP) · 68% · 95% 구간", "점이 아니라 범위로 낸다 (수치는 Ⅳ)"], fill="#eef7ee", stroke=GRN_D)
    mid = bx + bw // 2
    g.arrow(mid, 124, mid, 146); g.arrow(mid, 210, mid, 232); g.arrow(mid, 374, mid, 396)
    g.arrow(grid_right + 6, gy + 4 * (cell + gap) + cell // 2, bx - 6, 82, color=BLU_D)
    x6 = gx + 6 * (cell + gap) + cell // 2
    g.path(f"M {x6} {gy - 2} L {x6} {gy - 12} L {grid_right + 30} {gy - 12} C {bx - 40} {gy - 12}, {bx - 40} 178, {bx - 6} 178", color=RED)
    g.text(gx, 530, "실측 근거: 섹터 0-6 을 10만 회 지운 세 칩에서 섹터 32-127 의 소거 시간은 신품 대비 1.00 (Ⅳ 참조)", size=13, fill="#666")
    return g.save("overview_fig_fresh_reference.svg")


def fig_system_block():
    g = Svg(1100, 520, 14)
    g.rect(40, 40, 600, 420, "#fafafa", "#333", rx=12, sw=2)
    g.text(56, 68, "Zybo Z7-20 (Zynq-7020) — 한 보드, 두 경로", size=18, weight=700)
    g.box(60, 90, 285, 232, "PL  측정 경로 — 위상 스윕",
          ["MMCM 위상 이동 15.873ps/스텝", "샘플 클럭 위상만 민다", "(SCLK·명령은 고정)",
           "SPI 읽기 → PRBS15 비교", "→ 오류 카운터 → 욕조 곡선", "→ 유효 윈도우 폭(ps)"], fill="#eef4fb", stroke=BLU_D, size=12)
    g.box(355, 90, 265, 232, "PS  마모 경로 — P/E 엔진",
          ["섹터 0-6 프로그램·소거 반복", "소거 시간 = 명령 끝 → Busy 해제", "µs 타이머, 매 사이클 섹터별",
           "tally 2곳, 100회당 1바이트", "UART 행마다 체크섬"], fill="#fbeeee", stroke=RED, size=12)
    g.rect(220, 348, 240, 78, "#fff8e1", "#c9a227")
    g.text(232, 372, "W25Q64 SPI NOR (소켓)", weight=700)
    g.text(232, 392, "64비트 UID 로 개체 식별", size=12, fill="#333")
    g.text(232, 410, "같은 핀, 비트스트림만 교체", size=12, fill="#333")
    g.arrow(202, 322, 290, 348); g.arrow(487, 322, 400, 348)
    g.text(56, 446, "체크포인트마다 두 경로를 번갈아: 마모 → prep → 스윕 → 재개", size=12, fill="#555")
    g.box(690, 90, 370, 190, "호스트 PC — Python 실행기",
          ["run_wear.py: 구간·체크포인트·재개", "run_sweep_chip.py: prep → 스윕 → 분석",
           "UID 등록부 · P/E 장부 (추가만)", "네 경로 대조: 카운터·행 수·tally·UID",
           "CSV → 교정 표 → 역산 모델"], size=12)
    g.box(690, 310, 370, 96, "열화 환경 (옵션)",
          ["Arduino PWM + DFR0457 전력 제어", "TMP117 센서, 일정 온도에서 같은 절차"], fill="#eef7ee", stroke=GRN_D, size=12)
    g.arrow(640, 170, 690, 170); g.arrow(690, 200, 640, 200)
    g.text(650, 162, "UART", size=11, fill="#333")
    g.text(650, 216, "JTAG", size=11, fill="#333")
    g.text(690, 486, "측정 결과·수치는 Ⅳ 참조", size=13, fill="#666")
    return g.save("overview_fig_system_block.svg")


if __name__ == "__main__":
    for p in (fig_fresh_reference(), fig_system_block()):
        print(p)
