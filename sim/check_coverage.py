#!/usr/bin/env python3
"""G1 회귀 상태 대조 — 기준 항목의 실행 여부와 PASS/FAIL을 함께 본다.

기준: docs/spec/s3.g1_test_plan.md (동결본, 소유·개정 한영웅)
근거: 같은 문서 §4 · §4.1 · §4.2 / docs/workflow/6.g1_launch_and_spec_hardening.md C 트랙

이 스크립트는 항목 누락과 JUnit 실행 결과를 검출한다. 어서션이 항목을 실제로 재는지는
알 수 없으므로(기준 문서 §4 경고), PASS 숫자를 코드 리뷰의 결론으로 삼지 말 것.

사용:
    check_coverage.py --results sim/build/results_fw.xml sim/build/results_core.xml sim/build/results_i.xml
    cocotb 회귀 후 실행. 누락이 하나라도 있으면 비영 종료 → 회귀 전체가 FAIL.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
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
    """cocotb JUnit XML에서 각 테스트의 이름과 실행 상태를 읽는다."""
    root = ET.parse(path).getroot()
    cases = []
    for tc in root.iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            status = "FAIL"
        elif tc.find("skipped") is not None:
            status = "SKIPPED"
        else:
            status = "PASS"
        cases.append(
            {
                "name": tc.get("name", ""),
                "classname": tc.get("classname", ""),
                "time": tc.get("time", ""),
                "status": status,
            }
        )
    return cases


def aggregate_status(cases):
    """All tests mapped to one item must pass; skipped work is incomplete."""
    if not cases:
        return "MISSING"
    states = {case["status"] for case in cases}
    if "FAIL" in states:
        return "FAIL"
    if states == {"PASS", "SKIPPED"}:
        return "PARTIAL"
    if "SKIPPED" in states:
        return "SKIPPED"
    return "PASS"


def write_markdown_report(path, results_path, amendment_state, excluded, items, states, by_id, overall):
    """Write a human-readable snapshot without replacing the JUnit source of truth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {state: sum(1 for item in items if states[item] == state)
              for state in ("PASS", "FAIL", "PARTIAL", "SKIPPED", "MISSING", "EXCLUDED")}
    lines = [
        "# G1 cocotb regression status",
        "",
        f"- Overall: **{overall}**",
        f"- JUnit source: `{results_path}`",
        f"- Amendment #1: **{amendment_state}**",
        f"- Summary: PASS {counts['PASS']} / FAIL {counts['FAIL']} / "
        f"PARTIAL {counts['PARTIAL']} / "
        f"SKIPPED {counts['SKIPPED']} / MISSING {counts['MISSING']} / "
        f"EXCLUDED {counts['EXCLUDED']}",
        "",
        "| ID | Automated result | Test case(s) |",
        "| --- | --- | --- |",
    ]
    for item in items:
        tests = "<br>".join(
            f"{case['name']} ({case['status']})" for case in by_id.get(item, [])
        ) or "-"
        note = " (amendment #1 not approved)" if item in excluded else ""
        lines.append(f"| {item} | **{states[item]}**{note} | {tests} |")
    lines.extend(
        [
            "",
            "> Automated PASS proves only that the recorded assertions passed. ",
            "> Assertion adequacy is reviewed separately in `docs/spec/s3.g1_review.md`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="G1 회귀 커버리지 대조")
    ap.add_argument(
        "--results",
        required=True,
        nargs="+",
        help="one or more cocotb JUnit XML files (separate Flash/Core/Integration runs)",
    )
    ap.add_argument(
        "--amendment1",
        action="store_true",
        help="계약 수정안 #1(BASE_SECTOR) 승인됨 — F11·F12 를 대조에 포함",
    )
    ap.add_argument("--plan", default=str(PLAN), help="합격 기준 문서 경로")
    ap.add_argument(
        "--markdown",
        default=str(REPO / "sim" / "build" / "g1_status.md"),
        help="사람이 읽는 상태표 출력 경로 (기본: sim/build/g1_status.md)",
    )
    args = ap.parse_args()

    items, gated = parse_plan(Path(args.plan))
    excluded = set() if args.amendment1 else gated
    required = [i for i in items if i not in excluded]

    cases = []
    for result_file in args.results:
        cases.extend(parse_results(Path(result_file)))
    by_id = defaultdict(list)
    unmapped = []
    for case in cases:
        match = TESTNAME.search(case["name"])
        if match:
            by_id[match.group("id")].append(case)
        else:
            unmapped.append(case["name"])

    # 제외 사실은 항상 선두에 출력한다 — 플래그를 끄고 돌려 2항목이 조용히
    # 사라지는 것이 이 방식의 유일한 위험이다 (기준 문서 §4.2)
    state = "APPROVED" if args.amendment1 else "NOT APPROVED"
    ex = " ".join(sorted(excluded, key=lambda i: (i[0], int(i[1:])))) if excluded else "(없음)"
    hint = "" if args.amendment1 else "   (--amendment1 로 활성화)"
    print(f"[amendment #1: {state}]  excluded: {ex}{hint}")

    states = {}
    for item in items:
        states[item] = "EXCLUDED" if item in excluded else aggregate_status(by_id.get(item, []))

    stray = sorted(set(by_id) - set(items), key=lambda i: (i[0], int(i[1:])))
    for item in items:
        print(f"{item:<4} {states[item]}")
    if stray:
        print(f"\n기준에 없는 항목 ID: {' '.join(stray)} — 오타이거나 기준이 낡았다")
    if unmapped:
        print(f"\n항목 ID가 없는 테스트: {' '.join(unmapped)}")

    counts = {status: sum(1 for item in required if states[item] == status)
              for status in ("PASS", "FAIL", "PARTIAL", "SKIPPED", "MISSING")}
    if counts["FAIL"] or stray or unmapped:
        overall = "FAIL"
    elif counts["PARTIAL"] or counts["SKIPPED"] or counts["MISSING"]:
        overall = "INCOMPLETE"
    else:
        overall = "PASS"

    print(
        f"\nPASS {counts['PASS']}/{len(required)} | FAIL {counts['FAIL']} | "
        f"PARTIAL {counts['PARTIAL']} | "
        f"SKIPPED {counts['SKIPPED']} | MISSING {counts['MISSING']} | "
        f"EXCLUDED {len(excluded)}"
    )
    print(f"OVERALL: {overall}")

    report_path = Path(args.markdown)
    write_markdown_report(
        report_path,
        ", ".join(args.results),
        state,
        excluded,
        items,
        states,
        by_id,
        overall,
    )
    print(f"status table: {report_path}")

    if overall != "PASS":
        return 1
    print("PASS — 누락 없음. 어서션의 충실성은 §6 ① 코드 열람이 본다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
