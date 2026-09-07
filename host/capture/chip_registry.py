#!/usr/bin/env python3
"""docs/chip_registry.md 등록부 표 파서 — UID ↔ 라벨 역조회 + 제한된 쓰기.

정본은 md 표 자체다. 별도 CSV/JSON을 두지 않는다 (로그 20 §4 H5 — 문서와 목록이
어긋나는 실패를 기각). 대신 파서를 빡빡하게 한다:
  UID 정확히 16 hex · 라벨 chip01~chip10 · UID 중복 없음 · 라벨 중복 없음
  0행 파싱 → "등록 칩 없음"이 아니라 파서 고장 (비어 있음을 정상으로 받지 않는다)
하나라도 어기면 SystemExit (비영 종료).

쓰기는 두 가지만:
  - UID 칸이 공란(빈 칸 또는 *(…)* 자리표시)인 기존 행에 UID 채우기
  - 라벨 행이 없으면 행 추가
그 외 기존 행 수정·삭제는 하지 않는다 — 사람이 한다 (UID는 불변).

--selftest: 임시 사본으로 파서·쓰기 규칙을 검증한다.
"""

import argparse
import re
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "docs" / "chip_registry.md"

LABELS = tuple(f"chip{i:02d}" for i in range(1, 11))
UID_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
PLACEHOLDER_RE = re.compile(r"^\*\(.*\)\*$")   # *(D 트랙에서 확보)* 류 = 공란 취급


class RegistryError(SystemExit):
    def __init__(self, msg):
        super().__init__(f"chip_registry: {msg}")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(lines):
    """(헤더 idx, 첫 행 idx, 끝 idx(배타)). 헤더 = '| 라벨 | UID …' 로 시작하는 줄."""
    for i, ln in enumerate(lines):
        c = _cells(ln)
        if ln.lstrip().startswith("|") and len(c) >= 2 and c[0] == "라벨" and c[1].startswith("UID"):
            first = i + 2                       # i+1 은 구분선
            end = first
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            return i, first, end
    raise RegistryError("등록부 표 헤더('| 라벨 | UID …')를 찾지 못함 — 파서 고장 또는 표 삭제")


def _parse_lines(lines):
    _, first, end = _table(lines)
    rows = {}
    seen_uid = {}
    for ln in lines[first:end]:
        c = _cells(ln)
        if len(c) < 2:
            raise RegistryError(f"열 부족: {ln.strip()!r}")
        label, cell = c[0], c[1]
        if label not in LABELS:
            raise RegistryError(f"라벨 {label!r} 은 chip01~chip10 이 아님")
        if label in rows:
            raise RegistryError(f"라벨 중복: {label}")
        if cell == "" or PLACEHOLDER_RE.match(cell):
            uid = None
        elif UID_RE.match(cell):
            uid = cell.upper()
        else:
            raise RegistryError(f"{label}: UID {cell!r} 는 정확히 16 hex 가 아님")
        if uid is not None:
            if uid in seen_uid:
                raise RegistryError(f"UID 중복: {uid} ({seen_uid[uid]} · {label})")
            seen_uid[uid] = label
        rows[label] = uid
    if not rows:
        raise RegistryError("등록부 표에서 0행 파싱 — 등록 칩 없음이 아니라 파서 고장으로 취급")
    return rows


def parse(path=REGISTRY):
    """{label: uid | None}. 규칙 위반 시 SystemExit."""
    return _parse_lines(Path(path).read_text(encoding="utf-8").splitlines(keepends=True))


def normalize_uid(uid):
    if not UID_RE.match(uid or ""):
        raise RegistryError(f"UID {uid!r} 는 정확히 16 hex 가 아님")
    return uid.upper()


def label_for(uid, path=REGISTRY):
    """UID → 라벨. 미등록이면 None."""
    uid = normalize_uid(uid)
    for label, u in parse(path).items():
        if u == uid:
            return label
    return None


def register(label, uid, first_measured, path=REGISTRY):
    """라벨 행의 공란 UID 를 채우거나(기입 절차 2번), 행이 없으면 추가한다.
    다른 값이 이미 있는 행은 건드리지 않고 SystemExit. 같은 값이면 no-op."""
    uid = normalize_uid(uid)
    if label not in LABELS:
        raise RegistryError(f"라벨 {label!r} 은 chip01~chip10 이 아님")
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    rows = _parse_lines(lines)
    owner = next((l for l, u in rows.items() if u == uid), None)
    if owner is not None:
        if owner == label:
            return
        raise RegistryError(f"UID {uid} 는 이미 {owner} 로 등록됨 — {label} 에 넣을 수 없음")
    if rows.get(label) is not None:
        raise RegistryError(f"{label} 행에 이미 UID {rows[label]} 가 있음 — 기존 행 수정 금지")

    hdr, first, end = _table(lines)
    header = _cells(lines[hdr])
    if label in rows:
        for i in range(first, end):
            c = _cells(lines[i])
            if c[0] == label:
                c[1] = uid
                lines[i] = "| " + " | ".join(c) + " |\n"
                break
    else:
        c = [""] * len(header)
        c[0], c[1] = label, uid
        if "최초 측정" in header:
            c[header.index("최초 측정")] = first_measured
        lines.insert(end, "| " + " | ".join(c) + " |\n")
    path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- selftest

_HEAD = "# 등록부\n\n산문.\n\n"
_TBL_HDR = ("| 라벨 | UID (16 hex) | 최초 측정 | 용도 | 비고 |\n"
            "| --- | --- | --- | --- | --- |\n")
_TAIL = "\n## 기입 절차\n\n산문.\n"


def _selftest():
    def expect_error(text, why):
        p = Path(d) / "r.md"
        p.write_text(text, encoding="utf-8")
        try:
            parse(p)
        except SystemExit as e:
            print(f"  ok  거부: {why} → {e}")
            return
        raise AssertionError(f"거부돼야 함: {why}")

    with tempfile.TemporaryDirectory() as d:
        good = (_HEAD + _TBL_HDR
                + "| chip01 | *(D 트랙에서 확보)* | 2026-07-08 | 브링업 | 별도 보관 |\n"
                + "| chip02 | a1b2c3d4e5f60718 | | | |\n"
                + "| chip03 | | | | |\n" + _TAIL)
        p = Path(d) / "r.md"
        p.write_text(good, encoding="utf-8")
        rows = parse(p)
        assert rows == {"chip01": None, "chip02": "A1B2C3D4E5F60718", "chip03": None}, rows
        assert label_for("a1b2c3d4e5f60718", p) == "chip02"
        assert label_for("0000000000000000", p) is None
        print("  ok  정상 md 파싱·역조회")

        expect_error(_HEAD + _TBL_HDR + "| chip01 | A1B2C3D4E5F6071 | | | |\n" + _TAIL, "UID 15자")
        expect_error(_HEAD + _TBL_HDR + "| chip01 | A1B2C3D4E5F60718 | | | |\n"
                     "| chip02 | A1B2C3D4E5F60718 | | | |\n" + _TAIL, "UID 중복")
        expect_error(_HEAD + "표 없음\n" + _TAIL, "표 삭제")
        expect_error(_HEAD + _TBL_HDR + _TAIL, "0행")
        expect_error(_HEAD + _TBL_HDR + "| chip11 | | | | |\n" + _TAIL, "라벨 범위 밖")
        expect_error(_HEAD + _TBL_HDR + "| chip01 | | | | |\n| chip01 | | | | |\n" + _TAIL,
                     "라벨 중복")

        # 쓰기: 자리표시 채우기 → 다른 줄은 바이트 단위로 동일
        p.write_text(good, encoding="utf-8")
        register("chip01", "0123456789abcdef", "2026-09-07", p)
        after = p.read_text(encoding="utf-8")
        assert parse(p)["chip01"] == "0123456789ABCDEF"
        assert [l for l in after.splitlines() if "chip01" not in l] == \
               [l for l in good.splitlines() if "chip01" not in l]
        assert "| chip01 | 0123456789ABCDEF | 2026-07-08 | 브링업 | 별도 보관 |" in after
        print("  ok  공란(자리표시) 채우기 — 타 셀·타 행 보존")

        register("chip01", "0123456789ABCDEF", "2026-09-07", p)           # 같은 값 no-op
        assert p.read_text(encoding="utf-8") == after
        for lab, u, why in [("chip01", "FFFFFFFFFFFFFFFF", "기존 UID 덮어쓰기"),
                            ("chip03", "0123456789ABCDEF", "타 라벨의 UID 재등록")]:
            try:
                register(lab, u, "2026-09-07", p)
            except SystemExit as e:
                print(f"  ok  거부: {why} → {e}")
            else:
                raise AssertionError(f"거부돼야 함: {why}")
        assert p.read_text(encoding="utf-8") == after

        # 행 추가 (라벨 행 자체가 없을 때) — 표 끝에, 산문은 그대로
        register("chip04", "FEDCBA9876543210", "2026-09-07", p)
        rows = parse(p)
        assert rows["chip04"] == "FEDCBA9876543210" and len(rows) == 4
        txt = p.read_text(encoding="utf-8")
        assert txt.endswith(_TAIL) and "| chip04 | FEDCBA9876543210 | 2026-09-07 |  |  |\n" in txt
        print("  ok  행 추가 — 표 끝, 산문 보존")

    print("selftest PASS")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--lookup", metavar="UID", help="UID → 라벨 출력 (미등록이면 비영 종료)")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    elif args.lookup:
        label = label_for(args.lookup)
        if label is None:
            raise RegistryError(f"미등록 UID {args.lookup.upper()}")
        print(label)
    else:
        for label, uid in parse().items():
            print(f"{label}\t{uid or '-'}")


if __name__ == "__main__":
    main()
