"""`host/run/run_wear.py` — 판정·로그 분리·명령 조립은 순수 함수로, 시리얼·xsct 경로는 sim 파이프로."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import harness as H
import host_side as hs
import mock_engine as me

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "run"))
import run_wear as rw                                        # noqa: E402

RUN_WEAR = REPO / "host" / "run" / "run_wear.py"
CHIP01_UID = me.REGISTRY_UID


def _mock_result(**kw):
    r = H.run(**kw)
    return r, r.engine.wear_status(), r.engine.tally_read(), r.engine.tally_dump(), r.engine.uid_read()


def _probe(r):
    return r.engine.blank_check(r.base, r.n_sectors)          # accept 가 멈춘 뒤 부르는 시험 버튼


def test_judge_accept_passes_on_good_run():
    r, st, tally, dumps, uid = _mock_result()
    v = rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID, probe=_probe(r))
    assert [i for i, _, _ in v] == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "C", "probe"]
    assert all(ok for _, ok, _ in v), v


@pytest.mark.parametrize("bug, item", [("undercount", "A1"), ("drop_sector_rows", "A2"),
                                       ("drop_b_row", "A3"), ("tally_single", "A5"),
                                       ("uid_wrong", "A7"), ("program_check_dead", "probe")])
def test_judge_accept_fails_the_right_item(bug, item):
    r, st, tally, dumps, uid = _mock_result(bugs={bug})
    failed = {i for i, ok, _ in rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID, probe=_probe(r)) if not ok}
    assert item in failed


def test_judge_accept_probe_none_is_fail():
    r, st, tally, dumps, uid = _mock_result()
    v = dict((i, ok) for i, ok, _ in rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID, probe=None))
    assert v["probe"] is False and v["C"] is True                  # BLANK 거부 = 확인 못 함 = FAIL


def test_judge_accept_C_needs_checkpoint_due():
    r, st, tally, dumps, uid = _mock_result()
    v = dict((i, ok) for i, ok, _ in rw.judge_accept(r.log, (100, "halted", False, ""), tally, dumps, uid, CHIP01_UID))
    assert v["C"] is False and v["A1"] is True


def test_judge_accept_A6_flags_slow_erase():
    r, st, tally, dumps, uid = _mock_result()
    r.log.a[3]["t_erase_us"] = 400_001
    v = dict((i, ok) for i, ok, _ in rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID))
    assert v["A6"] is False and v["A1"] is True


def test_judge_accept_A6_is_acceptance_only():
    """마모 런(erase_check=False)에서는 A6 가 없고, 400ms 를 넘는 소거가 구간을 세우지 않는다 (로그 48 §12)."""
    r, st, tally, dumps, uid = _mock_result()
    r.log.a[3]["t_erase_us"] = 400_001
    v = rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID, probe=_probe(r), erase_check=False)
    assert [i for i, _, _ in v] == ["A1", "A2", "A3", "A4", "A5", "A7", "C", "probe"]
    assert all(ok for _, ok, _ in v), v


def test_plan_segments_confirms_the_first_checkpoints():
    """확인(enter)은 앞의 K **체크포인트**에만 붙는다 — 쪼갠 경계는 묻지 않는다."""
    segs = rw.plan_segments(0, 100_000, rw.SEG_CHUNK, 2, rw.CHECKPOINTS)
    assert [st + d for st, d, c, _ in segs if c] == [100, 1_000]     # 앞 두 체크포인트에서만 묻는다
    assert all(cp for _, _, c, cp in segs if c)                    # 확인이 붙은 경계는 전부 체크포인트
    # 체크포인트가 없으면(TB) 앞 K 구간에 붙는다 — 예전 동작 그대로
    segs = rw.plan_segments(0, 300, 100, 2)
    assert [c for *_, c, _ in segs] == [True, True, False]


def test_plan_segments_breaks_at_every_checkpoint():
    """체크포인트가 구간 경계다 — 그 사이가 --delta 보다 길면 더 쪼개고, 쪼갠 끝은 체크포인트가 아니다."""
    segs = rw.plan_segments(0, 100_000, rw.SEG_CHUNK, 0, checkpoints=rw.CHECKPOINTS)
    ends = [st + d for st, d, _, cp in segs if cp]
    assert ends == list(rw.CHECKPOINTS)                        # 13점 전부가 구간 끝으로 선다
    assert segs[0] == (0, 100, False, True) and segs[1] == (100, 900, False, True)
    assert sum(d for _, d, _, _ in segs) == 100_000            # 총량은 그대로
    # 체크포인트 사이가 SEG_CHUNK 보다 길면 쪼갠다 — 13점 격자에는 그런 간격이 없어 파일럿의 긴 간격으로 본다
    segs = rw.plan_segments(0, 300_000, rw.SEG_CHUNK, 0, checkpoints=(137_000, 294_500, 300_000))
    mid = [(st, d, cp) for st, d, _, cp in segs if 137_000 <= st < 294_500]
    assert len(mid) > 1 and not any(cp for *_, cp in mid[:-1]) and mid[-1][2]   # 긴 구간은 쪼개진다
    assert sum(d for _, d, _, _ in segs) == 300_000


def test_resolve_defaults_need_only_the_chip():
    """사람이 칩만 줘도 계획이 선다 — 목표는 마지막 체크포인트, 확인은 앞 1점."""
    ap = rw.build_parser()
    args = ap.parse_args(["accept", "--chip", "chip01"])
    rw.resolve_accept(ap, args)
    assert args.checkpoint_list == rw.CHECKPOINTS and args.confirm_first == 1 and args.cycle is None
    to = rw.resolve_target(lambda m: pytest.fail(m), args, 0)
    assert to == rw.CHECKPOINTS[-1] == 100_000               # 종단 종점 = 정격 내구 (S-1 §15)
    segs = rw.build_segments(args, 0, to)
    assert sum(d for _, d, _, _ in segs) == 100_000 and [g[0] + g[1] for g in segs if g[3]] == list(rw.CHECKPOINTS)
    # TB(체크포인트 없음)는 100사이클 한 구간 — 인수 시험 모양
    args = ap.parse_args(["accept", "--base-sector", "1000"])
    rw.resolve_accept(ap, args)
    assert args.checkpoint_list == ()
    assert rw.build_segments(args, 0, rw.resolve_target(lambda m: pytest.fail(m), args, 0)) == [(0, 100, True, False)]


LEDGER = [("0~127", "미상(≥1)", "flash_prep", "소급 불가"),
          ("1000~1006", "+100", "run_wear accept (session 1)", "cycle 0→100"),
          ("512", "+1", "run_wear tally-erase (session 2)", "tally erase · 지운 값 a=1 b=1"),
          ("1536", "+1", "run_wear tally-erase (session 2)", "tally erase · 지운 값 a=1 b=1"),
          ("0~6", "+300", "run_wear accept (session 3)", "cycle 0→300"),
          ("0~6", "+1", "run_wear checkpoint (session 3)", "체크포인트 300 — 소거+PRBS"),
          ("0~6", "+37", "run_wear accept (session 4)", "cycle 보정: tally 300 → 시작 337"),
          ("2", "±1", "run_wear resume (session 4)", "reerase · ±1")]


def test_ledger_correction_only_covers_what_the_ledger_missed():
    """호스트가 먼저 죽어 구간 행이 없으면 채택값까지 보정하고, 엔진이 error 로 서서 +done 이 이미 적혔으면 0 이다."""
    assert rw.ledger_correction(337, 300, 300) == 37          # host_died — 장부 300 · tally 300 · 채택값 337
    assert rw.ledger_correction(122_164, 122_100, 122_164) == 0   # error 정지 — 장부가 이미 122,164
    assert rw.ledger_correction(122_164, 122_100, None) == 64     # 장부를 못 읽으면 tally 기준
    assert rw.ledger_correction(122_100, 122_100, 122_164) == 0   # 장부가 앞서면 적지 않는다


def test_ledger_wear_counts_only_after_the_last_tally_erase():
    """tally 와 맞댈 값 = 마지막 실험 개시 소거 이후의 run_wear accept 증분 합 (영역은 구분하지 않는다)."""
    wear, areas, bad = rw.ledger_wear(LEDGER)
    assert wear == 337 and areas == {"0~6"} and bad == 0        # TB 100 은 소거 이전이라 빠진다
    assert rw.ledger_wear(LEDGER[:2]) == (100, {"1000~1006"}, 0)


def test_ledger_area_total_counts_every_overlapping_row():
    """곡선 x축 = 그 영역이 실제로 받은 P/E 합 — 범위가 겹치면 prep·체크포인트도 센다."""
    total, unknown = rw.ledger_area_total(LEDGER, 0, 7)
    assert total == 338 and unknown == 2       # 300+1+37 · 값을 모르는 둘(미상(≥1) · 재소거 ±1)은 뺀다
    assert rw.ledger_area_total(LEDGER, 1000, 7) == (100, 0)   # TB 영역
    assert rw.parse_area("1000~1006") == (1000, 1006) and rw.parse_area("512") == (512, 512)


def test_summary_and_estimate_come_from_the_A_rows():
    """소거 시간 요약과 예상 시간 단가는 A 행에서 나온다 (ts 간격의 중앙값 = 사이클 실소요)."""
    rows = [{"cycle": c, "sector": s, "t_erase_us": 40_000 + 100 * c, "t_program_us": 11_000,
             "ts": c * 500_000 + s} for c in range(1, 11) for s in range(7)]
    acc = rw.collect(rows, rw.new_acc())
    out = rw.summarize(acc)
    assert out["t_erase_p50"] == 40_600 and out["t_erase_max"] == 41_000
    assert out["t_program_p50"] == out["t_program_max"] == 11_000               # 쓰기도 같은 해상도로
    assert out["cycle_s_p50"] == 0.5                                           # ts 간격 0.5s
    segs = [(0, 1000, False, True), (1000, 1000, False, True)]
    assert rw.estimate(segs, 0.5, 120.0) == 2000 * 0.5 + 2 * 120.0


def test_split_rows_keeps_only_checksummed_rows():
    r = H.run(faults={"garbage_prefix", "truncate"})
    raw = r.link.drain() if False else None                   # link 는 이미 비워졌다 — 원문을 다시 만든다
    lines = ["\x00\xfe" + hs.PREFIX + hs.with_sum("A cycle=1 sector=0 t_erase_us=1 t_program_us=2 ts=3"),
             hs.PREFIX + "A cycle=1 sector=1 t_erase_us=1 t_prog",                # 잘림
             "OK req=1 sum=0000",
             hs.PREFIX + hs.with_sum("R kind=halt cycle=5 sector= op= t_us= ok=1 resid_before= resid_after= ts=9")]
    out = rw.split_rows(lines)
    assert len(out["A"]) == 1 and out["A"][0].startswith(hs.PREFIX + "A cycle=1")   # 쓰레기 접두 제거
    assert len(out["R"]) == 1 and out["B"] == [] and raw is None


def test_start_command_is_the_locked_syntax():
    assert rw.start_command(300, 345, 1758412800, base=1000).startswith(
        "WEAR START base=1000 n_sectors=7 pattern=0x00 cycle=300 delta=345 session=1758412800 req=1 sum=")


def test_host_log_max_from_session_dir(tmp_path):
    (tmp_path / "A.txt").write_text(hs.PREFIX + hs.with_sum("A cycle=147 sector=1000 t_erase_us=1 t_program_us=2 ts=3") + "\n")
    assert rw.host_log_max_from(tmp_path) == 147


# ── sim 파이프로 끝까지 ────────────────────────────────────────────────────
CHIP_PE_DOC = ("# 이력\n\n## 이력\n\n"
               "| 일자 | 라벨 | UID | 섹터 범위 | P/E 증분 | 출처 | 비고 |\n"
               "| ---- | ---- | --- | --------- | -------- | ---- | ---- |\n"
               "| 2026-07-08 | chip01 | (미확보) | 0~127 | 미상(≥1) | flash_prep | 소급 불가 |\n")


def _run(args, tmp_path, sim_bin, extra_env=None, stdin=""):
    pe = tmp_path / "chip_pe.md"
    if not pe.exists():
        pe.write_text(CHIP_PE_DOC)
    cmd = [sys.executable, str(RUN_WEAR), *args, "--sim", str(sim_bin), "--no-program",
           "--logdir", str(tmp_path / "logs"), "--chip-pe", str(pe), "--sim-state", str(tmp_path / "chip.bin")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, input=stdin)
    return r, pe


def test_tally_erase_needs_typed_uid_and_writes_ledger_first(sim_bin, tmp_path):
    """같은 칩으로 0 부터 다시 — 자물쇠 셋 (UID 타이핑 · 장부 먼저 · 엔진의 idle/UID 대조)."""
    r, pe = _run(["accept", "--session", "1758412900", "--base-sector", "1000", "--to", "100"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr                 # tally 에 1바이트가 남는다
    rows_before = pe.read_text().count("tally erase")
    # 빈 입력 · 틀린 UID → 지우지 않고 장부도 안 건드린다. 종료 코드 3
    for typed in ("", "0000000000000000\n", "y\n"):
        r, _ = _run(["tally-erase", "--session", "1758412901"], tmp_path, sim_bin, stdin=typed)
        assert r.returncode == 3 and "지우지 않는다" in r.stderr, (typed, r.stdout, r.stderr)
        assert pe.read_text().count("tally erase") == rows_before
    r, _ = _run(["tally"], tmp_path, sim_bin)
    assert "tally_a=1 tally_b=1" in r.stdout
    # 맞는 UID (소문자도 받는다) → 장부 두 행(512·1,536) 뒤에 소거. 그 다음 cycle=0 신규 시작이 열린다
    r, _ = _run(["tally-erase", "--session", "1758412902"], tmp_path, sim_bin, stdin=CHIP01_UID.lower() + "\n")
    assert r.returncode == 0 and "clean=1" in r.stdout and "지운 값 a=1 b=1" in r.stdout, r.stdout + r.stderr
    tail = pe.read_text().splitlines()[-2:]
    assert "| 512 | +1 | run_wear tally-erase (session 1758412902) | tally erase · 지운 값 a=1 b=1 |" in tail[0]
    assert "| 1536 | +1 |" in tail[1]
    r, _ = _run(["tally"], tmp_path, sim_bin)
    assert "tally_a=0 tally_b=0" in r.stdout
    r, _ = _run(["accept", "--session", "1758412903", "--base-sector", "1000", "--to", "100"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr                 # E_DIRTY 가 아니다


def test_tally_erase_refuses_real_chip_without_flag(tmp_path):
    r = subprocess.run([sys.executable, str(RUN_WEAR), "tally-erase", "--no-program", "--port", "/dev/null",
                        "--logdir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 3 and "--i-approve-tally-erase" in r.stderr


def test_accept_end_to_end_on_sim(sim_bin, tmp_path):
    r, pe = _run(["accept", "--session", "1758412800", "--base-sector", "1000", "--to", "100"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    d = tmp_path / "logs" / "1758412800"
    verdict = (d / "verdict.txt").read_text()
    assert verdict.count("PASS") == 9 and "FAIL" not in verdict, verdict
    assert "PASS  probe program_fail_bits 229376 (기대 229376) 잔류 0" in verdict
    assert len((d / "A.txt").read_text().splitlines()) == 700
    assert len((d / "B.txt").read_text().splitlines()) == 1 and (d / "H.txt").exists()
    assert "WEAR START base=1000 n_sectors=7 pattern=0x00 cycle=0 delta=100 session=1758412800" in (d / "commands.txt").read_text()
    assert "baud rate  : 마모 921600 · 스윕 921600" in (d / "plan.txt").read_text()   # 계획서에 보 레이트가 남는다
    tail = pe.read_text().splitlines()[-1]
    assert tail.startswith("| ") and "| chip01 | D1654CB09B352233 | 1000~1006 | +100 | run_wear accept (session 1758412800) |" in tail

    # 같은 칩에 다시 신규 시작 — E_DIRTY 로 막힌다 (tally 마크가 남아 있다)
    r2, _ = _run(["accept", "--session", "1758412801", "--base-sector", "1000", "--cycle", "0", "--to", "100"],
                 tmp_path, sim_bin)
    assert r2.returncode == 3 and "E_DIRTY" in r2.stderr
    # 이어 돌리기 — --cycle 을 안 줘도 칩의 tally(100)에서 이어 간다. 채점은 구간 기준
    r3, _ = _run(["accept", "--session", "1758412802", "--base-sector", "1000", "--to", "200"], tmp_path, sim_bin)
    assert r3.returncode == 0, r3.stdout                      # 이 세션이 본 것만 센다 (A2·A3·A5)
    assert "PASS  A1    카운터 200" in r3.stdout and "PASS  A2    A 행 700 (기대 700)" in r3.stdout
    assert "| 1000~1006 | +100 |" in pe.read_text().splitlines()[-1]


def test_accept_ladder_runs_segments_to_target(sim_bin, tmp_path):
    """--to 하나로 구간을 이어 간다 — 계획이 먼저 남고, 구간마다 판정이 붙고, 장부에도 구간마다 한 행."""
    r, pe = _run(["accept", "--session", "1758412810", "--base-sector", "1000",
                  "--checkpoints", "100,200,300", "--confirm-first", "0", "--to", "300"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    d = tmp_path / "logs" / "1758412810"
    plan = (d / "plan.txt").read_text()
    assert "마모 섹터  : 1000~1006" in plan and "체크포인트 : 3점 — 100 · 200 · 300" in plan
    assert "[구간 3/3] 누적 200 → 300" in r.stdout
    verdict = (d / "verdict.txt").read_text()
    assert verdict.count("PASS") == 27 and "FAIL" not in verdict, verdict      # 9줄 × 3구간
    assert len((d / "A.txt").read_text().splitlines()) == 2100                 # 구간마다 덧붙었다
    assert pe.read_text().count("run_wear accept (session 1758412810)") == 3


def test_accept_ladder_stops_when_the_human_says_q(sim_bin, tmp_path):
    """확인 지점에서 q — 다음 구간을 시작하지 않는다. 그 자리까지는 정상 종료."""
    r, pe = _run(["accept", "--session", "1758412811", "--base-sector", "1000",
                  "--checkpoints", "100,200,300", "--confirm-first", "2", "--to", "300"],
                 tmp_path, sim_bin, stdin="q\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "사람이 멈췄다 — 누적 100" in r.stdout and "[구간 2/3" not in r.stdout
    assert pe.read_text().count("run_wear accept (session 1758412811)") == 1


def test_accept_runs_through_checkpoints_without_stopping_the_wear(sim_bin, tmp_path):
    """마모 그룹은 체크포인트가 구간 경계다. 재는 것은 sim 에서 건너뛰지만 **마모는 멈추지 않는다**."""
    r, pe = _run(["accept", "--session", "1758412830", "--to", "1000", "--confirm-first", "0"],
                 tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    plan = (tmp_path / "logs" / "1758412830" / "plan.txt").read_text()
    assert "마모 섹터  : 0~6" in plan and "체크포인트 : 2점 — 100 · 1,000" in plan
    assert "체크포인트 100 — 측정을 건너뛴다 (sim)" in r.stdout
    assert "[구간 2/2] 누적 100 → 1,000 · 900 사이클" in r.stdout      # 체크포인트를 지나 끝까지 간다
    rows = [l for l in pe.read_text().splitlines() if "1758412830" in l]
    assert [l.split("|")[5].strip() for l in rows] == ["+100", "+900"]
    assert all("| 0~6 |" in l for l in rows)


def test_accept_confirms_at_the_first_k_checkpoints(sim_bin, tmp_path):
    """--confirm-first 2 면 enter 를 두 번 친다 — 그 뒤로는 묻지 않고 무인으로 간다."""
    r, _ = _run(["accept", "--session", "1758412831", "--to", "3000", "--confirm-first", "2"],   # 100 · 1,000 · 3,000
                tmp_path, sim_bin, stdin="\n\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("확인했으면 enter") == 2
    assert "체크포인트 100 확인 (남은 유인 2회)" in r.stdout
    assert "유인 확인 종료 — 여기부터 3,000 까지 무인 실행" in r.stdout


def test_accept_refuses_a_target_off_the_tally_grid(tmp_path):
    """구간은 tally 눈금(100)의 배수여야 한다 — 사람이 다시 친다. --cycle 은 예외(복구 채택값)."""
    for bad in (["--to", "1050"], ["--checkpoints", "300,650"]):
        r = subprocess.run([sys.executable, str(RUN_WEAR), "accept", "--no-program", "--port", "/dev/null",
                            "--logdir", str(tmp_path), *bad], capture_output=True, text=True)
        assert r.returncode == 2 and "100 의 배수로 준다" in r.stderr, (bad, r.stderr)


def test_wear_area_moves_with_base_sector(sim_bin, tmp_path):
    """--base-sector 0 = 마모 그룹 0~6. START·장부·계획이 같은 자리를 가리킨다 (기본은 TB 1,000)."""
    assert rw.start_command(0, 100, 1, base=0).startswith("WEAR START base=0 n_sectors=7 ")
    r, pe = _run(["accept", "--session", "1758412820", "--base-sector", "0", "--to", "100"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    plan = (tmp_path / "logs" / "1758412820" / "plan.txt").read_text()
    assert "마모 섹터  : 0~6 (7섹터 · 112페이지)" in plan
    assert "| 0~6 | +100 |" in pe.read_text().splitlines()[-1]


def test_sim_refuses_to_touch_the_real_ledger(tmp_path):
    """연습(--sim)은 P/E 를 내지 않는다 — 그 행이 진짜 이력에 붙으면 거짓이고, tally 대조가 그것을 센다."""
    for cmd in ("accept", "resume", "tally-erase"):
        r = subprocess.run([sys.executable, str(RUN_WEAR), cmd, "--sim", "/bin/true", "--no-program",
                            "--logdir", str(tmp_path)], capture_output=True, text=True)
        assert r.returncode == 2 and "임시 장부로 한다" in r.stderr, (cmd, r.stderr)
    # 임시 장부를 주면 그대로 돈다 (아래 sim 시험들이 전부 그 경로다)
    r = subprocess.run([sys.executable, str(RUN_WEAR), "uid", "--sim", "/bin/true"],
                       capture_output=True, text=True)
    assert "임시 장부" not in r.stderr                              # 읽기 명령은 장부를 안 쓴다


def test_accept_refuses_real_pe_without_flag(tmp_path):
    r = subprocess.run([sys.executable, str(RUN_WEAR), "accept", "--no-program", "--port", "/dev/null",
                        "--logdir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 3 and "--i-approve-real-pe" in r.stderr


def test_resume_reerases_and_prints_adopted_value(sim_bin, tmp_path):
    (tmp_path / "image.txt").write_text(f"fill {1002 * 4096 + 0x10:#x} 16 0x7F\n")
    r, pe = _run(["resume", "--host-log-max", "36", "--session", "1758412900", "--base-sector", "1000",
                  "--sim-image", str(tmp_path / "image.txt")], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "판정 normal 채택값 36" in out and "reerase ok=1" in out and "재확인 잔류 0" in out
    assert "마모 섹터 1000~1006" in out                           # resume 도 어느 자리를 본 건지 남긴다
    assert "accept --base-sector 1000 --cycle 36 --delta <n> --i-approve-real-pe" in out
    assert "| 1002 | ±1 | run_wear resume (session 1758412900) | reerase · ±1 |" in pe.read_text().splitlines()[-1]
    assert "WEAR START" not in (tmp_path / "logs" / "1758412900" / "commands.txt").read_text()   # START 는 안 보낸다
    assert (tmp_path / "logs" / "1758412900" / "R.txt").read_text().count("kind=reerase") == 1


def test_status_halt_tally_uid_on_sim(sim_bin, tmp_path):
    for cmd, want in [("status", "cycle=0 state=idle"), ("uid", f"uid={CHIP01_UID} 등록부=chip01"),
                      ("tally", "tally_a=0 tally_b=0"), ("dump", "copy 1: 0x00 0개")]:
        r, _ = _run([cmd], tmp_path, sim_bin)
        assert r.returncode == 0 and want in r.stdout, (cmd, r.stdout, r.stderr)
    r, _ = _run(["halt"], tmp_path, sim_bin)                  # idle 에서 halt 는 E_STATE
    assert r.returncode != 0 and "E_STATE" in r.stdout + r.stderr


def test_gcc_absent_is_reported_not_hidden():
    assert shutil.which("gcc"), "gcc 가 없으면 sim 케이스는 skip 되고 그 사실이 보고서에 적힌다"
