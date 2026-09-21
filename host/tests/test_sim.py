"""C 엔진(`ps/src/flash_wear.c`)을 실칩 없이 같은 채점표로 잰다 — 호스트 시뮬레이션.

fixture 가 `ps/sim/build_sim.sh` 로 `build/sim/flash_wear_sim` 을 만들고 파이프로 띄운다. 어댑터
(`host/run/wear_link.py`)를 거치므로 명령·응답·행 문법(S-4 §5.2)까지 실제 문자열로 두드린다.
고장·버그 주입은 mock 전용이다 — 여기서는 fake NOR 의 초기 이미지로 tally 마크·잔류 비트만 심는다.

프로세스를 다시 띄우는 것이 보드 리셋이다 (`WEAR_FAKE_STATE` 로 칩만 남긴다) — 엔진이 무상태인지를
J 와 복구 경로가 그것으로 본다.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import harness as H
import host_side as hs
import mock_engine as me

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "run"))
import wear_link as wl                                       # noqa: E402

TB_BASE, N = 1000, 7                                          # S-4 §9 TB 전용 마모 영역
TALLY_ADDR = {0: 512 * 4096, 1: 1536 * 4096}
# `sim_bin` fixture 는 conftest.py — gcc 가 없으면 skip 한다


class Sim:
    """엔진 프로세스 하나 = 부팅 하나. `restart()` 가 보드 리셋이다 (칩은 state 파일로 남는다)."""

    def __init__(self, sim_bin, tmp_path, image=None, stuck_se=None):
        self.bin, self.dir = sim_bin, tmp_path
        self.trace = tmp_path / "trace.txt"
        self.state = tmp_path / "chip.bin"
        self.env = dict(os.environ, WEAR_FAKE_TRACE=str(self.trace), WEAR_FAKE_STATE=str(self.state))
        if image:
            (tmp_path / "image.txt").write_text("\n".join(image) + "\n")
            self.env["WEAR_FAKE_IMAGE"] = str(tmp_path / "image.txt")
        if stuck_se is not None:
            self.env["WEAR_FAKE_STUCK_SE"] = str(stuck_se)
        self.log = hs.WearLog()
        self.link = None
        self.restart()

    def restart(self):
        if self.link:
            self.link.close()
        env = dict(self.env)
        if self.state.exists():
            env.pop("WEAR_FAKE_IMAGE", None)                  # 이미지는 첫 부팅에만
        self.link = wl.WearLink(wl.PipeTransport([str(self.bin)], env=env), log=self.log)
        return self.link

    def close(self):
        if self.link:
            self.link.close()
            self.link = None

    def pe_sectors(self):
        """fake 가 남긴 P/E 자취 — (소거 섹터 집합, 프로그램 섹터 집합)."""
        se, pp = set(), set()
        for ln in self.trace.read_text().splitlines():
            op, a, *_ = ln.split()
            (se if op == "SE" else pp).add(int(a) if op == "SE" else int(a) // 4096)
        return se, pp

    def result(self, base=TB_BASE, n=N):
        c, s, _, _ = self.link.wear_status()
        return H.Result(None, None, self.log, c, s, False, self.link, base=base, n_sectors=n)


def start(link, cycle, delta, base=TB_BASE, n=N):
    link.wear_start(base, n, 0x00, cycle, delta, me.SESSION)


def tally_mark(count, copies=(0, 1)):
    """tally 두 벌의 앞 count 바이트에 0x00 — 100×count 사이클을 돈 칩."""
    return [f"fill {TALLY_ADDR[c]:#x} {count} 0x00" for c in copies]


# ── 100사이클 · A1~A5 · A7 · C · probe · resume ──────────────────────────
def test_sim_100_cycles_scores(sim_bin, tmp_path):
    sim = Sim(sim_bin, tmp_path)
    try:
        assert sim.link.wear_status() == (0, "idle", False, "")
        start(sim.link, 0, 100)
        cycle, state, _, _ = sim.link.wait_stopped()
        assert (cycle, state) == (100, "checkpoint_due")
        r = sim.result()
        for item in ("A1", "A2", "A3", "A4", "A5", "A7", "C", "probe", "resume"):
            H.SCORE[item](r)
        assert sim.log.rejected == [], sim.log.rejected[:3]
        h = sim.log.h[0]
        assert (h["session"], h["cycle"], h["delta"], h["base_sector"], h["n_sectors"]) == \
            (me.SESSION, 0, 100, TB_BASE, N)
        rev = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        assert h["git_rev"] == rev, "git_rev 가 빌드 시점 HEAD 가 아니다"
        assert sim.log.b[0]["die_temp_mc"] is None and sim.log.b[0]["uid_ok"] == 1
        se, pp = sim.pe_sectors()                                   # P/E 주소 전부 지정 범위 안
        assert se == set(range(TB_BASE, TB_BASE + N))
        assert pp == set(range(TB_BASE, TB_BASE + N)) | {512, 1536}
        a, b = sim.link.tally_dump()
        assert a.count(0) == 1 and b.count(0) == 1 and len(a) == len(b) == 4096
    finally:
        sim.close()


# ── tally 소거 — 경계 10 (S-1 §8.1 초기화) ────────────────────────────────
def test_sim_tally_erase_locks(sim_bin, tmp_path):
    sim = Sim(sim_bin, tmp_path)
    try:
        start(sim.link, 0, 100)
        assert sim.link.wait_stopped()[:2] == (100, "checkpoint_due")
        with pytest.raises(hs.Reject, match="E_STATE"):            # idle 이 아니다
            sim.link.tally_erase(me.REGISTRY_UID)
        sim.restart()                                               # 리셋 = idle
        with pytest.raises(hs.Reject, match="E_RANGE"):            # 길이가 아니다
            sim.link.tally_erase("ABC")
        with pytest.raises(hs.Reject, match="E_UID"):              # 다른 칩의 UID
            sim.link.tally_erase("0000000000000000")
        assert sim.link.tally_read()[:2] == (100, 100)              # 거부는 거부로 끝났다
        with pytest.raises(hs.Reject, match="E_DIRTY"):
            start(sim.link, 0, 10)
        r = sim.link.tally_erase(me.REGISTRY_UID.lower())           # 소문자도 같은 UID
        assert (r.count_a, r.count_b, r.clean) == (100, 100, True)   # t_erase_us 는 sim 에선 0 일 수 있다 (시계가 가짜)
        assert sim.link.tally_read() == (0, 0, False)
        a, b = sim.link.tally_dump()
        assert a == b == b"\xff" * 4096
        se, _ = sim.pe_sectors()
        assert se == set(range(TB_BASE, TB_BASE + N)) | {512, 1536}   # 지운 것은 tally 두 섹터뿐
        start(sim.link, 0, 10)                                      # 자물쇠가 열렸다
        assert sim.link.wait_stopped()[:2] == (10, "checkpoint_due")
    finally:
        sim.close()


# ── J — 두 구간 + 리셋 ─────────────────────────────────────────────────
def test_sim_J_split_across_reset(sim_bin, tmp_path):
    sim = Sim(sim_bin, tmp_path)
    try:
        start(sim.link, 0, H.SPLIT)
        assert sim.link.wait_stopped()[:2] == (H.SPLIT, "checkpoint_due")
        sim.restart()                                               # 체크포인트 = 리셋
        assert sim.link.wear_status()[:2] == (0, "idle")            # 무상태 — 리셋 뒤 0
        start(sim.link, H.SPLIT, 100 - H.SPLIT)
        sim.link.wait_stopped()
        H.check_J(sim.result())
    finally:
        sim.close()


# ── 거부 12종 — 어댑터 경유 ───────────────────────────────────────────────
@pytest.mark.parametrize("code, kwargs", [
    ("E_NSECT0",        dict(base=0, n=0)),
    ("E_RANGE",         dict(base=2045, n=7)),
    ("E_TALLY_OVERLAP", dict(base=510, n=7)),
    ("E_CTRL_OVERLAP",  dict(base=7, n=7)),
    ("E_CTRL_OVERLAP",  dict(base=2041, n=7)),
    ("E_CAP",           dict(cycle=409_600, delta=1)),
])
def test_sim_rejects_args(sim_bin, tmp_path, code, kwargs):
    sim = Sim(sim_bin, tmp_path)
    try:
        kw = dict(base=TB_BASE, n=N, cycle=0, delta=1); kw.update(kwargs)
        with pytest.raises(hs.Reject) as e:
            start(sim.link, kw["cycle"], kw["delta"], kw["base"], kw["n"])
        assert e.value.code == code
        assert sim.link.wear_status() == (0, "idle", False, code)  # last_reject · 상태 불변
        assert not sim.trace.exists() or sim.trace.read_text() == ""   # 플래시를 만지지 않았다
    finally:
        sim.close()


def test_sim_rejects_dirty_and_cycle(sim_bin, tmp_path):
    """tally 에 마크 1개(=100사이클)인 칩 — `cycle=0` 은 `E_DIRTY`, d 규칙 밖은 `E_CYCLE`, 안쪽은 통과."""
    sim = Sim(sim_bin, tmp_path, image=tally_mark(1))
    try:
        with pytest.raises(hs.Reject) as e:
            start(sim.link, 0, 1)
        assert e.value.code == "E_DIRTY"
        for bad in (250, 50, 200):
            with pytest.raises(hs.Reject) as e:
                start(sim.link, bad, 1)
            assert e.value.code == "E_CYCLE"
        assert sim.link.tally_read() == (100, 100, False)
        start(sim.link, 147, 0)                                     # delta=0 — H 행만, 즉시 checkpoint_due
        assert sim.link.wait_stopped()[:2] == (147, "checkpoint_due")
        assert len(sim.log.h) == 1 and sim.log.h[0]["cycle"] == 147 and not sim.log.a
    finally:
        sim.close()


def test_sim_half_written_tally_byte(sim_bin, tmp_path):
    """쓰다 만 바이트(0x0F)는 마크다 — `E_DIRTY`. RESUME 은 그것을 `next_byte` 로 되돌린다."""
    sim = Sim(sim_bin, tmp_path, image=[f"{TALLY_ADDR[0]:#x} 0x0F", f"{TALLY_ADDR[1]:#x} 0x0F"])
    try:
        with pytest.raises(hs.Reject) as e:
            start(sim.link, 0, 1)
        assert e.value.code == "E_DIRTY"
        info = sim.link.wear_resume()
        assert info == hs.ResumeInfo(0, 0, False, 0x0F, True)
        assert hs.decide_resume(info, 147) == (hs.UNCERTAIN, 147)
    finally:
        sim.close()


def test_sim_rejects_sum_dup_state(sim_bin, tmp_path):
    """`E_SUM`·`E_DUP` 은 문자열에서만 생긴다 — 원문을 직접 보낸다. `E_STATE`·`E_RUNNING` 도 같이."""
    sim = Sim(sim_bin, tmp_path)
    link = sim.link
    try:
        line = hs.format_cmd("START", 1, base=TB_BASE, n_sectors=N, pattern=0x00, cycle=0,
                             delta=300, session=me.SESSION)
        bad = line.replace("delta=300", "delta=900")                # 숫자 한 자리 반전
        link.t.write((bad + "\n").encode())
        assert link._wait_response(1, 5).fields["code"] == "E_SUM"
        link.t.write((line + "\n").encode())                        # 같은 req 를 바르게 — E_SUM 은 req 를 안 먹는다
        assert link._wait_response(1, 5).kind == "OK"
        link.req = 1
        link.t.write((line + "\n").encode())                        # 재전송 — E_DUP, 재실행 없음
        assert link._wait_response(1, 5).fields["code"] == "E_DUP"
        with pytest.raises(hs.Reject) as e:                         # running 중 START
            start(link, 0, 1)
        assert e.value.code == "E_RUNNING"
        with pytest.raises(hs.Reject) as e:                         # running 중 나머지
            link.blank_check(TB_BASE, N)
        assert e.value.code == "E_STATE"
        assert link.wear_status()[1] == "running"                   # STATUS 는 읽기 전용으로 답한다
        link.halt()
        cycle, state, _, _ = link.wait_stopped()
        assert state == "halted" and 0 < cycle < 300
        assert len(sim.log.a) == cycle * 7, "재전송된 START 가 두 번 실행됐거나 행이 샜다"
        with pytest.raises(hs.Reject) as e:                         # recovering 밖의 reerase
            link.reerase(TB_BASE, N)
        assert e.value.code == "E_STATE"
        with pytest.raises(hs.Reject) as e:                         # running 밖의 halt
            link.halt()
        assert e.value.code == "E_STATE"
    finally:
        sim.close()


# ── HALT → START(cycle=마지막 완료값) ───────────────────────────────────
def test_sim_halt_then_continue(sim_bin, tmp_path):
    sim = Sim(sim_bin, tmp_path)
    try:
        start(sim.link, 0, 100_000)
        sim.link.pump(0.05)
        sim.link.halt()
        cycle, state, _, _ = sim.link.wait_stopped()
        assert state == "halted" and cycle >= 1
        halts = [r for r in sim.log.r if r["kind"] == "halt"]
        assert len(halts) == 1 and halts[0]["cycle"] == cycle and halts[0]["ok"] == 1
        assert len(sim.log.a) == cycle * 7
        assert cycle < 100, "HALT 가 100사이클 안에 안 먹혔다"
        sim.restart()                                               # 이어 가는 길 — START(cycle=마지막 완료값)
        start(sim.link, cycle, 100 - cycle)
        sim.link.wait_stopped()
        r = sim.result()
        for item in ("A1", "A2", "A3", "A4", "A5"):
            H.SCORE[item](r)
    finally:
        sim.close()


# ── 복구 — recovering → blank_check → reerase → START(cycle=채택값) ───────
def test_sim_recovering_reerase(sim_bin, tmp_path):
    """소거 중 차단을 이미지로 심는다 — 섹터 1,002 에 16바이트 잔류(0x7F = 비트 7 만 0).
    §8.3 을 `host_side.resume()` 그대로 밟고 채택값으로 이어 돈다 (S-1 §13 B 의 두 번째 조건)."""
    sim = Sim(sim_bin, tmp_path, image=[f"fill {1002 * 4096 + 0x10:#x} 16 0x7F"])
    try:
        link = sim.link
        o = hs.resume(link, host_log_max=36, base_sector=TB_BASE, n_sectors=N)
        assert (o.verdict, o.restored, o.residual_before, o.reerased, o.residual_after) == \
            (hs.NORMAL, 36, 16, True, 0)
        rows = [r for r in sim.log.r if r["kind"] == "reerase"]
        assert len(rows) == 1 and (rows[0]["sector"], rows[0]["op"], rows[0]["ok"]) == (1002, "erase", 1)
        assert (rows[0]["resid_before"], rows[0]["resid_after"]) == (16, 0)
        se, _ = sim.pe_sectors()
        assert se == {1002}, "잔류가 없는 섹터를 지웠다"
        bc = link.blank_check(TB_BASE, N)                          # recovering 에서 다시 읽으면 0
        assert bc.erase_residual_bits == 0 and bc.program_fail_bits == N * 16 * 256 * 8
        with pytest.raises(hs.Reject) as e:                         # 잔류가 없으면 재소거는 E_STATE
            link.reerase(TB_BASE, N)
        assert e.value.code == "E_STATE"
        start(link, o.restored, 4)                                  # §8.3 6
        assert link.wait_stopped()[:2] == (40, "checkpoint_due")
        assert [a["cycle"] for a in sim.log.a[::7]] == [37, 38, 39, 40]
    finally:
        sim.close()


def test_sim_blank_check_addrs(sim_bin, tmp_path):
    """BLANK 의 주소는 잔류 기준 · base 상대 페이지 · 최대 64개 + 총 개수 · 최악 페이지 (§3 #9)."""
    sim = Sim(sim_bin, tmp_path, image=[f"fill {1001 * 4096:#x} 70 0xFE",         # 페이지 16, 70비트
                                         f"{1005 * 4096 + 3 * 256 + 9:#x} 0x00"])   # 페이지 83 바이트 9, 8비트
    try:
        bc = sim.link.blank_check(TB_BASE, N)
        assert bc.erase_residual_bits == 78 and bc.addr_count == 78
        assert len(bc.addrs) == 64 and bc.addrs[0] == (16, 0, 0)
        assert (bc.worst_page_idx, bc.worst_page_bits) == (16, 70)
        assert bc.program_fail_bits == N * 16 * 256 * 8 - 78
    finally:
        sim.close()


# ── 정지 사유 — WIP 타임아웃 (§10) ─────────────────────────────────────
def test_sim_wip_timeout_stops_with_R_row(sim_bin, tmp_path):
    sim = Sim(sim_bin, tmp_path, stuck_se=1003)
    try:
        start(sim.link, 0, 5)
        cycle, state, _, _ = sim.link.wait_stopped(timeout=30)
        assert (cycle, state) == (0, "error")
        row = sim.log.r[-1]
        assert (row["kind"], row["op"], row["sector"], row["ok"]) == ("wip_timeout", "erase", 1003, 0)
        assert row["t_us"] >= 2_000_000
        assert sim.log.a == [], "끝나지 않은 사이클의 A 행이 나갔다"
        start(sim.link, 0, 0)                                       # error 에서도 START 는 받는다 (§3 #4)
    finally:
        sim.close()
