"""S-1 §13 A·C 와 S-4 §4 경계 오용. 정상 엔진이 채점표를 통과하는가."""

import pytest

import harness as H
import mock_engine as me


@pytest.fixture(scope="module")
def clean():
    return H.run()


@pytest.mark.parametrize("item", list(H.ACCEPTANCE))
def test_acceptance_item(clean, item):
    H.ACCEPTANCE[item](clean)


# ── S-4 §4 경계 오용 — 가짜 엔진 없이 직접 두드린다 ───────────────────────
@pytest.mark.parametrize("kwargs, why", [
    (dict(base_sector=0, n_sectors=0), "n_sectors=0"),
    (dict(base_sector=510, n_sectors=7), "tally 섹터 512 침범"),
    (dict(base_sector=1530, n_sectors=8), "tally 섹터 1,536 침범"),
    (dict(base_sector=2045, n_sectors=7), "주소 범위 초과"),
    (dict(base_sector=0, n_sectors=7, cycles=409_700), "tally 용량 초과"),
])
def test_rejects(kwargs, why):
    eng = me.MockEngine(me.Chip(), me.Link())
    kwargs.setdefault("cycles", 100)
    with pytest.raises(ValueError, match="REJECT"):
        eng.wear_start(pattern=0x00, **kwargs)


def test_reject_restart_while_running():
    """`[D29-7]` — 한 wear 그룹 안에서 다시 시작할 수 없다."""
    eng = me.MockEngine(me.Chip(), me.Link())
    eng.wear_start(0, 7, 0x00, 100)
    eng.state = "running"
    with pytest.raises(ValueError, match="REJECT"):
        eng.wear_start(0, 7, 0x00, 100)


def test_uid_matches_registry():
    """A7 — mock 에서는 고정값 대조만. 실칩에서 등록부와 맞춘다."""
    assert me.MockEngine(me.Chip(), me.Link()).uid_read() == "D1654CB09B352233"


def test_reject_new_run_on_dirty_tally():
    """§8.1 초기화가 안 돌면 X축이 앞선 채로 6일이 간다.

    TB 인수 시험이 tally 에 `0x00` 을 남기고 가므로, 실험 개시가 그것을 소거하지 않으면
    여기서 걸려야 한다. **자동으로 소거하지 않는다** — 재개를 신규로 착각하면
    X축이 통째로 날아간다.
    """
    chip = me.Chip()
    me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)   # TB 인수 시험
    with pytest.raises(ValueError, match="초기화 미실행"):
        me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)

    for copy in chip.tally:                                       # §8.1 초기화
        copy[:] = b"\xff" * me.TALLY_BYTES
    me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)    # 이제 통과
