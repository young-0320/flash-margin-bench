"""호스트 쪽 — 행 문법·파서·재개 절차.

**이 파일이 제안-1·3·4·5 의 실물이다** (`docs/spec/s4.blackbox_tb.md` §5·§5.2).
박지민 스펙이 다르게 정하면 여기와 `mock_engine.py` 가 같이 바뀐다.

행 문법 (제안-3·4) — 정본은 S-4 §5.2:

    #WEAR H chip_id=<16hex> git_rev=<hex> base_sector=<n> n_sectors=<n>
            pattern=0x<2hex> ts=<n> sum=<4hex>
    #WEAR A cycle=<n> sector=<n> t_erase_us=<n> t_program_us=<n> ts=<n> sum=<4hex>
    #WEAR B cycle=<n> erase_residual_bits=<n> program_fail_bits=<n>
            defect_addr_count=<n> defect_addrs=<p:b:k;...> worst_page_idx=<n>
            worst_page_bits=<n> die_temp_mc=<n> uid_ok=<0|1> ts=<n> sum=<4hex>

  * 유효 접두는 `#WEAR ` — 줄 앞에 쓰레기가 붙어도 찾는다
    (`host/capture/sweep_uart_capture.py:164` 와 같은 처리)
  * `sum` 은 그 앞까지의 본문 바이트 합 mod 0x10000. 패리티가 없는 UART 에서
    숫자 비트 반전을 잡는 **유일한** 수단이다 — `verify=False` 로 끄면 그것을 보인다
  * 공통 필수(`chip_id`·`git_rev`·`base_sector`)는 **H 행 1행**에 싣는다. A 행마다
    실으면 300k 에서 2.1M행이 그만큼 길어진다 (어디에 싣나는 재량 — jimin §4)
"""

from collections import namedtuple

PREFIX = "#WEAR "
INT_FIELDS = ("cycle", "sector", "t_erase_us", "t_program_us", "ts",
              "erase_residual_bits", "program_fail_bits", "defect_addr_count",
              "worst_page_idx", "worst_page_bits", "die_temp_mc", "uid_ok",
              "base_sector", "n_sectors")


class WearLog:
    """받은 바이트를 H·A·B 행으로 가른다. 깨진 행은 세지 않고 `rejected` 에 쌓는다."""

    def __init__(self, verify=True):
        self.verify = verify
        self.h, self.a, self.b, self.rejected = [], [], [], []

    def feed(self, data: bytes):
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                self.rejected.append(raw)
                continue
            i = text.find(PREFIX)
            if i < 0:
                self.rejected.append(raw)
                continue
            row = _parse(text[i + len(PREFIX):], verify=self.verify)
            if row is None:
                self.rejected.append(raw)
            else:
                {"H": self.h, "A": self.a, "B": self.b}[row["kind"]].append(row)

    @property
    def max_cycle(self):
        """A 로그가 본 마지막 사이클. 제안-6(매 사이클 실시간)이 전제다."""
        return max((r["cycle"] for r in self.a), default=0)


def _parse(body: str, verify=True):
    from mock_engine import _checksum
    if " sum=" not in body:
        return None
    payload, _, chk = body.rpartition(" sum=")
    if verify:
        try:
            if int(chk, 16) != _checksum(payload):
                return None                   # 비트 반전 · 행 잘림 · 두 행 붙음
        except ValueError:
            return None
    parts = payload.split()
    if not parts or parts[0] not in ("H", "A", "B"):
        return None
    row = {"kind": parts[0]}
    for kv in parts[1:]:
        k, _, v = kv.partition("=")
        row[k] = v
    if row["kind"] in ("A", "B") and "cycle" not in row:
        return None
    for k in INT_FIELDS:
        if k in row:
            try:
                row[k] = int(row[k])
            except ValueError:
                return None
    if "defect_addrs" in row:
        row["defect_addrs"] = _parse_addrs(row["defect_addrs"])
        if row["defect_addrs"] is None:
            return None
    return row


def _parse_addrs(text):
    """`page:byte:bit` 를 `;` 로 이은 것 (§7 · 제안-3)."""
    if not text:
        return []
    out = []
    for item in text.split(";"):
        try:
            p, b, k = (int(x) for x in item.split(":"))
        except ValueError:
            return None
        out.append((p, b, k))
    return out


# ── 재개 판단 — 로그 41 `[D41-21]` ────────────────────────────────────────
NORMAL, HOST_DIED, HALT_CALL_HUMAN, TALLY_LATE, UNCERTAIN = (
    "normal", "host_died", "halt_call_human", "tally_late", "uncertain")


def decide_resume(info, host_log_max):
    """2벌 병합(§8.2) → `d` 3구간 + `d >= 100` 분기(§8.3).

    「큰 쪽 채택」은 하지 않는다 (`[D41-20]`) — **병합과 채택은 다른 일이다.**
    병합은 2벌을 tally 값 하나로 합치는 것(눈금이 같다)이고, 채택은 tally 값과 호스트
    로그 중 최종 사이클 수를 고르는 것(눈금이 다르다)이다.

    반환: (판정, 채택한 사이클 수)
    """
    if info.mismatch and abs(info.tally_a - info.tally_b) > 100:
        return HALT_CALL_HUMAN, None          # §8.2 — 정상 차단으로 설명되지 않는다
    tally = max(info.tally_a, info.tally_b) if info.mismatch else info.tally_a
    d = host_log_max - tally
    if d < 0:
        return HOST_DIED, tally               # 호스트가 놓친 구간이 있다
    if d < 100:
        return NORMAL, host_log_max
    if not info.write_ok:
        return HALT_CALL_HUMAN, None          # 플래시가 안 써진다
    if info.next_byte == 0xFF:
        return TALLY_LATE, host_log_max       # tally 쓰기 전에 끊겼다 — 정상 차단
    if info.next_byte is None:
        return HALT_CALL_HUMAN, None          # tally 를 다 썼다 — 용량 소진
    return UNCERTAIN, host_log_max            # §8.2 「그 외 값 = ±1 불확실」


# ── 재개 절차 — S-1 §8.3 1~5 ──────────────────────────────────────────────
Resume = namedtuple("Resume", "verdict restored mismatch "
                              "residual_before reerased residual_after")


def resume(engine, host_log_max, base_sector=0, n_sectors=7,
           registry_uid=None):
    """§8.3 의 다섯 단계를 **엔진 단계와 호스트 판단으로 갈라** 밟는다.

    엔진 1(UID 판독) · 2(tally 판독) · 4(blank check · 재소거),
    호스트 1(등록부 대조) · 3(대조·채택) · 5(이어서 진행 여부).
    엔진이 채택하거나 중단을 스스로 정하지 않는다 (제안-5 · §8.3 1).
    """
    from mock_engine import REGISTRY_UID
    registry_uid = REGISTRY_UID if registry_uid is None else registry_uid
    if engine.uid_read() != registry_uid:                       # 1
        return Resume(HALT_CALL_HUMAN, None, False, None, False, None)
    info = engine.wear_resume()                                 # 2
    verdict, restored = decide_resume(info, host_log_max)       # 3
    if restored is None:
        return Resume(verdict, None, info.mismatch, None, False, None)
    before = engine.blank_check(base_sector, n_sectors).erase_residual_bits   # 4
    reerased = engine.reerase(base_sector, n_sectors) if before else False
    after = engine.blank_check(base_sector, n_sectors).erase_residual_bits
    return Resume(verdict, restored, info.mismatch, before, reerased, after)
