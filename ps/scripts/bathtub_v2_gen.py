# bathtub_v2_gen.py — 욕조 v2 펌웨어 소스의 클럭별 상수 치환 (build_bathtub_v2.py · ps/sim/build_bt2_sim.sh 가 같이 쓴다)
#
# 실행:  python3 ps/scripts/bathtub_v2_gen.py <mhz 25|75> <out.c>
#
# bathtub_v2.c 의 상수는 25MHz 값이다. 75MHz 는 S-6 §2 「75MHz 묶음」 — UI 스텝 수 · 천장 문턱 · 이력 범위가 다르고
# 나머지(훑기 N · 천장 N · 벽 N · K · 바깥 상한 64 · 바닥 최소 128)는 스텝 단위라 같다. 45MHz 묶음은 명세에 없어 받지 않는다.
# build_g3_sweep.py 와 같은 방식이다 — 원본은 고치지 않고 치환한 사본을 빌드한다. 치환 대상 줄이 원본에서
# 사라지면 시끄럽게 죽는다 (조용한 25MHz 상수 잔류 방지).

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ps" / "src" / "bathtub_v2.c"

PARAMS = {   # mhz: (천장 판정 읽기당 오류, 이력 범위 lo, hi) — S-6 §2
    25: (205, 580, 760),
    75: (410, 600, 750),
}


def gen_source(mhz):
    if mhz not in PARAMS:
        raise SystemExit(f"mhz={mhz}: 25|75 만 허용 (S-6 §2 에 다른 묶음이 없다)")
    o = 1125 // mhz
    ceil, lo, hi = PARAMS[mhz]
    src = SRC.read_text()
    for pat, repl in [
        (r"#define SWEEP_STEPS\s+\d+u[^\n]*", f"#define SWEEP_STEPS     {56 * o}u          /* 56 x {o} = 1 UI ({mhz}MHz) */"),
        (r"#define F_SCLK_HZ\s+\d+u[^\n]*", f"#define F_SCLK_HZ       {mhz * 1_000_000}u"),
        (r"#define CEIL_ERR\s+\d+u[^\n]*", f"#define CEIL_ERR        {ceil}u           /* S-6 §2 ({mhz}MHz) */"),
        (r"#define RANGE_LO\s+\d+u[^\n]*", f"#define RANGE_LO        {lo}u"),
        (r"#define RANGE_HI\s+\d+u[^\n]*", f"#define RANGE_HI        {hi}u"),
    ]:
        src, n = re.subn(pat, repl, src)
        if n != 1:
            raise SystemExit(f"bathtub_v2.c 에서 치환 대상 미발견/중복: {pat} (n={n})")
    return src


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: bathtub_v2_gen.py <mhz 25|75> <out.c>")
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(gen_source(int(sys.argv[1])))
