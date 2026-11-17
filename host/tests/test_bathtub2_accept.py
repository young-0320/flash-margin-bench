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
