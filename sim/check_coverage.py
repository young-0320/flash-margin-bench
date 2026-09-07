#!/usr/bin/env python3
"""G1 회귀 커버리지 대조 — 합격 기준 항목이 전부 실행됐는지 본다.

기준: docs/spec/s3.g1_test_plan.md (동결본, 소유·개정 한영웅)
근거: 같은 문서 §4 · §4.1 · §4.2 / docs/workflow/6.g1_launch_and_spec_hardening.md C 트랙

이 스크립트는 **항목 누락만** 검출한다. 어서션이 항목을 실제로 재는지는 알 수 없다
(기준 문서 §4 경고). 초록 숫자를 리뷰의 결론으로 삼지 말 것.

사용:
    check_coverage.py --results sim/build/results.xml
    cocotb 회귀 후 실행. 누락이 하나라도 있으면 비영 종료 → 회귀 전체가 FAIL.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "docs" / "spec" / "s3.g1_test_plan.md"

ROW = re.compile(r"^\|\s*(?P<id>[FWCI]\d+)\s*\|")
TOTAL = re.compile(
    r"\*\*합계 (?P<total>\d+)항목\*\* — F (?P<F>\d+) · W (?P<W>\d+) · C (?P<C>\d+) · I (?P<I>\d+)"
)
# 테스트명 규약: test_<항목ID>_<설명>  (기준 문서 §4)
TESTNAME = re.compile(r"\btest_(?P<id>[FWCI]\d+)_")


def parse_plan(path):
    """§5 표에서 항목 ID를, 합계 선언에서 기대 개수를 뽑아 교차 검증한다.

    별도 목록 파일을 두지 않는 이유는 기준 문서 §4.1. 서식이 바뀌어 파싱이 깨지면
    개수가 0이 되는 대신 합계 선언과 어긋나므로, 조용히 통과하지 않는다.
    """
    text = path.read_text(encoding="utf-8")
    body = text.split("\n## 5.", 1)
    if len(body) != 2:
        sys.exit(f"FATAL: {path} 에서 §5 를 찾지 못했다 — 기준 문서 서식 확인")
    section = body[1].split("\n## 6.", 1)[0]

    items, gated = [], set()
    amendment_block = False
    for line in section.splitlines():
        if "수정안 #1 승인 시 추가" in line:
            amendment_block = True
            continue
        if line.startswith("###"):
            amendment_block = False
        m = ROW.match(line)
        if not m:
            continue
        item = m.group("id")
        if item in items:
            sys.exit(f"FATAL: 항목 {item} 이 §5 에 중복 등장한다")
        items.append(item)
        if amendment_block:
            gated.add(item)

    m = TOTAL.search(section)
    if not m:
        sys.exit(f"FATAL: {path} §5 의 합계 선언 문장을 찾지 못했다")
    declared = {k: int(m.group(k)) for k in ("total", "F", "W", "C", "I")}

    counted = {p: sum(1 for i in items if i[0] == p) for p in "FWCI"}
    counted["total"] = len(items)
    mismatch = {k: (counted[k], declared[k]) for k in declared if counted[k] != declared[k]}
    if mismatch:
        sys.exit(
            "FATAL: §5 표 파싱 결과가 합계 선언과 어긋난다 — 표와 합계 줄을 함께 고칠 것\n"
            + "\n".join(f"  {k}: 표 {c} vs 선언 {d}" for k, (c, d) in mismatch.items())
        )
    return items, gated


def parse_results(path):
    """cocotb가 내는 JUnit XML에서 실행된 테스트명을 모은다."""
    root = ET.parse(path).getroot()
    return [tc.get("name", "") for tc in root.iter("testcase")]


def main():
    ap = argparse.ArgumentParser(description="G1 회귀 커버리지 대조")
    ap.add_argument("--results", required=True, help="cocotb JUnit XML (results.xml)")
    ap.add_argument(
        "--amendment1",
        action="store_true",
        help="계약 수정안 #1(BASE_SECTOR) 승인됨 — F11·F12 를 대조에 포함",
    )
    ap.add_argument("--plan", default=str(PLAN), help="합격 기준 문서 경로")
    args = ap.parse_args()

    items, gated = parse_plan(Path(args.plan))
    excluded = set() if args.amendment1 else gated
    required = [i for i in items if i not in excluded]

    names = parse_results(Path(args.results))
    seen = {m.group("id") for n in names for m in [TESTNAME.search(n)] if m}

    # 제외 사실은 항상 선두에 출력한다 — 플래그를 끄고 돌려 2항목이 조용히
    # 사라지는 것이 이 방식의 유일한 위험이다 (기준 문서 §4.2)
    state = "APPROVED" if args.amendment1 else "NOT APPROVED"
    ex = " ".join(sorted(excluded, key=lambda i: (i[0], int(i[1:])))) if excluded else "(없음)"
    hint = "" if args.amendment1 else "   (--amendment1 로 활성화)"
    print(f"[amendment #1: {state}]  excluded: {ex}{hint}")

    missing = [i for i in required if i not in seen]
    stray = sorted(seen - set(items), key=lambda i: (i[0], int(i[1:])))

    for item in required:
        print(f"{item:<4} {'covered ✓' if item in seen else 'MISSING ✗'}")
    if stray:
        print(f"\n기준에 없는 항목 ID: {' '.join(stray)} — 오타이거나 기준이 낡았다")
    print(f"\ncovered {len(required) - len(missing)}/{len(required)}")

    if missing or stray:
        print(f"FAIL — 누락 {len(missing)}건, 미등록 {len(stray)}건")
        return 1
    print("PASS — 누락 없음. 어서션의 충실성은 §6 ① 코드 열람이 본다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
