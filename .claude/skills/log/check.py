#!/usr/bin/env python3
"""서식 규약 기계 검사 — 사람이 읽고도 빠뜨리는 것만 본다.

규약 본문: docs/log/FORMAT.md (이 스크립트는 규약이 아니다)
사용: python3 .claude/skills/log/check.py docs/log/young/39.xxx.md
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
YOUNG = REPO / "docs" / "log" / "young"
INDEX = REPO / "docs" / "log" / "README.md"
SECTIONS = ["## 결정", "## 근거", "## 미결"]   # 산출물은 조건부라 뺀다


def gaps(index: str) -> set[str]:
    """README 「결번」 줄의 번호. 가리킬 파일이 없으니 링크를 요구하지 않는다"""
    line = re.search(r"^#+\s*결번.*$", index, re.M)
    return set(re.findall(r"\d+", line.group())) if line else set()


def check(target: Path) -> list[str]:
    bad = []
    text = target.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    num = target.name.split(".")[0]

    for s in SECTIONS:
        if not re.search(rf"^{re.escape(s)}", text, re.M):
            bad.append(f"골격 누락 — {s}")

    # 로그 번호는 첫 등장에 링크. 대괄호 안에 절·부록이 붙어도 링크로 친다
    # (`[로그 23 부록 A](...)`). 자기 번호와 결번은 가리킬 파일이 없어 뺀다
    linked = {n for n in re.findall(r"\[로그 (\d+)[^\]]*\]\([^)]+\.md\)", text)}
    seen = set(re.findall(r"로그 (\d+)(?!\d)", text))
    for n in sorted(seen - linked - gaps(index) - {num}, key=int):
        bad.append(f"로그 {n} — 링크가 한 번도 안 걸렸다")

    for _, tgt in re.findall(r"\[([^\]]+)\]\(([^)]+\.md)\)", text):
        if not (target.parent / tgt).exists():
            bad.append(f"깨진 링크 — {tgt}")

    if f"](young/{num}." not in index:
        bad.append(f"목록 미등재 — docs/log/README.md 에 로그 {num} 행이 없다")

    return bad


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"사용: {Path(__file__).name} <로그 파일>")
    target = Path(sys.argv[1]).resolve()

    bad = check(target)
    for b in bad:
        print(f"  FAIL  {b}")
    print(f"{target.name}: {'통과' if not bad else str(len(bad)) + '건'}")

    notes = [f"  {f.name}:{i}" for f in sorted(YOUNG.glob("*.md"))
             for i, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
             if re.match(r"\s*> \*\*20", l)]
    print(f"추기 {len(notes)}곳 — 뒤집힌 결정에 다 붙었는지는 사람이 본다")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
