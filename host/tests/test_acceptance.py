"""S-1 §13 A·B·C 와 S-4 §4 경계 오용. 정상 엔진이 채점표를 통과하는가."""

from pathlib import Path

import pytest

import harness as H
import mock_engine as me

# S-4 §2 표에서 mock 열이 `O` 인 항목. 여기서 하나가 조용히 빠지면 T1 이 무너진다
SPEC_MOCK_COLUMN = {"A1", "A2", "A3", "A4", "A5", "A7", "B", "C"}


@pytest.mark.parametrize("item", sorted(H.SCORE))
def test_acceptance_item(item):
    H.score(item)


def test_score_table_covers_spec():
    """T1 집행 — §2 표의 항목이 채점표에서 빠지면 여기서 걸린다.

    A6(소거 시간)는 mock 이 못 본다. 그것 하나만 빠져 있어야 한다.
    """
    assert SPEC_MOCK_COLUMN <= set(H.SCORE), f"채점 없는 항목: {SPEC_MOCK_COLUMN - set(H.SCORE)}"
    assert "A6" not in H.SCORE, "A6 는 실칩 전용이다 (S-4 §2)"


# ── S-4 §4 경계 오용 — 가짜 엔진 없이 직접 두드린다 ───────────────────────
@pytest.mark.parametrize("code, kwargs", [
    ("E_NSECT0",        dict(base_sector=0, n_sectors=0)),
    ("E_TALLY_OVERLAP", dict(base_sector=510, n_sectors=7)),
    ("E_TALLY_OVERLAP", dict(base_sector=1530, n_sectors=8)),
    ("E_RANGE",         dict(base_sector=2045, n_sectors=7)),
    ("E_CAP",           dict(base_sector=0, n_sectors=7, cycles=409_700)),
])
def test_rejects(code, kwargs):
    """거부는 **코드로** 갈려야 한다 — 사유 문자열만으로는 무엇을 거부했는지 못 잰다."""
    eng = me.MockEngine(me.Chip(), me.Link())
    kwargs.setdefault("cycles", 100)
    with pytest.raises(me.Reject) as e:
        eng.wear_start(pattern=0x00, **kwargs)
    assert e.value.code == code


def test_reject_restart_while_running():
    """`[D29-7]` — 한 wear 그룹 안에서 다시 시작할 수 없다."""
    eng = me.MockEngine(me.Chip(), me.Link())
    eng.wear_start(0, 7, 0x00, 100)
    eng.state = "running"
    with pytest.raises(me.Reject) as e:
        eng.wear_start(0, 7, 0x00, 100)
    assert e.value.code == "E_RUNNING"


def test_reject_new_run_on_dirty_tally():
    """§8.1 초기화가 안 돌면 X축이 앞선 채로 6일이 간다.

    TB 인수 시험이 tally 에 `0x00` 을 남기고 가므로, 실험 개시가 그것을 소거하지 않으면
    여기서 걸려야 한다. **자동으로 소거하지 않는다** — 재개를 신규로 착각하면
    X축이 통째로 날아간다.
    """
    chip = me.Chip()
    me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)   # TB 인수 시험
    with pytest.raises(me.Reject) as e:
        me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)
    assert e.value.code == "E_DIRTY"

    for copy in chip.tally:                                       # §8.1 초기화
        copy[:] = b"\xff" * me.TALLY_BYTES
    me.MockEngine(chip, me.Link()).wear_start(0, 7, 0x00, 100)    # 이제 통과


def test_every_reject_has_a_case():
    """T3 집행 — §4 의 여섯 줄과 거부 코드가 1:1 인가.

    목록에만 있고 케이스가 없으면 **거부한다고 적어 두고 안 재는 줄**이 생긴다.
    """
    src = (Path(__file__).parent / "test_acceptance.py").read_text()
    missing = {c for c in me.REJECTS if f'"{c}"' not in src}
    assert not missing, f"케이스 없는 거부 코드: {sorted(missing)}"


def test_uid_matches_registry():
    """A7 의 경계 쪽 절반 — 로그 쪽 절반은 `check_A7` 이 본다."""
    assert me.MockEngine(me.Chip(), me.Link()).uid_read() == me.REGISTRY_UID


def test_defect_addrs_round_trip():
    """§7 — 결함 주소는 최대 64개 + **총 개수**. 인코딩이 틀리면 전부 못 읽는다."""
    chip = me.Chip(defects=[(p, 3, 5) for p in range(70)])
    r = H.run(chip=chip)
    row = r.log.b[-1]
    assert row["defect_addr_count"] == 70          # 총 개수는 줄지 않는다
    assert len(row["defect_addrs"]) == 64          # 실은 주소는 64개까지
    assert row["defect_addrs"][0] == (0, 3, 5)
