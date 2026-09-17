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
KINDS = [("D", "## 결정"), ("U", "## 미결")]   # ID 종류 → 그 ID 가 사는 절


def gaps(index: str) -> set[str]:
    """README 「결번」 줄의 번호. 가리킬 파일이 없으니 링크를 요구하지 않는다"""
    line = re.search(r"^#+\s*결번.*$", index, re.M)
    return set(re.findall(r"\d+", line.group())) if line else set()


def section(text: str, head: str) -> list[str]:
    """`## <head>` 절의 줄들. 다음 `## ` 에서 닫는다"""
    out, on = [], False
    for l in text.splitlines():
        if l.startswith("## "):
            on = l.strip() == head
        elif on:
            out.append(l)
    return out


def ids(lines: list[str], num: str, kind: str) -> tuple[dict[str, bool], list[str]]:
    """이 로그가 정의한 ID → 그 자리에 추기가 붙었나. 중복 ID 도 같이 돌려준다.

    불릿이 시작되면 그 ID 의 구간이 열리고, 다음 불릿이나 제목에서 닫힌다.
    구간 안의 `> **20…` 이 추기다 (들여쓴 것도 같다).
    자기 번호만 정의로 친다 — 남의 번호가 붙은 불릿은 인용이다
    """
    out, dup, cur = {}, [], None
    for l in lines:
        if m := re.match(rf"^- .*?\[{kind}(\d+)-(\d+)\]", l):
            cur = f"{m.group(1)}-{m.group(2)}" if m.group(1) == num else None
            if cur:
                if cur in out:
                    dup.append(cur)
                out.setdefault(cur, False)
        elif re.match(r"^(- |#)", l):
            cur = None
        elif cur and re.match(r"\s*> \*\*20", l):
            out[cur] = True
    return out, dup


def unlabeled(lines: list[str], kind: str) -> list[str]:
    """ID 가 안 붙은 불릿. 뒤집힘 대조의 손잡이가 없는 줄이다"""
    return [l.strip()[:44] for l in lines
            if l.startswith("- ") and not re.search(rf"\[{kind}\d+-\d+\]", l)]


def crossref() -> list[str]:
    """뒤집혔다고 인용된 결정·미결에 추기가 붙었나 — 전 로그를 걸쳐야 안다"""
    defined, annotated, cites = {}, set(), {}
    for f in sorted(YOUNG.glob("*.md")):
        num, text = f.name.split(".")[0], f.read_text(encoding="utf-8")
        for kind, head in KINDS:
            got, _ = ids(section(text, head), num, kind)
            for i, noted in got.items():
                defined[kind + i] = f.name
                if noted:
                    annotated.add(kind + i)
        for k, i in re.findall(r"\[([DU])(\d+-\d+)\][^\n]{0,8}?(?:뒤집|닫)", text):
            cites.setdefault(k + i, f.name)

    bad = []
    for i in sorted(cites.keys() - annotated):
        if defined.get(i) == cites[i]:
            continue                      # 자기 로그 안의 표현은 인용이 아니다
        where = defined.get(i)
        bad.append(f"[{i}] — {cites[i]} 가 뒤집었다는데 "
                   + (f"{where} 에 추기가 없다" if where else "정의한 로그가 없다"))
    return bad


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

    # ID 는 뒤집힘·닫힘 대조의 손잡이다. 결정과 미결 둘 다 요구한다
    for kind, head in KINDS:
        lines = section(text, head)
        got, dup = ids(lines, num, kind)
        for b in unlabeled(lines, kind):
            bad.append(f"{head} ID 없음 — `[{kind}{num}-n]` 을 단다: {b}")
        for d in sorted(set(dup)):
            bad.append(f"[{kind}{d}] 가 두 번 정의됐다")

    return bad


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"사용: {Path(__file__).name} <로그 파일>")
    target = Path(sys.argv[1]).resolve()

    bad = check(target)
    for b in bad:
        print(f"  FAIL  {b}")
    print(f"{target.name}: {'통과' if not bad else str(len(bad)) + '건'}")

    missing = crossref()
    for m in missing:
        print(f"  MISS  {m}")

    notes = sum(1 for f in YOUNG.glob("*.md")
                for l in f.read_text(encoding="utf-8").splitlines()
                if re.match(r"\s*> \*\*20", l))
    print(f"추기 {notes}곳 · 인용 대조 "
          f"{'통과' if not missing else str(len(missing)) + '건'}")
    return 1 if bad or missing else 0


if __name__ == "__main__":
    sys.exit(main())
