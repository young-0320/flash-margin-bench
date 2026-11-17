"""수정안 #4 A4 · A5 판정(host/analysis/bathtub2_accept.py) 회귀 — chip02 2026-11-17 실데이터와 그 변조 사본.

실데이터(data/ 는 git 밖)가 없는 PC 에서는 skip 한다. 변조는 리뷰(2026-11-17 · 18)가 판정을 뒤집어 본 것 중
고친 뒤에도 지켜야 할 것: 천장 한 읽기 −1 · e1 전부 0 · 극성 반전(e1 ↔ e − e1) · 원형 이동."""

import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import bathtub2_accept as acc  # noqa: E402

D = REPO / "data" / "bathtub2" / "chip02"
V1 = REPO / "data" / "sweep_chip02_D1642C74E7134527_20261117T142414Z.csv"
V2 = D / "bathtub2_chip02_D1642C74E7134527_20261117T142542Z.csv"
V75 = D / "bathtub2_chip02_D1642C74E7134527_20261117T143250Z.csv"
need = pytest.mark.skipif(not (V1.exists() and V2.exists() and V75.exists()), reason="chip02 2026-11-17 실데이터가 없다")


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)


def mutate(src, tmp, reads_fn=None, main_fn=None):
    """src 메인 · _reads 를 tmp 로 복사하며 행을 바꾼다. reads_fn(list[str]) → list[str], main_fn(dict) → dict."""
    dst = tmp / src.name
    with open(src, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if main_fn:
        rows = [main_fn(r) for r in rows]
    with open(dst, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = Path(str(src)[:-4] + "_reads.csv").read_text().splitlines()
    body = [ln.split(",") for ln in lines[1:]]
    if reads_fn:
        body = reads_fn(body)
    Path(str(dst)[:-4] + "_reads.csv").write_text("\n".join([lines[0]] + [",".join(f) for f in body]) + "\n")
    return dst


@need
def test_real_runs_pass():
    assert acc.a4(V1, V2)
    assert acc.a5(V75) == "통과"


@need
def test_ceiling_minus_one_fails(tmp_path):
    def reads(b):
        for f in b:
            if f[1] == "c" and f[0] == "614" and f[2] == "5":
                f[3] = str(int(f[3]) - 1)
                f[6] = str(int(f[6]) - 1)               # e_c2 — err_count 는 정렬 min
                break
        return b

    def main(r):
        if r["pass"] == "ceil" and r["phase_step"] == "614":
            r["bit_errors"] = str(int(r["bit_errors"]) - 1)
        return r
    assert not acc.a4(V1, mutate(V2, tmp_path, reads, main))


@pytest.mark.parametrize("kind", ["e1_zero", "polarity"])
@need
def test_e1_path_faults_fail_a4(tmp_path, kind):
    def reads(b):
        for f in b:
            for k in range(3):
                e, e1 = int(f[4 + k]), int(f[7 + k])
                f[7 + k] = "0" if kind == "e1_zero" else str(e - e1)
        return b
    assert not acc.a4(V1, mutate(V2, tmp_path, reads))


@need
def test_e1_zero_fails_a5(tmp_path):
    def reads(b):
        for f in b:
            f[7] = f[8] = f[9] = "0"
        return b
    assert not acc.a5(mutate(V75, tmp_path, reads)).startswith("통과")


@need
def test_circular_shift_passes(tmp_path):
    k = 1905                                            # 덩어리가 2520 → 0 을 걸치게 민다

    def sh(s):
        return str((int(s) + k) % 2520)

    def reads(b):
        for f in b:
            f[0] = sh(f[0])
        return b

    def main(r):
        r["phase_step"] = sh(r["phase_step"])
        return r
    (tmp_path / "v1").mkdir()
    (tmp_path / "v2").mkdir()
    assert acc.a4(mutate(V1, tmp_path / "v1", reads, main), mutate(V2, tmp_path / "v2", reads, main))


@need
def test_missing_ceil_row_fails(tmp_path):
    """천장 범위 안 칸의 ceil 행이 아예 없으면(훑기 오류가 문턱 미만이라 wall 로 간 칸) 구멍 — 불통과."""
    def main(r):
        if r["pass"] == "ceil" and r["phase_step"] == "614":
            r["pass"] = "wall"
        return r

    def reads(b):
        for f in b:
            if f[1] == "c" and f[0] == "614":
                f[1] = "w"
        return b
    assert not acc.a4(V1, mutate(V2, tmp_path, reads, main))


@need
def test_mixed_direction_fails(tmp_path):
    """천장 e1 을 세 정렬 모두 +1 — 극성 항등식은 공통 오프셋에 불변이라 「4 방향」 만 잡는다 (2026-11-18 리뷰 F1)."""
    def reads(b):
        for f in b:
            if f[1] == "c" and 612 <= int(f[0]) <= 617:
                for k in range(3):
                    f[7 + k] = str(int(f[7 + k]) + 1)
        return b
    assert not acc.a4(V1, mutate(V2, tmp_path, reads))


# ── 합성 75MHz 런 (실데이터 없이 돈다) ────────────────────────────────────────
# flash_rx 창을 손으로 옮긴 모형(2026-11-18 리뷰 rev2/emu.py): 캡처 샘플 m_j 는 전이 (L[j-1] → L[j]) 를 걸친다.
#   L[-1] = 데이터 앞 선 상태, L[0..2047] = 쪽 비트, L[2048] = 1(다음 쪽 첫 비트)
#   정렬 0: m_j 대 b[j+1] (j = 0..2046) · 정렬 1: m_j 대 b[j] · 정렬 2: m_(j+1) 대 b[j]
# 칩 모형은 chip02 75MHz 실측에서 여섯 값이 전부 맞은 규칙 — L 선반 「1 0 1」 상승만 먼저, 천장 상승 전부 먼저,
# R 선반 「1 1 0」 하강만 아직, 읽기 0 의 머리 하강 이력은 R 쪽에서 0
def six(page, early, pre, pre2):
    import numpy as np
    from bathtub2_analysis import prbs_page
    b = prbs_page(page).astype(int)
    L = np.concatenate(([pre2, pre], b, [1]))
    m = np.empty(2049, int)
    for j in range(2049):
        a, p, c = L[j], L[j + 1], L[j + 2]
        m[j] = c if (p == c or early((a, p, c))) else p
    e, e1 = [], []
    for got, want in ((m[0:2047], b[1:2048]), (m[0:2048], b), (m[1:2049], b)):
        d = got != want
        e.append(int(d.sum()))
        e1.append(int((d & (want == 1)).sum()))
    return e, e1


EARLY = {"FL": lambda h: False, "L": lambda h: h == (1, 0, 1), "C": lambda h: h[2] == 1,
         "R": lambda h: h != (1, 1, 0), "FR": lambda h: True}
MAIN_COLS = ("phase_step,phase_ps,n_reads,b_bits,bit_errors,reads_with_error,bit_err_sq_sum,f_sclk_hz,dphi_ps,pass,"
             "base_sector,mode,flags,target,generated_at,git_rev,uid,reseat,repeat_idx,batch_id,reason").split(",")


def synth75(tmp, base, e1_dead=False):
    def region(s):
        return "L" if 600 <= s <= 609 else "C" if 610 <= s <= 622 else "R" if 623 <= s <= 660 else \
            "FL" if 420 <= s < 600 else "FR"
    cache, mrows, rrows = {}, [], []

    def add(pass_, s, n):
        reg = region(s)
        tot = sq = we = 0
        for k in range(n):
            i = k % 112
            if (reg, i) not in cache:
                pre = (0, 0) if (i == 0 and reg in ("R", "FR")) else (1, 1)
                cache[(reg, i)] = six(base * 16 + i, EARLY[reg], *pre)
            e, e1 = cache[(reg, i)]
            if e1_dead:
                e1 = [0, 0, 0]
            m = min(e)
            tot, sq, we = tot + m, sq + m * m, we + (m > 0)
            rrows.append(f"{s},{pass_[0]},{i},{m},{e[0]},{e[1]},{e[2]},{e1[0]},{e1[1]},{e1[2]}")
        mrows.append(dict(zip(MAIN_COLS, [s, f"{s * 15.873016:.3f}", n, 2048, tot, we, sq, 75000000, 15.873016, pass_,
                                          base, "std", "", "chip02", "2026-11-18T00:00:00+00:00", "x",
                                          "D1642C74E7134527", 0, 1, "synth", "complete"])))
    for s in range(840):
        add("scan", s, 1)
    for s in range(610, 623):
        add("ceil", s, 112)
    for s in list(range(595, 610)) + list(range(623, 666)):
        add("wall", s, 224)
    for s in range(840):
        add("rescan", s, 1)
    p = tmp / f"bathtub2_chip02_D1642C74E7134527_synth{base}.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MAIN_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(mrows)
    Path(str(p)[:-4] + "_reads.csv").write_text(
        "phase_step,pass,read_idx,err_count,e_c0,e_c1,e_c2,e1_c0,e1_c1,e1_c2\n" + "\n".join(rrows) + "\n")
    return p


@pytest.mark.parametrize("base", [0, 48, 121])
def test_synth_a5_passes(tmp_path, base):
    """base 48 은 쪽이 「0 0」 으로 끝나 쪽 끝 상승이 「0 0 1」 이다 — ③ 왼쪽 옛 식(상승+쪽 끝 − 부류)은 여기서 떨어졌다(리뷰 H1)."""
    assert acc.a5(synth75(tmp_path, base)) == "통과"


def test_synth_a5_e1_dead_fails(tmp_path):
    assert not acc.a5(synth75(tmp_path, 48, e1_dead=True)).startswith("통과")
