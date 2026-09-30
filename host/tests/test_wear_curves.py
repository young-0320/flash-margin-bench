"""`host/analysis/wear_curves.py` — A.txt → 1k 구간·섹터 분위수 표. 합성 세션 폴더로 규칙 셋을 잰다."""

import sys
from pathlib import Path

import host_side as hs

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import wear_curves as wc                                     # noqa: E402


def a_line(cycle, sector, te, tp, ts=0):
    return hs.PREFIX + hs.with_sum(f"A cycle={cycle} sector={sector} t_erase_us={te} t_program_us={tp} ts={ts}")


def write_session(tmp_path, name, lines):
    d = tmp_path / name
    d.mkdir()
    (d / "A.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def test_bins_overlap_drop_and_checksum(tmp_path):
    # 세션 1: 1~1500 사이클, 섹터 0·1. 소거 = cycle, 프로그램 = 7000
    s1 = [a_line(c, s, c, 7000) for c in range(1, 1501) for s in (0, 1)]
    s1.append(a_line(1, 0, 999999, 1)[:-1] + "0")              # 체크섬 깨진 행 → 버린다
    s1.append("OK req=1 code=x sum=0000")                       # A 행이 아닌 줄 → 버린다
    # 세션 2: 1401~1600 을 되돌려 다시 돌았다 — 소거 = 5000 으로 구분. 뒤 세션이 이겨야 한다
    s2 = [a_line(c, s, 5000, 7000) for c in range(1401, 1601) for s in (0, 1)]
    d1 = write_session(tmp_path, "s1", s1)
    d2 = write_session(tmp_path, "s2", s2)

    rows, rejected = wc.load_sessions([d1, d2], drop=[(100, 109)])
    assert rejected == 2
    assert (100, 0) not in rows and (109, 1) not in rows and (110, 0) in rows
    assert rows[(1450, 0)] == (5000, 7000)                      # 겹친 구간은 세션 2 값

    table = wc.bin_table("chipX", rows)
    by = {(r["bin_start"], r["sector"]): r for r in table}
    assert set(by) == {(1, 0), (1, 1), (1001, 0), (1001, 1)}
    b0 = by[(1, 0)]
    assert b0["bin_end"] == 1000 and b0["n"] == 990             # 1000 − 뺀 10
    assert b0["erase_us_p50"] == 506 and b0["program_us_p50"] == 7000   # 990개의 495번째 (1-99, 110-1000)
    b1 = by[(1001, 1)]
    assert b1["n"] == 600                                       # 1001~1600
    assert b1["erase_us_p90"] == 5000 and b1["erase_us_p10"] == 1061   # 600개의 60번째


def test_cli_writes_csv(tmp_path, capsys):
    d = write_session(tmp_path, "s", [a_line(c, 3, 40000 + c, 6900) for c in range(1, 8)])
    out = tmp_path / "o.csv"
    wc.main([str(d), "--chip", "chip99", "--drop-cycles", "7", "-o", str(out)])
    text = out.read_text(encoding="utf-8").splitlines()
    assert text[0] == ",".join(wc.FIELDS)
    assert text[1].startswith("chip99,1,1000,3,6,40001,40004,40006,6900,6900,6900")
    assert "n<1000 인 구간 1개" in capsys.readouterr().out
