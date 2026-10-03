"""`host/analysis/wear_checkpoint_csv.py` — 합성 세션 로그·세션 폴더로 행 다섯 종류의 규칙을 잰다.

실데이터 대조(chip01·03·04·07·09·12 의 손 CSV 와 수치·순서 일치)는 data/ 가 커밋되지 않아 여기 둘 수 없다 — 로그 48 참조."""

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import host_side as hs

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import wear_checkpoint_csv as wcc                            # noqa: E402

CHIP, UID = "chipX", "D100000000000000"
T0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)   # 마모 시작 = 세션 폴더 이름


def stamp(t):
    return f"{t:%Y%m%dT%H%M%SZ}"


def session_log(datadir, t, mode, mhz, erase=None, program=None, width=39600.0):
    """세션 로그 + 그 스윕의 analysis.json. 스윕 파일 stamp 는 batch 와 다르게(+1분) — 생성기는 batch 를 써야 한다."""
    batch, sweep = stamp(t), f"sweep_{CHIP}_{UID}_{stamp(t + timedelta(minutes=1))}.csv"
    lines = [f"[00:00:00] batch {batch}: mode={mode} chip={CHIP} mhz={mhz} pl=None repeat=1"]
    lines += [f"[00:00:01] #PREP ERASE {s} {us}" for s, us in (erase or {}).items()]
    lines += [f"[00:00:02] #PREP PROGRAM {s} {us}" for s, us in (program or {}).items()]
    lines.append(f"[00:01:00] [1/1] VALID {sweep} (2520 rows, reason=complete)")
    (datadir / f"session_{CHIP}_{UID}_{batch}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (datadir / sweep.replace(".csv", ".analysis.json")).write_text(json.dumps(
        {"width_ps@0.01": width, "width_ps@0.001": width - 15, "width_ps@0.0001": width - 30, "floor_ber": 0.0}))
    return sweep


def a_line(cycle, sector, te, tp, ts):
    return hs.PREFIX + hs.with_sum(f"A cycle={cycle} sector={sector} t_erase_us={te} t_program_us={tp} ts={ts}")


def test_five_row_kinds(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    survey = tmp_path / "survey.csv"
    survey.write_text("label,erase_us_median\nchipX,101\n", encoding="utf-8")
    monkeypatch.setattr(wcc, "SURVEY", survey)

    # 마모 전: newchip 둘 — 집계표 신품값 101 은 첫 번째 것 (마지막 것이 아니라 이것이 x=0)
    session_log(data, T0 - timedelta(days=3), "newchip", 25, erase={s: 101 for s in range(128)}, width=39500.0)
    session_log(data, T0 - timedelta(days=2), "newchip", 25, erase={s: 200 for s in range(128)})
    session_log(data, T0 - timedelta(hours=1), "sweep", 75, width=12000.0)            # 사다리
    session_log(data, T0 - timedelta(minutes=30), "sweep", 25)                        # 마모 전 25MHz → 제외

    # 마모: 체크포인트 100 (C 행 채움) · 200 (격자에만 — 결측) · 300 (C 행 비어 있음 → A 행 재계산) · 400 (마지막보다 뒤 — 안 넣음)
    cp100 = session_log(data, T0 + timedelta(hours=1), "sweep", 25)
    manual = session_log(data, T0 + timedelta(hours=2), "sweep", 25)                  # 마모 중 C 행 없는 스윕
    cp300 = session_log(data, T0 + timedelta(hours=3), "sweep", 25)
    sdir = tmp_path / str(int(T0.timestamp()))
    sdir.mkdir()
    (sdir / "plan.txt").write_text("체크포인트 : 4점 — 100 · 200 · 300 · 400\n", encoding="utf-8")
    head = "cycle,area,sweep_csv,chip_id,base_sector,n_reads,mhz,session,t_erase_p50,t_erase_p99,t_erase_max," \
           "t_program_p50,t_program_p99,t_program_max,cycle_s_p50,cp_s,measured"
    (sdir / "checkpoints.csv").write_text("\n".join([
        head,
        f"100,0~6,{cp100},{UID},0,112,25,{sdir.name},150,160,170,6800,6850,6900,0.5,88,직후",
        f"300,0~6,{cp300},{UID},0,112,25,{sdir.name},,,,,,,,88,휴지 뒤",
    ]) + "\n", encoding="utf-8")
    a = [a_line(c, s, 1000 + c, 7000, c * 1_000_000) for c in range(1, 301) for s in range(7)]
    (sdir / "A.txt").write_text("\n".join(a) + "\n", encoding="utf-8")

    # 마모 뒤: 사다리 45MHz · newchip (마모 섹터 0-6 = 500, 나머지 = 100 · 프로그램 0-6 = 6700)
    session_log(data, T0 + timedelta(hours=4), "sweep", 45, width=21000.0)
    erase = {s: (500 if s < 7 else 100) for s in range(128)}
    session_log(data, T0 + timedelta(hours=5), "newchip", 25, erase=erase, program={s: 6700 for s in range(128)})

    warns = []
    rows = wcc.build(CHIP, [sdir], data, warn=warns.append)
    got = [(r["cycle"], r["mhz"]) for r in rows]
    assert got == [(0, 25), (0, 75), (100, 25), (200, 25), (300, 25), ("", 25), (300, 45), (300, 25)]

    x0, ladder, c100, miss, c300, man, post45, post_new = rows
    assert x0["erase_us_p50"] == 101 and x0["width_1e2_ps"] == "39500.00"          # 집계표 값과 같은 첫 newchip
    assert x0["sweep_batch"] == stamp(T0 - timedelta(days=3))                      # 스윕 stamp 아닌 batch
    assert ladder["width_1e2_ps"] == "12000.00"
    assert any("마모 전 25MHz" in w for w in warns)
    assert c100["erase_us_p50"] == "150" and c100["wear_session"] == sdir.name
    assert miss["note"].startswith("결측") and miss["width_1e2_ps"] == "" and miss["wear_session"] == sdir.name
    assert c300["erase_us_p50"] == 1000 + 201 and c300["program_us_p50"] == 7000   # A 행 101-300 의 p50
    assert "run_wear.summarize" in c300["note"]
    assert man["cycle"] == "" and manual                                            # 사이클은 사람이 채운다
    assert post45["width_1e2_ps"] == "21000.00"
    assert post_new["erase_us_p50"] == 500 and post_new["program_us_p50"] == 6700


def test_missing_analysis_json_warns(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    sweep = session_log(data, T0, "sweep", 25)
    (data / sweep.replace(".csv", ".analysis.json")).unlink()
    warns = []
    assert wcc.widths(data, sweep, warns.append) == {}
    assert "bathtub_analysis.py --json" in warns[0]
