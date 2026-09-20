"""S-1 §13 A·B·C · S-4 §2 J 와 S-4 §4 경계 오용. 정상 엔진이 채점표를 통과하는가."""

from pathlib import Path

import pytest

import harness as H
import host_side as hs
import mock_engine as me

# S-4 §2 표에서 mock 열이 `O` 인 항목. 여기서 하나가 조용히 빠지면 T1 이 무너진다
SPEC_MOCK_COLUMN = {"A1", "A2", "A3", "A4", "A5", "A7", "B", "C", "J"}


def _engine(chip=None, **kw):
    return me.MockEngine(chip or me.Chip(), me.Link(), **kw)


def _start(eng, base=0, n=7, cycle=0, delta=100):
    eng.wear_start(base, n, 0x00, cycle, delta, me.SESSION)


def corrupt_sum(line):
    """체크섬의 마지막 자리를 반드시 다른 값으로."""
    return line[:-1] + ("0" if line[-1] != "0" else "1")


@pytest.mark.parametrize("item", sorted(H.SCORE))
def test_acceptance_item(item):
    H.score(item)


def test_score_table_covers_spec():
    """T1 집행 — §2 표의 항목이 채점표에서 빠지면 여기서 걸린다.

    A6(소거 시간)는 mock 이 못 본다. 그것 하나만 빠져 있어야 한다.
    """
    assert SPEC_MOCK_COLUMN <= set(H.SCORE), f"채점 없는 항목: {SPEC_MOCK_COLUMN - set(H.SCORE)}"
    assert "A6" not in H.SCORE, "A6 는 실칩 전용이다 (S-4 §2)"


# ── S-4 §4 경계 오용 — 가짜 엔진 없이 직접 두드린다 (열한 줄, T3) ─────────
@pytest.mark.parametrize("code, kwargs", [
    ("E_NSECT0",        dict(base=0, n=0)),
    ("E_TALLY_OVERLAP", dict(base=510, n=7)),
    ("E_TALLY_OVERLAP", dict(base=1530, n=8)),
    ("E_RANGE",         dict(base=2045, n=7)),
    ("E_CAP",           dict(base=0, n=7, delta=409_700)),
    ("E_CAP",           dict(base=0, n=7, cycle=409_600, delta=1)),
    ("E_CTRL_OVERLAP",  dict(base=7, n=7)),          # 근접 대조군
    ("E_CTRL_OVERLAP",  dict(base=1, n=7)),          # 마모 그룹이 근접에 한 섹터 걸침
    ("E_CTRL_OVERLAP",  dict(base=2041, n=7)),       # 원격 대조군
    ("E_CTRL_OVERLAP",  dict(base=2035, n=7)),       # 원격에 한 섹터 걸침
])
def test_rejects(code, kwargs):
    """거부는 **코드로** 갈려야 한다 — 사유 문자열만으로는 무엇을 거부했는지 못 잰다."""
    eng = _engine()
    with pytest.raises(me.Reject) as e:
        _start(eng, **kwargs)
    assert e.value.code == code
    assert eng.chip.worn_cycles == 0, "거부인데 플래시를 만졌다"


def test_tb_area_and_pilot_area_are_accepted():
    """보호 범위의 음성 대조 — 파일럿 마모 0~6 과 TB 전용 1,000~1,006 은 통과한다 (S-4 §9)."""
    for base in (0, 1000):
        _start(_engine(), base=base, delta=1)


def test_reject_restart_while_running():
    """`[D29-7]` — 한 wear 그룹 안에서 다시 시작할 수 없다: `E_RUNNING`."""
    eng = _engine()
    _start(eng)
    eng.state = "running"
    with pytest.raises(me.Reject) as e:
        _start(eng)
    assert e.value.code == "E_RUNNING"


def test_reject_new_run_on_dirty_tally():
    """`E_DIRTY` — tally 에 마크가 있는데 `cycle=0` 이면 거부한다 (`[D44-10]`).

    TB 인수 시험이 tally 에 `0x00` 을 남기고 가므로, 실험 개시가 그것을 소거하지 않으면
    여기서 걸려야 한다. **자동으로 소거하지 않는다** — 재개를 신규로 착각하면
    X축이 통째로 날아간다. 마크가 있어도 `cycle=100` 으로 이어 돌리는 것은 받는다.
    """
    chip = me.Chip()
    _start(_engine(chip))                                # TB 인수 시험 — tally 에 1개
    with pytest.raises(me.Reject) as e:
        _start(_engine(chip))                            # cycle=0 신규 시작
    assert e.value.code == "E_DIRTY"
    chip.tally[1][1] = 0x0F                              # 쓰다 만 바이트도 마크다 (§3 #5)
    with pytest.raises(me.Reject) as e:
        _start(_engine(chip))
    assert e.value.code == "E_DIRTY"
    chip.tally[1][1] = 0xFF
    _start(_engine(chip), cycle=100, delta=1)            # 이어 돌리기는 통과

    for copy in chip.tally:                              # §8.1 초기화
        copy[:] = b"\xff" * me.TALLY_BYTES
    _start(_engine(chip))                                # 이제 신규도 통과


@pytest.mark.parametrize("cycle", [250, 50, 99, 200])
def test_reject_cycle_off_tally(cycle):
    """`E_CYCLE` — `d = cycle − tally×100` 이 `0 ≤ d < 100` 밖이면 거부 (§8.3 · `[D44-10]`).

    tally 100 에서 250(d=150)·50(d=−50)·99(d=−1)·200(d=100) 전부 밖이다.
    """
    chip = me.Chip()
    _start(_engine(chip))                                # tally = 100
    with pytest.raises(me.Reject) as e:
        _start(_engine(chip), cycle=cycle, delta=1)
    assert e.value.code == "E_CYCLE"
    for ok in (100, 147, 199):                           # 안쪽은 통과
        _start(_engine(me.Chip(tally=[bytearray(c) for c in chip.tally])), cycle=ok, delta=0)


def test_reject_bad_checksum_and_no_flash_command():
    """`E_SUM` — 명령 체크섬 불일치는 거부로 끝나고 **플래시 명령이 한 번도 나가지 않는다**
    (S-4 §4 마지막 문단). `delta=100` 의 한 자리를 뒤집어 `delta=900` 으로 보낸다."""
    eng = _engine()
    line = hs.format_cmd("START", 1, base=0, n_sectors=7, pattern=0x00, cycle=0,
                         delta=100, session=me.SESSION)
    bad = line.replace("delta=100", "delta=900")
    (resp,) = eng.command(bad)
    r = hs.parse_response(resp)
    assert (r.kind, r.fields["code"]) == ("REJECT", "E_SUM")
    assert eng.chip.worn_cycles == 0 and eng.wear_status()[:2] == (0, "idle")
    assert eng.wear_status()[3] == "E_SUM"               # last_reject


def test_reject_duplicate_req_is_not_reexecuted():
    """`E_DUP` — 같은 `req` 의 `wear_start` 가 두 번 오면 두 번째는 거부이고 재실행이 없다.
    「이전 결과 반환」이 아니다 — 호스트는 응답을 잃으면 `wear_status()` 로 확인한다."""
    eng = _engine()
    line = hs.format_cmd("START", 7, base=0, n_sectors=7, pattern=0x00, cycle=0,
                         delta=10, session=me.SESSION)
    (ok,) = eng.command(line)
    assert hs.parse_response(ok).kind == "OK"
    assert eng.chip.worn_cycles == 10
    (dup,) = eng.command(line)
    assert hs.parse_response(dup).fields["code"] == "E_DUP"
    assert eng.chip.worn_cycles == 10, "중복 명령이 재실행됐다 — X축이 밀린다"
    (older,) = eng.command(hs.format_cmd("STATUS", 3))    # req 가 뒤로 가도 E_DUP
    assert hs.parse_response(older).fields["code"] == "E_DUP"
    (later,) = eng.command(hs.format_cmd("STATUS", 8))
    assert hs.parse_response(later).fields["state"] == "checkpoint_due"


def test_reject_after_E_SUM_does_not_consume_req():
    """§3 #1 — `E_SUM` 은 `req` 를 믿을 수 없으므로 「처리」로 세지 않는다.
    같은 `req` 를 바르게 다시 보내면 통과한다. 다른 거부(`E_NSECT0`)는 처리로 센다."""
    eng = _engine()
    good = hs.format_cmd("STATUS", 5)
    assert hs.parse_response(eng.command(corrupt_sum(good))[0]).fields["code"] == "E_SUM"
    assert hs.parse_response(eng.command(good)[0]).kind == "OK"
    bad_args = hs.format_cmd("START", 6, base=0, n_sectors=0, pattern=0, cycle=0,
                             delta=1, session=me.SESSION)
    assert hs.parse_response(eng.command(bad_args)[0]).fields["code"] == "E_NSECT0"
    assert hs.parse_response(eng.command(hs.format_cmd("STATUS", 6))[0]).fields["code"] == "E_DUP"


@pytest.mark.parametrize("verb, state", [
    ("REERASE", "idle"), ("REERASE", "checkpoint_due"), ("REERASE", "halted"),
    ("HALT", "idle"), ("HALT", "checkpoint_due"),
])
def test_reject_wrong_state(verb, state):
    """`E_STATE` — `recovering` 밖의 `reerase` (`[D44-3]`) · `running` 밖의 `halt`."""
    eng = _engine()
    eng.state = state
    with pytest.raises(me.Reject) as e:
        if verb == "REERASE":
            eng.reerase(0, 7)
        else:
            eng.halt()
    assert e.value.code == "E_STATE"


def test_reerase_needs_recovering_and_a_residual_blank_check():
    """`recovering` 이어도 마지막 blank_check 가 잔류를 보지 않았으면 재소거는 `E_STATE` —
    잔류 없는 섹터를 지우는 것은 마모다."""
    eng = _engine()
    eng.wear_resume()
    assert eng.state == "recovering"
    with pytest.raises(me.Reject) as e:
        eng.reerase(0, 7)                                 # blank_check 없이
    assert e.value.code == "E_STATE"
    eng.blank_check(0, 7)                                 # 잔류 0
    with pytest.raises(me.Reject) as e:
        eng.reerase(0, 7)
    assert e.value.code == "E_STATE"
    assert eng.chip.worn_cycles == 0 and not eng.link.buf


def test_reject_priority_is_the_table_order():
    """§3 #2 — 여럿에 해당하면 앞의 코드. 체크섬이 틀린 `n_sectors=0` 은 `E_SUM`,
    `running` 중 `n_sectors=0` 은 `E_NSECT0`."""
    eng = _engine()
    line = hs.format_cmd("START", 1, base=0, n_sectors=0, pattern=0, cycle=0, delta=1,
                         session=me.SESSION)
    assert hs.parse_response(eng.command(corrupt_sum(line))[0]).fields["code"] == "E_SUM"
    eng.state = "running"
    assert hs.parse_response(eng.command(line)[0]).fields["code"] == "E_NSECT0"


def test_every_reject_has_a_case():
    """T3 집행 — §4 의 열한 줄과 거부 코드가 1:1 인가.

    목록에만 있고 케이스가 없으면 **거부한다고 적어 두고 안 재는 줄**이 생긴다.
    """
    src = (Path(__file__).parent / "test_acceptance.py").read_text(encoding="utf-8")
    missing = {c for c in me.REJECTS if f'"{c}"' not in src}
    assert not missing, f"케이스 없는 거부 코드: {sorted(missing)}"
    assert len(me.REJECTS) == 11


# ── HALT · 이어 돌리기 · R 행 ──────────────────────────────────────────────
def test_halt_stops_at_next_boundary_and_start_continues():
    """`[D44-4]` — HALT 는 다음 사이클 경계에서 멈추고 R `kind=halt` 를 남긴다.
    이어 가는 길은 `wear_start(cycle=마지막 완료값)` 이다. 채점표 항목이 아니라 케이스다."""
    r = H.run(halt_at=37)
    assert (r.state, r.cycle) == ("halted", 37)
    assert len(r.log.a) == 37 * 7 and len(r.log.r) == 1
    row = r.log.r[0]
    assert (row["kind"], row["cycle"], row["op"], row["ok"]) == ("halt", 37, "", 1)
    assert row["sector"] is None and row["t_us"] is None     # 쓰지 않는 필드는 빈 값

    eng = me.MockEngine(r.chip, r.link)                       # 이어서
    _start(eng, cycle=37, delta=63)
    r.log.feed(r.link.drain())
    r.cycle, r.state, r.engine = eng.cycle, eng.state, eng
    for check in (H.check_A1, H.check_A2, H.check_A3, H.check_A4, H.check_A5):
        check(r)


def test_R_row_round_trip_for_reerase():
    """R 행 — 재소거 사건 1건 1행. 카운터에도 tally 에도 더하지 않는다 (`[D44-6]`)."""
    r = H.resume_after(H.run(faults={"power_cut"}, cut_at=37, cut_phase="erase"))
    rows = [x for x in r.log.r if x["kind"] == "reerase"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["sector"], row["op"], row["ok"], row["resid_after"]) == (0, "erase", 1, 0)
    assert row["resid_before"] == me.PARTIAL_RESIDUAL_BITS
    assert r.chip.worn_cycles == 36 + H.CONT_DELTA           # 37번째는 끊겼다 — 재소거는 안 센다


def test_delta_zero_is_accepted():
    """§3 #13 — `delta=0` 은 H 행 1행 내고 즉시 `checkpoint_due`."""
    r = H.run(cycles=0)
    assert (r.state, r.cycle, len(r.log.h), len(r.log.a)) == ("checkpoint_due", 0, 1, 0)


def test_uid_matches_registry():
    """A7 의 경계 쪽 절반 — 로그 쪽 절반은 `check_A7` 이 본다."""
    assert _engine().uid_read() == me.REGISTRY_UID


def test_defect_addrs_round_trip():
    """§7 — 결함 주소는 최대 64개 + **총 개수**, phase 별로 두 벌 (`[D44-13]`)."""
    chip = me.Chip(defects=[(p, 3, 5) for p in range(70)])
    r = H.run(chip=chip)
    row = r.log.b[-1]
    for ph in ("p", "e"):
        assert row[f"{ph}_addr_count"] == 70              # 총 개수는 줄지 않는다
        assert len(row[f"{ph}_addrs"]) == 64              # 실은 주소는 64개까지
        assert row[f"{ph}_addrs"][0] == (0, 3, 5)
    assert row["die_temp_mc"] is None                     # XADC 미구현 — 빈 값


def test_header_row_returns_session_cycle_delta():
    """`[D44-5]` — H 행은 START 마다 1행이고 `session`·`cycle`·`delta` 를 되돌린다."""
    r = H.run_split()
    assert [(h["session"], h["cycle"], h["delta"]) for h in r.log.h] == \
        [(me.SESSION, 0, H.SPLIT), (me.SESSION, H.SPLIT, 100 - H.SPLIT)]


def test_command_strings_round_trip():
    """명령 문법의 왕복 — `format_cmd` 가 만든 것을 `parse_cmd` 가 그대로 읽는다 (S-4 §5.2)."""
    line = hs.format_cmd("START", 12, base=1000, n_sectors=7, pattern=0x00, cycle=300,
                         delta=345, session=me.SESSION)
    assert line.startswith("WEAR START base=1000 n_sectors=7 pattern=0x00 cycle=300 "
                           "delta=345 session=1758412800 req=12 sum=")
    c = hs.parse_cmd(line)
    assert (c.verb, c.req, c.sum_ok) == ("START", 12, True)
    assert c.args == dict(base=1000, n_sectors=7, pattern=0, cycle=300, delta=345,
                          session=me.SESSION)
    assert hs.format_cmd("HALT", 3).startswith("WEAR HALT req=3 sum=")
    eng = _engine()
    (ok,) = eng.command(hs.format_cmd("STATUS", 1))
    assert hs.parse_response(ok).fields == dict(cycle=0, state="idle", defect_seen=0,
                                                last_reject="")
    out = eng.command(hs.format_cmd("DUMP", 2))
    assert hs.parse_response(out[0]).kind == "OK" and len(out) == 65
    log = hs.WearLog()
    log.feed("\n".join(out[1:]).encode())
    assert len(log.d) == 64 and {d["copy"] for d in log.d} == {0, 1}
    assert all(d["hex"] == "ff" * 128 for d in log.d)
