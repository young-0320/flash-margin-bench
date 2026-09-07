#!/usr/bin/env python3
"""docs/chip_pe.md 에 P/E 증분 행을 덧붙인다 — append-only.

행 하나 = 작업 하나. 기존 행은 읽지도 고치지도 않는다 (누적은 읽는 쪽이 계산).
--blind 면 증분 대신 "(봉인)" 을 적는다 — 행은 남고 값만 가린다.
표가 없으면 SystemExit (파서 고장을 정상으로 받지 않는다).

--selftest: 임시 사본에 두 번 append 해 기존 행이 그대로인지 확인한다.
"""

import argparse
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHIP_PE = REPO / "docs" / "chip_pe.md"
HEADER = ("일자", "라벨", "UID", "섹터 범위", "P/E 증분", "출처", "비고")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def append_pe(date, label, uid, sectors, delta, source, note="", *, blind=False, path=CHIP_PE):
    """이력 표 끝에 한 줄 추가. delta 는 "+1" 같은 문자열; blind 면 "(봉인)" 으로 대체."""
    path = Path(path)
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines(keepends=True)
    hdr = next((i for i, ln in enumerate(lines) if tuple(_cells(ln)) == HEADER), None)
    if hdr is None:
        raise SystemExit(f"chip_pe: {path.name} 에서 이력 표 헤더를 찾지 못함 — 표 삭제 또는 파서 고장")
    end = hdr + 2
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    if not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    row = [date, label, uid, sectors, "(봉인)" if blind else delta, source, note]
    if any("|" in c or "\n" in c for c in row):
        raise SystemExit("chip_pe: 셀에 '|' 또는 줄바꿈 불가")
    lines.insert(end, "| " + " | ".join(row) + " |\n")
    after = "".join(lines)
    assert after.startswith("".join(lines[:end])) and before.splitlines() == \
        [l for i, l in enumerate(after.splitlines()) if i != end], "append-only 위반"
    path.write_text(after, encoding="utf-8")


def _selftest():
    doc = ("# 이력\n\n산문.\n\n## 이력\n\n"
           "| 일자 | 라벨 | UID | 섹터 범위 | P/E 증분 | 출처 | 비고 |\n"
           "| ---- | ---- | --- | --------- | -------- | ---- | ---- |\n"
           "| 2026-07-08 | chip01 | (미확보) | 0~127 | 미상(≥1) | flash_prep | 소급 불가 |\n")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pe.md"
        p.write_text(doc, encoding="utf-8")
        append_pe("2026-09-07", "chip01", "0123456789ABCDEF", "0~127", "+1",
                  "flash_prep (batch 20260907T131500Z)", path=p)
        append_pe("2026-09-07", "chip02", "FEDCBA9876543210", "0~127", "+1",
                  "flash_prep (batch 20260907T140000Z)", blind=True, path=p)
        txt = p.read_text(encoding="utf-8")
        assert txt.startswith(doc), "기존 내용이 바뀜"
        tail = txt[len(doc):].splitlines()
        assert tail == [
            "| 2026-09-07 | chip01 | 0123456789ABCDEF | 0~127 | +1 | flash_prep (batch 20260907T131500Z) |  |",
            "| 2026-09-07 | chip02 | FEDCBA9876543210 | 0~127 | (봉인) | flash_prep (batch 20260907T140000Z) |  |",
        ], tail
        print("  ok  두 번 append — 기존 행·산문 그대로, blind 는 (봉인)")

        # 표 뒤에 산문이 있어도 표 끝에 붙는다
        p.write_text(doc + "\n산문 뒤.\n", encoding="utf-8")
        append_pe("2026-09-08", "chip03", "0000000000000001", "0~6", "+300000", "run_wear", "파일럿 종단", path=p)
        assert p.read_text(encoding="utf-8").endswith(
            "| 2026-09-08 | chip03 | 0000000000000001 | 0~6 | +300000 | run_wear | 파일럿 종단 |\n\n산문 뒤.\n")
        print("  ok  표 뒤 산문 보존")

        p.write_text("# 이력\n\n표 없음\n", encoding="utf-8")
        try:
            append_pe("2026-09-08", "chip03", "0000000000000001", "0~6", "+1", "x", path=p)
        except SystemExit as e:
            print(f"  ok  거부: 표 없음 → {e}")
        else:
            raise AssertionError("거부돼야 함")
    print("selftest PASS")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        ap.error("append 는 run_sweep_chip.py 가 한다. 사람은 md 를 직접 편집 (정정 행 추가만)")


if __name__ == "__main__":
    main()
