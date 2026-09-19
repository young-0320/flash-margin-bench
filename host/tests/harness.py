"""채점표 본체 — `docs/spec/s4.blackbox_tb.md` §2 의 항목을 함수 하나씩으로 옮긴다.

검사를 테스트 함수가 아니라 **평범한 함수**로 둔 이유는 §7 T6 때문이다. 같은 검사를
정상 엔진에는 통과시키고 버그 심은 엔진에는 **실패시켜 봐야** 채점표가 살아 있다고 말할 수
있다. 테스트 안에 박아 두면 그 반대 방향을 부를 수 없다.

항목마다 필요한 **실행 모양이 다르다** (B 는 전원을 끊고 재개까지 가야 한다). 그래서
실행과 채점을 `score()` 한 자리에 묶는다 — T6 가 같은 항목을 두 번 부르기 때문이다.
"""

from dataclasses import dataclass, field

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
    bugs: set = field(default_factory=set)
    resume: object = None      # 재개까지 간 경우에만 채워진다 (§13 B)


DEFAULT_CUT = 37          # "power_cut" 을 이름으로 줄 때 쓰는 기본 차단 시점
OVERFLOW_CAP = 4096       # "buffer_overflow" 를 이름으로 줄 때의 링크 용량


def run(cycles=100, faults=frozenset(), bugs=frozenset(), cut_at=None,
        cut_phase="between", capacity=None, chip=None, verify=True):
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
    log = hs.WearLog(verify=verify)
    log.feed(link.drain())
    return Result(chip, link, log, eng.cycle, eng.state, cut, eng, set(bugs))


def resume_after(r):
    """전원을 다시 넣는다 — 새 엔진 객체를 같은 칩에 붙이고 §8.3 을 밟는다.

    엔진 객체는 차단으로 죽었고 남은 것은 칩과 호스트가 받아 둔 로그뿐이다.
    버그는 구현의 성질이므로 새 객체에도 그대로 따라온다.
    """
    eng = me.MockEngine(r.chip, me.Link(), bugs=r.bugs)
    r.resume = hs.resume(eng, r.log.max_cycle)
    return r


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


def check_A7(r, n=100):
    """A7 — **로그의** `chip_id` 가 등록부와 일치. 경계 7 만 보면 못 잡는다."""
    ids = {h["chip_id"] for h in r.log.h}
    assert ids == {me.REGISTRY_UID}, f"A7 로그 chip_id {ids or '없음'} != 등록부"
    assert r.engine.uid_read() == me.REGISTRY_UID, "A7 경계 7 의 UID 가 등록부와 다르다"


# ── S-1 §13 B ─────────────────────────────────────────────────────────────
def check_B(r, n=100):
    """§13 B 는 **조건이 둘이다.**

    ① 복원 카운트와 실제 진행의 차이 ≤ 100
    ② **소거 중 차단이면 부분 소거가 blank check 에 잡히고 재소거 후 정상 진행**
    """
    o = r.resume
    assert o is not None, "B 재개를 밟지 않았다"
    assert o.verdict != hs.HALT_CALL_HUMAN, f"B 정상 차단인데 사람을 불렀다 ({o.verdict})"
    assert abs(o.restored - r.chip.worn_cycles) <= 100, (
        f"B 복원 {o.restored} vs 실제 {r.chip.worn_cycles}")
    if o.residual_before:
        assert o.reerased and o.residual_after == 0, (
            f"B 부분 소거 {o.residual_before}비트가 재소거되지 않았다 "
            f"(재소거={o.reerased}, 남은 잔류={o.residual_after})")


# ── S-1 §13 C ─────────────────────────────────────────────────────────────
def check_C(r, n=100):
    """측정 경로 연결 — 호스트가 스윕을 걸 시점을 알 수 있나.

    §13 C 의 나머지(`valid=1 reason=complete` · CSV 파라미터 · `sweep_csv` 일치)는
    **호스트 도구(§5)** 가 내는 것이라 이 경계 위에 없다.
    """
    assert r.state == "checkpoint_due", f"C state={r.state}, 호스트가 스윕 시점을 모른다"


def check_probe(r, n=100):
    """**양성 대조** — 세는 경로가 살아 있나 (제안-10 · 로그 42 §7).

    체크포인트에서 엔진은 멈춰 있고 마지막 동작은 소거였다. 그러니 지금 `blank_check` 를
    부르면 `0xFF` 를 `0x00` 과 대조하는 것이라 **전량이 나와야 한다.** 여기서 `0` 이 나오면
    그 경로는 죽어 있는 것이다 — 신품 100사이클에서는 정답도 `0` 이라 **B 로그만 봐서는
    죽은 것과 멀쩡한 것이 같아 보인다.** 정답에서 제일 먼 값이 나오는 자리를 일부러 고른다.
    """
    total = 7 * me.SECTOR_PAGES * me.PAGE_BYTES * 8
    bc = r.engine.blank_check(0, 7)
    assert bc.erase_residual_bits == 0, f"probe 소거 직후인데 잔류 {bc.erase_residual_bits}"
    assert bc.program_fail_bits == total, (
        f"probe program_fail_bits {bc.program_fail_bits} != {total} — 세는 경로가 죽었다")
    assert bc.erase_residual_bits + bc.program_fail_bits == total, "probe 합 불변식 깨짐"


def check_resume_is_raw(r, n=100):
    """제안-5 — 엔진이 채택하거나 불일치를 가리면 안 된다 (`pe_engine.md` §2.1)."""
    a, b, mism = r.engine.tally_read()
    info = r.engine.wear_resume()
    assert (info.tally_a, info.tally_b, info.mismatch) == (a, b, mism), \
        "wear_resume 이 tally 를 가공했다 — 「큰 쪽 채택」은 호스트 몫이다"


SCORE = {"A1": check_A1, "A2": check_A2, "A3": check_A3, "A4": check_A4,
         "A5": check_A5, "A7": check_A7, "B": check_B, "C": check_C,
         "resume": check_resume_is_raw, "probe": check_probe}


def score(item, cycles=100, bugs=frozenset()):
    """채점 항목 하나를 실행하고 잰다. B 만 실행 모양이 다르다 — 끊고 재개해야 한다."""
    if item == "B":
        r = resume_after(run(cycles=cycles, bugs=bugs, faults={"power_cut"},
                             cut_at=DEFAULT_CUT, cut_phase="erase"))
    else:
        r = run(cycles=cycles, bugs=bugs)
    SCORE[item](r, n=cycles)
    return r
