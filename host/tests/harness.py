"""채점표 본체 — `docs/spec/s4.blackbox_tb.md` §2 의 항목을 함수 하나씩으로 옮긴다.

검사를 테스트 함수가 아니라 **평범한 함수**로 둔 이유는 §7 T6 때문이다. 같은 검사를
정상 엔진에는 통과시키고 버그 심은 엔진에는 **실패시켜 봐야** 채점표가 살아 있다고 말할 수
있다. 테스트 안에 박아 두면 그 반대 방향을 부를 수 없다.
"""

from dataclasses import dataclass

import mock_engine as me
import host_side as hs


@dataclass
class Result:
    chip: me.Chip
    link: me.Link
    log: hs.WearLog
    cycle: int
    state: str
    cut: bool
    engine: object


DEFAULT_CUT = 37          # "power_cut" 을 이름으로 줄 때 쓰는 기본 차단 시점
OVERFLOW_CAP = 4096       # "buffer_overflow" 를 이름으로 줄 때의 링크 용량


def run(cycles=100, faults=frozenset(), bugs=frozenset(), cut_at=None,
        cut_phase="between", capacity=None, chip=None):
    """100사이클 시험 1회. 전원이 끊기면 거기까지의 결과를 돌려준다.

    `power_cut`·`buffer_overflow`·`link_drop` 은 이름으로 줘도 동작한다 — S-4 §3 의
    목록과 실제 케이스가 어긋나지 않게 하려는 것이다 (T2).
    """
    faults = set(faults)
    if "power_cut" in faults and cut_at is None:
        cut_at = DEFAULT_CUT
    if "buffer_overflow" in faults and capacity is None:
        capacity = OVERFLOW_CAP
    chip = chip or me.Chip()
    link = me.Link(faults=faults, capacity=capacity)
    eng = me.MockEngine(chip, link, faults=faults, bugs=bugs,
                        cut_at=cut_at, cut_phase=cut_phase)
    cut = False
    try:
        if "link_drop" in faults:          # 중간 구간만 끊었다가 다시 붙인다
            eng.wear_start(0, 7, 0x00, cycles // 3)
            link.set_open(False)
            eng.state = "running"; eng._run(cycles // 3)
            link.set_open(True)
            eng.state = "running"; eng._run(cycles - 2 * (cycles // 3))
            eng.state = "checkpoint_due"
        else:
            eng.wear_start(0, 7, 0x00, cycles)
    except me.PowerCut:
        cut = True
    log = hs.WearLog()
    log.feed(link.drain())
    return Result(chip, link, log, eng.cycle, eng.state, cut, eng)


# ── S-1 §13 A ─────────────────────────────────────────────────────────────
def check_A1(r, n=100):
    assert r.cycle == n, f"A1 카운터 {r.cycle} != {n}"


def check_A2(r, n=100):
    assert len(r.log.a) == n * 7, f"A2 사이클 로그 {len(r.log.a)}행 != {n * 7}"


def check_A3(r, n=100):
    want = n // me.CHECK_PERIOD
    assert len(r.log.b) == want, f"A3 무결성 로그 {len(r.log.b)}행 != {want}"


def check_A4(r, n=100):
    want = n // me.TALLY_STRIDE
    for i, dump in enumerate(r.engine.tally_dump()):
        got = dump.count(0x00)
        assert got == want, f"A4 tally 벌{i} 0x00 {got}개 != {want}"


def check_A5(r, n=100):
    """네 경로가 같은 값을 말하나. 인수 기준의 심장이다."""
    counter, _, _ = r.engine.wear_status()
    a_rows = len(r.log.a) / 7
    b_cycle = r.log.b[-1]["cycle"] if r.log.b else None
    ta, tb, mismatch = r.engine.tally_read()
    assert not mismatch, f"A5 tally 2벌 불일치 {ta} vs {tb}"
    paths = {"카운터": counter, "A행수÷7": a_rows, "B의 cycle": b_cycle, "tally": ta}
    assert all(v == n for v in paths.values()), f"A5 경로 불일치 {paths}"


def check_C(r):
    """측정 경로 연결 — 호스트가 스윕을 걸 시점을 알 수 있나."""
    assert r.state == "checkpoint_due", f"C state={r.state}, 호스트가 스윕 시점을 모른다"


def check_resume_is_raw(r):
    """제안-5 — 엔진이 채택하거나 불일치를 가리면 안 된다 (`pe_engine.md` §2.1)."""
    a, b, mism = r.engine.tally_read()
    info = r.engine.wear_resume()
    assert (info.tally_a, info.tally_b, info.mismatch) == (a, b, mism), \
        "wear_resume 이 tally 를 가공했다 — 「큰 쪽 채택」은 호스트 몫이다"


ACCEPTANCE = {"A1": check_A1, "A2": check_A2, "A3": check_A3,
              "A4": check_A4, "A5": check_A5, "C": check_C,
              "resume": check_resume_is_raw}
