"""`host/analysis/pe_end.py` — 분석 스크립트를 부르지 않는 부분(세션 찾기 · raw 보관 · 승격 가드)을 합성 트리로 잰다.

실데이터 대조(chip12 --no-calib · chip17 --temp · chip09 교정의 1단계 산출물과 샌드박스 승격이 승격본과 같음)는
data/ 가 커밋되지 않아 여기 둘 수 없다 — 로그 48 참조."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import pe_end                                                # noqa: E402


def session(root, name, chip, sectors="0~6", a=True):
    d = root / name
    d.mkdir(parents=True)
    (d / "plan.txt").write_text(f"칩         : {chip}  UID D1\n마모 섹터  : {sectors} (7섹터)\n", encoding="utf-8")
    if a:
        (d / "A.txt").write_text("A\n", encoding="utf-8")
    return d


def test_find_sessions_filters_and_orders(tmp_path):
    b = tmp_path / "build"
    session(b, "1790000300", "chip90")
    session(b, "1790000100", "chip90")
    session(b, "1790000200", "chip91")                            # 다른 칩
    session(b, "1790000400", "chip90", sectors="1000~1006")       # 인수 시험 TB 영역 — 곡선에 섞이면 안 된다
    session(b, "1790000500", "chip90", a=False)                   # resume 판정 폴더 (A.txt 없음)
    assert [d.name for d in pe_end.find_sessions("chip90", [b])] == ["1790000100", "1790000300"]


def test_find_sessions_deep_for_bundle(tmp_path):
    session(tmp_path / "bundle" / "logs" / "wear", "1790000100", "chip90")
    assert pe_end.find_sessions("chip90", [tmp_path / "bundle"]) == []
    assert [d.name for d in pe_end.find_sessions("chip90", [tmp_path / "bundle"], deep=True)] == ["1790000100"]


def test_copy_raw_skips_same_and_refuses_clash(tmp_path):
    build, data = tmp_path / "build", tmp_path / "data"
    s = session(build / "logs", "1790000100", "chipX")
    (build / "data").mkdir(parents=True)
    for name in ("sweep_chipX_U_20260926T000000Z.csv", "session_chipX_U_20260926T000000Z.log",
                 "temp_chipX_65C_20261001T000000Z.csv", "temp_chipX_65C_20261001T000000Z_events.txt",
                 "temp_chipX_hourly.csv", "sweep_chipY_U_20260926T000000Z.csv"):
        (build / "data" / name).write_text(name, encoding="utf-8")
    assert pe_end.copy_raw("chipX", [s], [build / "data"], data) == 6       # 세션 2 + sweep · session · temp 원본 2
    assert (data / "wear" / "1790000100" / "A.txt").exists()
    assert not (data / "temp_chipX_hourly.csv").exists()                      # 온도 요약 산출물은 raw 가 아니다
    assert not (data / "sweep_chipY_U_20260926T000000Z.csv").exists()
    assert pe_end.copy_raw("chipX", [s], [build / "data"], data) == 0       # 다시 — 같은 파일은 건너뛴다

    (data / "session_chipX_U_20260926T000000Z.log").write_text("다른 내용", encoding="utf-8")
    (build / "data" / "sweep_chipX_U_20260927T000000Z.csv").write_text("새 것", encoding="utf-8")
    with pytest.raises(SystemExit, match="session_chipX"):
        pe_end.copy_raw("chipX", [s], [build / "data"], data)
    assert not (data / "sweep_chipX_U_20260927T000000Z.csv").exists()      # 멈추면 하나도 안 옮긴다


def test_month_of():
    assert pe_end.month_of("sweep_chip09_D1657C9713633921_20261001T085400Z.csv") == "2026-10"


def staged(tmp_path, files):
    out = tmp_path / "build" / "pe_end" / "chipX"
    out.mkdir(parents=True)
    for name in files:
        (out / name).write_bytes(b"a,b\r\n1,2\r\n")
    (out / "manifest.json").write_text(json.dumps({"files": files, "calib": False}), encoding="utf-8")
    return tmp_path / "docs" / "results"


def test_promote_refuses_twin_curves(tmp_path):
    res = staged(tmp_path, {"wear_curves_chipX_nocal_2026-10.csv": "data/wear_curves"})
    (res / "data" / "wear_curves").mkdir(parents=True)
    (res / "data" / "wear_curves" / "wear_curves_chipX_ali_2026-10.csv").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="다른 이름"):
        pe_end.promote("chipX", overwrite=True, root=tmp_path)               # --overwrite 로도 풀리지 않는다


def test_promote_refuses_changed_file(tmp_path):
    res = staged(tmp_path, {"wear_endurance_chipX_2026-10.csv": "data/wear"})
    (res / "data" / "wear").mkdir(parents=True)
    (res / "data" / "wear" / "wear_endurance_chipX_2026-10.csv").write_text("a,b\n1,2 사람이 단 사유\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="--overwrite"):
        pe_end.promote("chipX", root=tmp_path)


def test_put_keeps_line_endings_of_same_content(tmp_path):
    src, dst = tmp_path / "s.csv", tmp_path / "d.csv"
    src.write_bytes(b"a,b\r\n1,2\r\n")
    dst.write_bytes(b"a,b\n1,2\n")                                            # 승격본 LF · 스크립트 CRLF — 내용은 같다
    assert pe_end.put(src, dst) is False and dst.read_bytes() == b"a,b\n1,2\n"
    dst.unlink()
    assert pe_end.put(src, dst) is True and dst.read_bytes() == b"a,b\r\n1,2\r\n"
