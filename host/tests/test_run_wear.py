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


def test_judge_accept_passes_on_good_run():
    r, st, tally, dumps, uid = _mock_result()
    v = rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID)
    assert [i for i, _, _ in v] == ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "C"]
    assert all(ok for _, ok, _ in v), v


@pytest.mark.parametrize("bug, item", [("undercount", "A1"), ("drop_sector_rows", "A2"),
                                       ("drop_b_row", "A3"), ("tally_single", "A5"),
                                       ("uid_wrong", "A7")])
def test_judge_accept_fails_the_right_item(bug, item):
    r, st, tally, dumps, uid = _mock_result(bugs={bug})
    failed = {i for i, ok, _ in rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID) if not ok}
    assert item in failed


def test_judge_accept_C_needs_checkpoint_due():
    r, st, tally, dumps, uid = _mock_result()
    v = dict((i, ok) for i, ok, _ in rw.judge_accept(r.log, (100, "halted", False, ""), tally, dumps, uid, CHIP01_UID))
    assert v["C"] is False and v["A1"] is True


def test_judge_accept_A6_flags_slow_erase():
    r, st, tally, dumps, uid = _mock_result()
    r.log.a[3]["t_erase_us"] = 400_001
    v = dict((i, ok) for i, ok, _ in rw.judge_accept(r.log, st, tally, dumps, uid, CHIP01_UID))
    assert v["A6"] is False and v["A1"] is True


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
    assert rw.start_command(300, 345, 1758412800).startswith(
        "WEAR START base=1000 n_sectors=7 pattern=0x00 cycle=300 delta=345 session=1758412800 req=1 sum=")


def test_host_log_max_from_session_dir(tmp_path):
    (tmp_path / "A.txt").write_text(hs.PREFIX + hs.with_sum("A cycle=147 sector=1000 t_erase_us=1 t_program_us=2 ts=3") + "\n")
    assert rw.host_log_max_from(tmp_path) == 147


# ── sim 파이프로 끝까지 ────────────────────────────────────────────────────
CHIP_PE_DOC = ("# 이력\n\n## 이력\n\n"
               "| 일자 | 라벨 | UID | 섹터 범위 | P/E 증분 | 출처 | 비고 |\n"
               "| ---- | ---- | --- | --------- | -------- | ---- | ---- |\n"
               "| 2026-07-08 | chip01 | (미확보) | 0~127 | 미상(≥1) | flash_prep | 소급 불가 |\n")


def _run(args, tmp_path, sim_bin, extra_env=None):
    pe = tmp_path / "chip_pe.md"
    if not pe.exists():
        pe.write_text(CHIP_PE_DOC)
    cmd = [sys.executable, str(RUN_WEAR), *args, "--sim", str(sim_bin), "--no-program",
           "--logdir", str(tmp_path / "logs"), "--chip-pe", str(pe), "--sim-state", str(tmp_path / "chip.bin")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return r, pe


def test_accept_end_to_end_on_sim(sim_bin, tmp_path):
    r, pe = _run(["accept", "--session", "1758412800"], tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    d = tmp_path / "logs" / "1758412800"
    verdict = (d / "verdict.txt").read_text()
    assert verdict.count("PASS") == 8 and "FAIL" not in verdict, verdict
    assert len((d / "A.txt").read_text().splitlines()) == 700
    assert len((d / "B.txt").read_text().splitlines()) == 1 and (d / "H.txt").exists()
    assert "WEAR START base=1000 n_sectors=7 pattern=0x00 cycle=0 delta=100 session=1758412800" in (d / "commands.txt").read_text()
    tail = pe.read_text().splitlines()[-1]
    assert tail.startswith("| ") and "| chip01 | D1654CB09B352233 | 1000~1006 | +100 | run_wear accept (session 1758412800) |" in tail

    # 같은 칩에 다시 신규 시작 — E_DIRTY 로 막힌다 (tally 마크가 남아 있다)
    r2, _ = _run(["accept", "--session", "1758412801"], tmp_path, sim_bin)
    assert r2.returncode == 3 and "E_DIRTY" in r2.stderr
    # 이어 돌리기 — 사람이 채택값을 넣는다
    r3, _ = _run(["accept", "--session", "1758412802", "--cycle", "100", "--delta", "10"], tmp_path, sim_bin)
    assert r3.returncode == 1, r3.stdout                      # 110 은 100사이클 인수 기준이 아니다 — A3·A4 FAIL 이 정상
    assert "PASS  A1    카운터 110" in r3.stdout
    assert "| 1000~1006 | +10 |" in pe.read_text().splitlines()[-1]


def test_accept_refuses_real_pe_without_flag(tmp_path):
    r = subprocess.run([sys.executable, str(RUN_WEAR), "accept", "--no-program", "--port", "/dev/null",
                        "--logdir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 3 and "--i-approve-real-pe" in r.stderr


def test_resume_reerases_and_prints_adopted_value(sim_bin, tmp_path):
    (tmp_path / "image.txt").write_text(f"fill {1002 * 4096 + 0x10:#x} 16 0x7F\n")
    r, pe = _run(["resume", "--host-log-max", "36", "--session", "1758412900", "--sim-image", str(tmp_path / "image.txt")],
                 tmp_path, sim_bin)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "판정 normal 채택값 36" in out and "reerase ok=1" in out and "재확인 잔류 0" in out
    assert "accept --cycle 36 --delta <n> --i-approve-real-pe" in out
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
