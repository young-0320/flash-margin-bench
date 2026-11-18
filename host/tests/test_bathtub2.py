"""욕조 v2 — 펌웨어 호스트 시뮬레이션(ps/sim/build_bt2_sim.sh) · 캡처(bathtub2_capture.py) · 분석기(bathtub2_analysis.py).

같은 ps/src/bathtub_v2.c 를 가짜 core(ps/sim/bt2_core_fake.c) 위에 올려 S-6 §3 ①-⑦ 을 돌린다. 가짜 core 는 위상
스텝마다 상승 · 하강 에지가 셔터보다 먼저 올 확률(p_r · p_f)을 프로파일로 받아 읽기별 여섯 값을 비트 단위로 만든다.
프로파일은 v1 실측 벽(data/sweep_*.csv) 또는 가우시안 에지에서 만든다. 실측 파일이 없으면 그 경우만 skip 한다.
sim 의 stdout 이 UART 대신이고, 그 줄을 그대로 캡처에 흘려 파일을 만들고 분석기로 잰다. gcc 가 없으면 skip.

S-6 §6 시험 2 의 경우 — v1 실측 벽 · UI 끝 → 0 걸침 · 덩어리 둘 · 덩어리 없음 · 짧은 바닥 · 바깥 접촉 붕괴 · 끝 훑기 표류 ·
접촉 불량 산발 오류 · 75MHz 묶음 · 무효 ⑦-⑭ · drift · rescan_multi_block · BASE_SECTOR 되읽기(no_base_sector ·
base_sector_mismatch) · 칩 끝 BASE_SECTOR(2042-2047)에서 천장 START(N = 112) 거부 → cfg_err. 위상은 INC · DEC 가 섞인다
(되돌아가는 걷기 · 끝 훑기 전 되감기) — 펌웨어가 측정마다 PHASE_POS 를 정확 비교하므로 어긋나면 phase_pos_mismatch 로 끝난다.
분석기는 평균 · 폭만이 아니라 스텝마다 꼬리 비율(1e-5 아래)을 주입값과 맞댄다 — 「지금 비트」 = 1 · 2, 쪽 머리 상승 있음(유휴 0) ·
합성 프리앰블.
"""

import csv
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "capture"))
sys.path.insert(0, str(REPO / "host" / "analysis"))
import bathtub2_analysis as an2  # noqa: E402
import bathtub2_capture as cap2  # noqa: E402
import sweep_uart_capture as cap1  # noqa: E402
from bathtub_freq_compare import block  # noqa: E402

DPHI = 1e6 / 63 / 1e3          # ps
V1_25 = REPO / "data" / "sweep_chip01_20260708T164931Z.csv"          # bathtub_p1_figures.py 의 게재 런
V1_75 = REPO / "data" / "sweep_chip03_D1628C10C3433F33_20260926T073237Z.csv"
SMALL_N = "224"                # 벽 N = 112 × 2 — 대부분의 경우는 절차만 본다


@pytest.fixture(scope="module")
def sims():
    if not shutil.which("gcc"):
        pytest.skip("gcc 가 없다 — 호스트 시뮬레이션을 빌드할 수 없다")
    for mhz in (25, 75):
        subprocess.run([str(REPO / "ps" / "sim" / "build_bt2_sim.sh"), str(mhz)], check=True, capture_output=True)
    return {m: REPO / "build" / "sim" / f"bathtub_v2_sim_{m}" for m in (25, 75)}


# ── 프로파일 ──────────────────────────────────────────────────────────────
def write_profile(path, steps, rows):
    """rows = {step: (p_r, p_f, now)} — 없는 스텝은 가짜 core 가 0 0 1 로 둔다."""
    with open(path, "w") as f:
        f.write(f"steps {steps}\n")
        for s, (a, b, now) in sorted(rows.items()):
            f.write(f"{s} {a:.12g} {b:.12g} {now}\n")
    return path


def phi(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def gauss_rows(steps, center, mu_r, s_r, mu_f, s_f, now=1, t0_shift_ps=None):
    """에지별 가우시안 도착 시각(ps, 덩어리 중심 기준) → 스텝별 (p_r, p_f, now).
    x = (스텝 − 중심) × Δφ 를 [−UI/2, UI/2) 로 감는다 — 감는 자리(바닥 한가운데)에서 (p = 1, now) ≡ (p = 0, now) 다.
    t0_shift_ps 를 주면 그 위상부터 정렬 번호가 하나 오른다 (pay CDC 의 t0 이동 — 덩어리 안에 떨어진 경우)."""
    rows = {}
    for s in range(steps):
        x = ((s - center + steps / 2) % steps - steps / 2) * DPHI
        n = now + (1 if t0_shift_ps is not None and x >= t0_shift_ps else 0)
        rows[s] = (phi((x - mu_r) / s_r), phi((x - mu_f) / s_f), n)
    return rows


def v1_rows(path, shift=0):
    """v1 실측 BER → (p_r, p_f). 천장 중점 왼쪽은 상승이 오는 중(p_r = 읽기당 오류 ÷ 천장), 오른쪽은 상승 다 오고
    하강이 오는 중(p_f = 1 − 읽기당 오류 ÷ 천장). 덩어리 오른쪽 바닥은 바닥 한가운데까지 p = 1."""
    with open(path, newline="") as fh:
        rr = list(csv.DictReader(fh))
    steps = len(rr)
    e = np.array([int(r["bit_errors"]) / int(r["n_reads"]) for r in rr])
    first, length = block(np.array([int(r["bit_errors"]) for r in rr]))
    idx = [(first + k) % steps for k in range(length)]
    ceil = e[idx].max()
    top = [k for k in range(length) if e[idx[k]] >= 0.99 * ceil]
    mid = (top[0] + top[-1]) / 2
    rows = {}
    for k in range(length + (steps - length) // 2):
        s = (first + k) % steps
        f = min(1.0, e[s] / ceil)
        rows[(s + shift) % steps] = (f, 0.0, 1) if k <= mid else (1.0, 1.0 - f if k < length else 1.0, 1)
    return steps, rows, (first + shift) % steps, length


def need(p):
    if not p.exists():
        pytest.skip(f"{p.relative_to(REPO)} 가 없다 — data/ 원본이 이 PC 에 없다")


# ── 실행 · 캡처 ───────────────────────────────────────────────────────────
class Lines:
    """시리얼 대역 — 미리 받은 줄을 readline 으로 낸다. 줄이 떨어지면 Ctrl-C 로 본다 (보드가 말을 멈춘 것)."""
    port, baudrate = "sim", 921600

    def __init__(self, lines):
        self.it = iter(lines)

    def readline(self):
        try:
            return next(self.it)
        except StopIteration:
            raise KeyboardInterrupt from None


def run_sim(sim, tmp_path, rows=None, steps=2520, rescan_rows=None, wall_n=SMALL_N, base_sector=0, **env):
    e = dict(os.environ, BT2_WALL_N=str(wall_n), BT2_BASE_SECTOR=str(base_sector),
             **{f"BT2_FAKE_{k.upper()}": str(v) for k, v in env.items()})
    if rows is not None:
        e["BT2_FAKE_PROFILE"] = str(write_profile(tmp_path / "prof.txt", steps, rows))
    if rescan_rows is not None:
        e["BT2_FAKE_RESCAN_PROFILE"] = str(write_profile(tmp_path / "prof_rescan.txt", steps, rescan_rows))
    r = subprocess.run([str(sim)], env=e, capture_output=True, timeout=300, check=True)
    return [ln + b"\n" for ln in r.stdout.split(b"\r\n") if ln]


def end_of(lines):
    return cap2.kv(next(ln.decode() for ln in lines if b"SWEEP END" in ln))


def mains(lines):
    """[(pass, step, n_reads, bit_errors)] — M 줄 순서대로."""
    out = []
    for ln in lines:
        if ln.startswith(b"M,"):
            f = ln.decode().strip()[2:].split(",")
            out.append((f[9], int(f[0]), int(f[2]), int(f[4])))
    return out


def capture(lines, tmp_path, **kw):
    return cap2.capture_bathtub2(Lines(lines), "loopback", None, tmp_path / "out", log=open(os.devnull, "w"), **kw)


def read_csv(p):
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


# ── 펌웨어 절차 (S-6 §3) ──────────────────────────────────────────────────
def test_v1_wall_std_valid(sims, tmp_path):
    """v1 실측 벽 · 벽 N = std(8,064): 훑기 → 천장 한 묶음 → 벽 → 바깥 K 연속 0 → 끝 훑기 → valid."""
    need(V1_25)
    steps, rows, first, length = v1_rows(V1_25)
    lines = run_sim(sims[25], tmp_path, rows, steps, wall_n=8064)
    end = end_of(lines)
    assert (end["valid"], end["reason"], end["mode"]) == ("1", "complete", "std")
    m = mains(lines)
    assert [p for p, *_ in m[:steps]] == ["scan"] * steps and [s for _, s, *_ in m[:steps]] == list(range(steps))
    assert [p for p, *_ in m[-steps:]] == ["rescan"] * steps and [s for _, s, *_ in m[-steps:]] == list(range(steps))
    scan = {s: e for p, s, _, e in m if p == "scan"}
    ceil = [(s, n) for p, s, n, _ in m if p == "ceil"]
    wall = [(s, n, e) for p, s, n, e in m if p == "wall"]
    assert ceil and all(n == 112 and scan[s] >= 205 for s, n in ceil)
    assert all(n == 8064 for _, n, _ in wall)
    blk = {(first + k) % steps for k in range(length)}
    inner = {s for s, *_ in wall if s in blk}
    assert inner | {s for s, _ in ceil} >= {s for s in blk if scan[s] > 0}
    outer = [(s, e) for s, _, e in wall if s not in blk]
    left = [e for s, e in outer if (first - s) % steps < 100]
    right = [e for s, e in outer if (s - first) % steps < steps // 2]
    assert left[-5:] == [0] * 5 and right[-5:] == [0] * 5        # K = 5 연속 0 에서 멈춤
    assert int(end["main_rows"]) == len(m) and int(end["reads_rows"]) == sum(n for _, _, n, _ in m)


def test_block_across_wrap(sims, tmp_path):
    """덩어리가 2519 → 0 에 걸친다 — 같은 절차, 원형 스텝, 천장에서 무반응 거짓 경보 없음, 중심이 범위 밖."""
    need(V1_25)
    steps, _, first, length = v1_rows(V1_25)
    steps, rows, first, length = v1_rows(V1_25, shift=steps - length // 2 - first)
    assert (first + length) % steps < first                     # 정말 걸쳤다
    lines = run_sim(sims[25], tmp_path, rows, steps)
    end = end_of(lines)
    assert (end["valid"], end["reason"]) == ("1", "complete")
    assert "block_out_of_range" in end["flags"].split(";")
    deep = {s for p, s, *_ in mains(lines) if p in ("ceil", "wall")}
    assert {steps - 1, 0} <= deep


def test_two_blocks(sims, tmp_path):
    need(V1_25)
    steps, rows, *_ = v1_rows(V1_25)
    rows2 = dict(rows)
    for s, v in rows.items():
        if 0 < v[0] < 1 or (v[0] == 1 and v[1] < 1):           # 덩어리 스텝만 1,260 떨어진 곳에 하나 더
            rows2[(s + 1260) % steps] = v
    end = end_of(run_sim(sims[25], tmp_path, rows2, steps))
    assert (end["valid"], end["reason"]) == ("0", "multi_block")


def test_sporadic_floor_errors(sims, tmp_path):
    """접촉 불량 산발 오류 — 바닥 한가운데에 오류가 튄 스텝은 덩어리 둘(⑨). 덩어리에 K 미만으로 붙은 것은 같은 덩어리."""
    need(V1_25)
    steps, rows, first, length = v1_rows(V1_25)
    far = dict(rows)
    far[(first + 1300) % steps] = (0.05, 0.0, 1)
    assert end_of(run_sim(sims[25], tmp_path, far, steps))["reason"] == "multi_block"
    near = dict(rows)
    near[(first - 3) % steps] = (0.05, 0.0, 1)                  # 틈 2스텝 < K
    end = end_of(run_sim(sims[25], tmp_path, near, steps))
    assert (end["valid"], end["reason"]) == ("1", "complete")


def test_contact_collapse(sims, tmp_path):
    """바깥 걷기 중 바닥이던 자리가 천장 높이로 — 그 자리에서 ⑫. 받은 묶음까지 M 행이 남는다."""
    need(V1_25)
    steps, rows, first, length = v1_rows(V1_25)
    at = (first + length + 1) % steps                            # 오른쪽 바깥 둘째 스텝
    lines = run_sim(sims[25], tmp_path, rows, steps, collapse_step=at)
    end = end_of(lines)
    assert (end["valid"], end["reason"]) == ("0", "contact_collapse")
    p, s, n, e = mains(lines)[-1]
    assert (p, s, n) == ("wall", at, 112) and e >= 205 * 112
    assert int(end["main_rows"]) == len(mains(lines))


def test_no_block_and_mode_names(sims, tmp_path):
    end = end_of(run_sim(sims[25], tmp_path, wall_n=2064384))
    assert (end["valid"], end["reason"], end["mode"], end["main_rows"]) == ("0", "no_block", "deep", "2520")
    assert end_of(run_sim(sims[25], tmp_path, wall_n=224))["mode"] == "n224"


def test_no_window(sims, tmp_path):
    rows = {s: (0.5, 0.5, 1) for s in range(2520)}
    end = end_of(run_sim(sims[25], tmp_path, rows))
    assert (end["valid"], end["reason"]) == ("0", "no_window")


def test_short_floor(sims, tmp_path):
    rows = {s: (1.0, 0.0, 1) for s in range(2400)}               # 덩어리 2,400 · 바닥 120 < 128
    end = end_of(run_sim(sims[25], tmp_path, rows))
    assert (end["valid"], end["reason"]) == ("0", "short_floor")


def test_wall_cap(sims, tmp_path):
    """덩어리 왼쪽에 벽 N 에서만 보이는 낮은 오류 받침(70스텝) — 64스텝을 넘어도 0 K 연속이 안 온다 → ⑩."""
    rows = gauss_rows(2520, 670, -60, 10, 60, 10)
    for k in range(1, 71):
        s = (670 - 8 - k) % 2520
        rows[s] = (1e-6, 0.0, 1)
    lines = run_sim(sims[25], tmp_path, rows, wall_n=8064)
    end = end_of(lines)
    assert (end["valid"], end["reason"]) == ("0", "wall_cap")
    first, length = block(np.array([e for p, _, _, e in mains(lines) if p == "scan"]))
    outer = [s for p, s, *_ in mains(lines) if p == "wall" and (s - first) % 2520 >= length]
    assert outer == [(first - k) % 2520 for k in range(1, 65)]  # 왼쪽으로 64스텝, 0 K 연속 없이


def test_drift_and_rescan_multi_block(sims, tmp_path):
    rows = gauss_rows(2520, 670, -60, 10, 60, 10)
    end = end_of(run_sim(sims[25], tmp_path, rows, rescan_rows=gauss_rows(2520, 673, -60, 10, 60, 10)))
    assert (end["valid"], end["flags"]) == ("1", "drift")
    end = end_of(run_sim(sims[25], tmp_path, rows, rescan_rows=gauss_rows(2520, 671, -60, 10, 60, 10)))
    assert (end["valid"], end["flags"]) == ("1", "")              # 1스텝은 표류가 아니다
    two = gauss_rows(2520, 670, -60, 10, 60, 10)
    for s in range(1800, 1820):
        two[s] = (0.2, 0.0, 1)                                   # 천장 문턱 아래 — 천장 끝은 그대로
    end = end_of(run_sim(sims[25], tmp_path, rows, rescan_rows=two))
    assert (end["valid"], end["flags"]) == ("1", "rescan_multi_block")


def test_block_out_of_range(sims, tmp_path):
    end = end_of(run_sim(sims[25], tmp_path, gauss_rows(2520, 1500, -60, 10, 60, 10)))
    assert (end["valid"], end["flags"]) == ("1", "block_out_of_range")


@pytest.mark.parametrize("stuck,reason", [(0, "line_dead_stuck0"), (1, "line_dead_stuck1")])
def test_line_dead(sims, tmp_path, stuck, reason):
    lines = run_sim(sims[25], tmp_path, stuck=stuck)
    end = end_of(lines)
    assert (end["valid"], end["reason"], end["main_rows"]) == ("0", reason, "2")


def test_no_feature(sims, tmp_path):
    lines = run_sim(sims[25], tmp_path, feature=2)               # bit1 만 — 에지 계수기 없음
    end = end_of(lines)
    assert (end["valid"], end["reason"], end["main_rows"]) == ("0", "no_feature", "0")
    assert not any(b"SWEEP BEGIN" in ln for ln in lines)


@pytest.mark.parametrize("env", [{"pos0": 3}, {"phase_skip": 2600}])
def test_phase_pos_mismatch(sims, tmp_path, env):
    """시작 위치가 0 이 아니거나, 덩어리로 되돌아가는 중 위상 명령 하나를 놓쳤다."""
    end = end_of(run_sim(sims[25], tmp_path, gauss_rows(2520, 670, -60, 10, 60, 10), **env))
    assert (end["valid"], end["reason"]) == ("0", "phase_pos_mismatch")


@pytest.mark.parametrize("bs,feature,reason", [(5, 1, "no_base_sector"), (2048, 3, "base_sector_mismatch")])
def test_base_sector_readback(sims, tmp_path, bs, feature, reason):
    """0 아닌 BASE_SECTOR 는 FEATURE bit1 이 있어야 하고, 쓴 값을 되읽어 맞댄다 (2,048 은 [10:0] 에 안 들어가 0 으로 읽힌다)."""
    lines = run_sim(sims[25], tmp_path, gauss_rows(2520, 670, -60, 10, 60, 10), base_sector=bs, feature=feature)
    end = end_of(lines)
    assert (end["valid"], end["reason"], end["main_rows"]) == ("0", reason, "0")
    assert not any(b"SWEEP BEGIN" in ln for ln in lines)


@pytest.mark.parametrize("bs,valid,reason", [(2041, "1", "complete"), (2042, "0", "cfg_err"), (2047, "0", "cfg_err")])
def test_base_sector_chip_end(sims, tmp_path, bs, valid, reason):
    """칩 끝 BASE_SECTOR — 훑기(N = 1)는 들어가고, 2042 부터는 천장 START(N = 112)가 R11 로 거부된다(DONE 없음).
    한도까지 돌지(done_stuck) 않고 바로 cfg_err. BEGIN 의 base_sector 는 되읽은 값."""
    lines = run_sim(sims[25], tmp_path, gauss_rows(2520, 670, -60, 10, 60, 10), base_sector=bs)
    end = end_of(lines)
    assert (end["valid"], end["reason"]) == (valid, reason)
    assert any(f"base_sector={bs}".encode() in ln for ln in lines if b"SWEEP BEGIN" in ln)
    m = mains(lines)
    assert [p for p, *_ in m[:2520]] == ["scan"] * 2520
    if valid == "0":
        assert len(m) == 2520 and int(end["main_rows"]) == 2520


@pytest.mark.parametrize("bug,reason", [("min", "r8_min_mismatch"), ("e1gt", "r8_e1_gt_e"), ("polarity", "r8_polarity")])
def test_r8_new_checks(sims, tmp_path, bug, reason):
    end = end_of(run_sim(sims[25], tmp_path, gauss_rows(2520, 670, -60, 10, 60, 10), bug=bug))
    assert (end["valid"], end["reason"]) == ("0", reason)


def test_75mhz_params(sims, tmp_path):
    """75MHz 묶음 — UI 840스텝 · 천장 문턱 410: 선반(읽기당 약 256)은 천장이 아니라 벽으로 잰다."""
    need(V1_75)
    steps, rows, first, length = v1_rows(V1_75)
    assert steps == 840
    lines = run_sim(sims[75], tmp_path, rows, steps)
    end = end_of(lines)
    assert (end["valid"], end["reason"]) == ("1", "complete")
    m = mains(lines)
    scan = {s: e for p, s, _, e in m if p == "scan"}
    assert len(scan) == 840
    ceil = {s for p, s, *_ in m if p == "ceil"}
    shelf = {s for s, e in scan.items() if 150 <= e < 350}
    assert ceil == {s for s, e in scan.items() if e >= 410} and shelf and not shelf & ceil
    assert any(b"f_sclk_hz=75000000" in ln and b"steps=840" in ln for ln in lines)


# ── 캡처 (수정안 #4 §2.6) ─────────────────────────────────────────────────
@pytest.fixture(scope="module")
def gauss_lines(sims, tmp_path_factory):
    tp = tmp_path_factory.mktemp("g")
    return run_sim(sims[25], tp, gauss_rows(2520, 670, -100, 8, 120, 20), wall_n=1120)


def test_capture_valid(gauss_lines, tmp_path):
    r = capture(gauss_lines, tmp_path)
    assert r.valid and r.reason == "complete" and r.gap_rows == 0
    assert r.main_path.name.startswith("bathtub2_loopback_") and r.reads_path.name.endswith("_reads.csv")
    main = read_csv(r.main_path)
    assert list(main[0])[9:14] == ["pass", "base_sector", "mode", "flags", "target"] and list(main[0])[-1] == "reason"
    assert {x["mode"] for x in main} == {"n1120"} and {x["base_sector"] for x in main} == {"0"}
    assert {x["reason"] for x in main} == {"complete"}
    reads = read_csv(r.reads_path)
    assert list(reads[0]) == cap2.READS_COLS.split(",")
    assert {x["pass"] for x in reads} == {"s", "c", "w", "r"}
    assert len(reads) == int(r.end["reads_rows"]) and len(main) == int(r.end["main_rows"])
    # 스텝마다 R 행 수 · Σ = 메인 행
    got = {}
    for y in reads:
        k = (y["pass"], y["phase_step"])
        n, e = got.get(k, (0, 0))
        got[k] = (n + 1, e + int(y["err_count"]))
    assert got == {(x["pass"][0], x["phase_step"]): (int(x["n_reads"]), int(x["bit_errors"])) for x in main}
    assert not list((tmp_path / "out").glob("*.spool"))


def test_capture_drop_main_row_is_invalid(gauss_lines, tmp_path):
    i = next(k for k, ln in enumerate(gauss_lines) if ln.startswith(b"M,") and b",wall" in ln)
    r = capture(gauss_lines[:i] + gauss_lines[i + 1:], tmp_path)
    assert not r.valid and r.reason == "row_mismatch" and r.main_path.name.endswith("_invalid.csv")


def test_capture_drop_reads_rows_is_reads_gap(gauss_lines, tmp_path):
    i = next(k for k, ln in enumerate(gauss_lines) if ln.startswith(b"M,") and b",wall" in ln)
    step = gauss_lines[i].split(b",")[1].decode()
    lines = gauss_lines[:i - 3] + gauss_lines[i - 1:]            # 그 스텝의 R 줄 둘을 버린다
    r = capture(lines, tmp_path)
    assert r.valid and r.gap_rows == 1
    main = read_csv(r.main_path)
    gap = [x for x in main if "reads_gap" in x["flags"]]
    assert [(x["pass"], x["phase_step"]) for x in gap] == [("wall", step)]
    # 분석기는 그 스텝의 읽기별 값을 안 쓴다
    summ, st, *_ = an2.analyze(r.main_path)
    row = next(t for t in st if t["phase_step"] == int(step))
    assert row["reads_gap"] == 1 and sum(row[f"reads_{k}"] for k in an2.OUTCOMES) == 0
    assert summ["gap_steps"] == 1


def set_step(lines, i, step):
    """M 줄 i 와 그 앞 R 줄 묶음(n_reads 줄)의 phase_step 을 step 으로 바꾼다 — 값은 그대로라 reads_gap 은 안 걸린다."""
    f = lines[i].split(b",")
    n = int(f[3])
    out = list(lines)
    for k in range(i - n, i + 1):
        g = out[k].split(b",")
        g[1] = str(step).encode()
        out[k] = b",".join(g)
    return out


def m_index(lines, pss):
    return [k for k, ln in enumerate(lines) if ln.startswith(b"M,") and ln.rstrip().endswith(b"," + pss)]


@pytest.mark.parametrize("which", ["scan", "rescan", "wall"])
def test_capture_step_set_mismatch_is_invalid(gauss_lines, tmp_path, which):
    """scan · rescan 이 0..UI 끝을 하나씩 갖지 않거나 (pass, phase_step) 가 겹치면 무효 — 행 수 · Σ 는 다 맞아도."""
    ms = m_index(gauss_lines, which.encode())
    a, b = ms[5], ms[6]
    step_a = int(gauss_lines[a].split(b",")[1])
    lines = set_step(gauss_lines, b, step_a)                     # b 를 a 와 같은 스텝으로
    r = capture(lines, tmp_path)
    assert not r.valid and r.reason == "row_mismatch" and r.gap_rows == 0


def test_capture_sum_mismatch_is_invalid(gauss_lines, tmp_path):
    """R 행은 다 왔는데 Σerr_count ≠ bit_errors (값이 깨짐) — reads_gap 이 아니라 무효."""
    i = m_index(gauss_lines, b"wall")[0]
    lines = list(gauss_lines)
    g = lines[i - 1].split(b",")
    g[3] = str(int(g[3]) + 1).encode()                           # 그 스텝 마지막 R 줄의 err_count
    lines[i - 1] = b",".join(g)
    r = capture(lines, tmp_path)
    assert not r.valid and r.reason == "row_mismatch" and r.gap_rows == 0


def test_capture_interrupted_is_invalid(gauss_lines, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        capture(gauss_lines[:-1], tmp_path)                      # END 전에 끊김
    assert list((tmp_path / "out").glob("*_invalid.csv"))
    assert not list((tmp_path / "out").glob("*.spool"))


def test_v1_capture_rejects_bathtub2_begin(gauss_lines, tmp_path):
    r = cap1.capture_sweep(Lines(gauss_lines), "loopback", None, tmp_path, log=open(os.devnull, "w"))
    assert not r.valid and r.n_main == 0 and r.n_reads == 0 and r.reason == "no_end"


def test_v2_capture_rejects_v1_begin(tmp_path):
    v1 = [b"#G0 SWEEP BEGIN steps=2520 n=112 b=2048 f_sclk_hz=25000000 dphi_ps=15.873016\r\n",
          b"M,0,0.000,112,2048,0,0,0,25000000,15.873016\r\n", b"#G0 SWEEP END valid=1 reason=complete\r\n"]
    r = capture(v1, tmp_path)
    assert not r.valid and r.n_main == 0 and r.reason == "no_end"


def test_capture_base_sector_expectation(gauss_lines, tmp_path):
    r = capture(gauss_lines, tmp_path, expect_base_sector=7)
    assert not r.valid and r.n_main == 0


def test_capture_base_sector_expectation_zero(gauss_lines, tmp_path):
    """반대 방향 — 0 을 원했는데 스트림이 5 면 거부, 0 이면 유효 (2026-11-17 리뷰 F6: `if expect:` 로 바뀌면 0 이 빠진다)."""
    five = [ln.replace(b"base_sector=0", b"base_sector=5") if b"SWEEP BEGIN" in ln else ln for ln in gauss_lines]
    assert any(b"base_sector=5" in ln for ln in five)
    r = capture(five, tmp_path / "a", expect_base_sector=0)
    assert not r.valid and r.n_main == 0 and r.begin.get("base_sector") == "5"
    assert capture(gauss_lines, tmp_path / "b", expect_base_sector=0).valid


class Chunks:
    """포트 대역 — in_waiting · read 가 있어 _Pump 가 덩어리로 읽는다. 아무 데서나 끊긴 조각, 가끔 빈 읽기(timeout).
    빈 읽기는 잠깐 쉰다(헛돌며 GIL 을 쥐지 않게). 다 내보낸 뒤 빈 읽기가 이어지면 Ctrl-C 로 본다 — END 가 안 오는 회귀가 멈추지 않게."""
    port, baudrate = "sim", 921600

    def __init__(self, data, seed=1):
        self.data, self.rng, self.idle = data, np.random.default_rng(seed), 0

    @property
    def in_waiting(self):
        return int(self.rng.integers(0, 5000)) if self.data else 0

    def read(self, n=1):
        if not self.data or self.rng.random() < 0.05:
            import time
            time.sleep(0.001)
            self.idle += not self.data
            if self.idle > 3000:
                raise KeyboardInterrupt
            return b""
        out, self.data = self.data[:n], self.data[n:]
        return out


def _same_capture(a, b):
    assert a.valid and b.valid and (a.n_main, a.n_reads) == (b.n_main, b.n_reads)
    for p, q in ((a.main_path, b.main_path), (a.reads_path, b.reads_path)):
        drop = lambda rows: [{k: v for k, v in x.items() if k not in ("generated_at", "batch_id")} for x in rows]  # noqa: E731
        assert drop(read_csv(p)) == drop(read_csv(q))


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_capture_chunked_port(gauss_lines, tmp_path, eol):
    """덩어리 읽기(11/17 초심부 행 유실 수정) — 줄 중간에서 끊긴 조각 · 빈 읽기에도 줄 단위 캡처와 같은 파일.
    펌웨어 줄 끝 \\r\\n 도."""
    ref = capture(gauss_lines, tmp_path / "ref")
    data = b"".join(gauss_lines).replace(b"\n", eol)
    r = cap2.capture_bathtub2(Chunks(data), "loopback", None, tmp_path / "out",
                              log=open(os.devnull, "w"))
    _same_capture(r, ref)


def test_capture_chunked_through_drained(gauss_lines, tmp_path):
    """실행기 경로 — xsct 구간 선수신(Drained 버퍼, 줄 중간에서 끝남) 뒤에 포트 조각이 이어진다."""
    sys.path.insert(0, str(REPO / "host" / "run"))
    from run_sweep_chip import Drained
    data = b"".join(gauss_lines)
    ref = capture(gauss_lines, tmp_path / "ref")
    r = cap2.capture_bathtub2(Drained(Chunks(data[5003:]), data[:5003]), "loopback", None, tmp_path / "out",
                              log=open(os.devnull, "w"))
    _same_capture(r, ref)


def test_pump_dead_port_raises(tmp_path):
    """시작부터 죽은 포트(선수신 0B, in_waiting 이 OSError) — 끝없이 b"" 를 돌지 않고 port_error 로 정리된다 (리뷰 M1)."""
    class Dead(Chunks):
        @property
        def in_waiting(self):
            raise OSError(5, "Input/output error")
    with pytest.raises(OSError):
        cap2.capture_bathtub2(Dead(b""), "loopback", None, tmp_path / "out", log=open(os.devnull, "w"))
    assert [p.name for p in (tmp_path / "out").glob("*.csv")] and all("_invalid" in p.name for p in (tmp_path / "out").glob("*.csv"))


def test_pump_keeps_up_under_gil_contention():
    """진짜 pyserial 포트(pty)에서, 다른 스레드가 GIL 을 계속 쓰는 동안(스풀 옮기기 흉내) _Pump 가 921600 baud
    (92KB/s) 를 따라가는가 — 회귀 판별용. 순수 CPU 경합이라 옛 readline(1바이트씩) 은 1KB/s 미만, 새 펌프는
    약 330KB/s(pty 버퍼 4KB ÷ GIL 전환 5ms 로 정해지는 값이라 실포트 능력은 아니다). 문턱은 둘 사이 20KB/s."""
    serial = pytest.importorskip("serial")
    pytest.importorskip("termios")                       # pty 는 POSIX 만
    import pty
    import threading
    import time
    m, s = pty.openpty()
    line = b"R,620,17,3,929,0,930,464,0,465\n"
    n = 60000                                            # 약 1.9MB
    port = serial.Serial(os.ttyname(s), 921600, timeout=1)
    stop = threading.Event()

    def writer():
        v = memoryview(line * n)
        while v:
            v = v[os.write(m, v[:4096]):]

    def burner():
        while not stop.is_set():
            for r in range(1000):
                str(r).split(",")

    threading.Thread(target=writer, daemon=True).start()
    threading.Thread(target=burner, daemon=True).start()
    p = cap2._Pump(port)
    try:
        t, got = time.monotonic(), 0
        while got < n and time.monotonic() - t < 60:
            got += bool(p.readline())
        dt = time.monotonic() - t
    finally:
        stop.set()
        p.stop()
        p.join()
        port.close()
        os.close(m)
        os.close(s)
    assert got == n and n * len(line) / dt > 20e3, f"{got}/{n} 줄, {n * len(line) / dt / 1e3:.0f} KB/s"


def test_print_set_vars_live_in_data(sims):
    """xsct 가 dow 뒤 print -set 으로 덮어쓰는 변수는 .data 에 있어야 한다 — .bss 면 con 직후 crt0 이 0 으로 지운다
    (2026-11-17 g_base_sector 사건, 로그 49). 시뮬레이션은 덮어쓰기를 .bss 가 지워진 뒤에 해서 동작으로는 못 잡는다(리뷰 F5) —
    그래서 기호의 섹션을 본다. 호스트 gcc 도 초기값 0 을 .bss 에 두는 규칙이 같다. 빌드된 ARM ELF 가 있으면 그것도 본다."""
    import re
    if not shutil.which("nm"):
        pytest.skip("nm 이 없다")
    names = set(re.findall(r"print -set ([A-Za-z_][A-Za-z0-9_]*)","".join(p.read_text() for p in (REPO / "ps" / "scripts").glob("*.tcl"))))
    assert {"g_uart_baud", "g_wall_n", "g_base_sector"} <= names
    elfs = [sims[25], sims[75]] + sorted(REPO.glob("build/vitis_*/*/build/*.elf"))   # 빌드된 ARM ELF 전부 (없는 PC 는 sim 만)
    found = set()
    for elf in elfs:
        sym = {}
        for ln in subprocess.run(["nm", str(elf)], check=True, capture_output=True, text=True).stdout.splitlines():
            f = ln.split()
            if len(f) == 3:
                sym[f[2]] = f[1]
        for n in names & sym.keys():
            found.add(n)
            assert sym[n] in "Dd", (f"{elf.relative_to(REPO) if elf.is_relative_to(REPO) else elf}: {n} 이 {sym[n]} 섹션 — "
                                    f".data 에 둬야 한다. 옛 빌드면 다시 빌드한다")
    assert names <= found, f"기호를 어느 ELF 에서도 못 찾았다(빈 통과 방지): {sorted(names - found)}"


# ── 분석기 (S-6 §5) ───────────────────────────────────────────────────────
def h12(s):
    return math.sqrt(s * s + DPHI * DPHI / 12)                  # 폭에 든 스텝 양자화 몫


@pytest.mark.parametrize("mu_r,s_r,mu_f,s_f,t0", [
    (-100, 8, 120, 20, None),          # 상승이 이른 칩
    (110, 20, -90, 8, None),           # 하강이 이른 칩
    (-100, 8, 120, 20, 10.0),          # 덩어리 안에서 정렬 번호가 하나 오른다 (t0 이동)
])
def test_analyzer_recovers_edges(sims, tmp_path, mu_r, s_r, mu_f, s_f, t0):
    lines = run_sim(sims[25], tmp_path, gauss_rows(2520, 670, mu_r, s_r, mu_f, s_f, t0_shift_ps=t0), wall_n=1120)
    r = capture(lines, tmp_path)
    assert r.valid
    out = tmp_path / "an"
    (summ,) = an2.main([str(r.main_path), "--outdir", str(out)])
    # 원점 = 훑기 덩어리 중점. 주입은 스텝 670 기준이라 그 차이만큼 옮겨 맞댄다
    c0 = summ["block_first"] + (summ["block_steps"] - 1) / 2
    off = (670 - c0) * DPHI
    assert summ["mu_rise_ps"] == pytest.approx(mu_r + off, abs=1.5)
    assert summ["mu_fall_ps"] == pytest.approx(mu_f + off, abs=1.5)
    assert summ["dcd_ps"] == pytest.approx(mu_f - mu_r, abs=2.0)
    assert summ["width_rise_ps"] == pytest.approx(h12(s_r), abs=1.5)
    assert summ["width_fall_ps"] == pytest.approx(h12(s_f), abs=1.5)
    assert {p.name for p in out.iterdir()} >= {f"{r.main_path.stem}_p1.png", f"{r.main_path.stem}_edges.png",
                                               f"{r.main_path.stem}_steps.csv", "bathtub2_edges.csv"}


def step_tol(k, mu):
    """이항(작은 기대값은 포아송) 잡음 허용 — 5σ + 3개."""
    return abs(k - mu) <= 5 * math.sqrt(mu) + 3


@pytest.mark.parametrize("now,idle,preamble", [
    (1, 1, 0), (2, 1, 0),              # 쪽 머리 전이 없음 (유휴 1)
    (1, 0, 0), (2, 0, 0),              # 유휴 0 — 쪽 머리 상승이 「다음 비트」 창에 들어 어긋남 2 까지
    (1, 0, 1), (2, 0, 1),              # 유휴 0 + 합성 프리앰블 (RTL 과 같은 조합 — 정렬 0 은 쪽 머리를 가린다)
])
def test_analyzer_tail_fractions(sims, tmp_path, now, idle, preamble):
    """벽 집중 스텝마다 에지별 「먼저 온 비율」 이 주입 누적분포와 이항 잡음 안에서 맞는다 — 평균 · 폭이 아니라 꼬리.
    벽 N = 8,064 (스텝당 상승 약 400만 개)라 바깥 꼬리가 1e-5 아래로 내려간다. 바닥 쪽 꼬리에서 두 짝이 다 맞는
    읽기를 빼면 꼬리가 한없이 치우친다(리뷰 H1) — 옆 짝 규칙으로 모든 읽기에 짝이 있어야 한다."""
    rows = gauss_rows(2520, 670, -100, 8, 120, 20, now=now)
    lines = run_sim(sims[25], tmp_path, rows, wall_n=8064, idle=idle, preamble=preamble)
    r = capture(lines, tmp_path)
    assert r.valid
    summ, st, *_ = an2.analyze(r.main_path)
    pages = range(112)
    R = sum(an2.page_counts(p)[1] for p in pages)
    F = sum(an2.page_counts(p)[2] for p in pages)
    deep = [t for t in st if t["pass"] in an2.DEEP]
    assert len(deep) == summ["deep_steps"] > 10
    assert summ["reads_near"] == summ["reads_none"] == 0
    assert summ["reads_paired"] == sum(t["n_reads"] for t in deep)
    low_r, low_f = [], []
    for t in deep:
        pr, pf, _ = rows[t["phase_step"]]
        m = t["n_reads"] // 112
        assert t["frac_rise"] != "" and t["frac_fall"] != ""
        kr, kf = t["frac_rise"] * m * R, t["frac_fall"] * m * F
        assert kr == pytest.approx(round(kr), abs=1e-6) and kf == pytest.approx(round(kf), abs=1e-6)
        assert step_tol(round(kr), m * R * pr), (t["phase_step"], t["frac_rise"], pr)
        assert step_tol(m * F - round(kf), m * F * (1 - pf)), (t["phase_step"], t["frac_fall"], pf)
        if t["pass"] == "wall" and 0 < t["frac_rise"] < 1e-5:
            low_r.append(t["frac_rise"])
        if t["pass"] == "wall" and 0 < 1 - t["frac_fall"] < 1e-5:
            low_f.append(1 - t["frac_fall"])
    assert low_r and low_f                                       # 두 바깥 꼬리 모두 1e-5 아래 점이 있다
    assert summ["reads_both"] > 0                                # 바닥 쪽 꼬리에서 두 짝이 다 맞는 읽기를 옆 짝으로 받았다


def test_analyzer_rejects_v1_file(tmp_path):
    p = tmp_path / "sweep_chip01_20260708T164931Z.csv"
    p.write_text("phase_step,n_reads\n0,112\n")
    with pytest.raises(SystemExit):
        an2.read_main(p)


def test_analyzer_selfcheck():
    an2.selfcheck()
