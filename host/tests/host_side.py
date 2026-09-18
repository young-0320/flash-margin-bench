"""호스트 쪽 — 행 문법·파서·재개 판단.

**이 파일이 제안-1·3·4·5 의 실물이다** (`docs/spec/s4.blackbox_tb.md` §5).
박지민 스펙이 다르게 정하면 여기와 `mock_engine.py` 가 같이 바뀐다.

행 문법 (제안-3·4):

    #WEAR A cycle=<n> sector=<n> t_erase_us=<n> t_program_us=<n> ts=<n> sum=<4hex>
    #WEAR B cycle=<n> erase_residual_bits=<n> program_fail_bits=<n>
            defect_addr_count=<n> defect_addrs=<a;b;c> die_temp_c=<f> uid_ok=<0|1>
            ts=<n> sum=<4hex>

  * 유효 접두는 `#WEAR ` — 줄 앞에 쓰레기가 붙어도 찾는다
    (`host/capture/sweep_uart_capture.py:164` 와 같은 처리)
  * `sum` 은 그 앞까지의 본문 바이트 합 mod 0x10000. 패리티가 없는 UART 에서
    숫자 비트 반전을 잡는 유일한 수단이다
"""

PREFIX = "#WEAR "


class WearLog:
    """받은 바이트를 A·B 행으로 가른다. 깨진 행은 세지 않고 `rejected` 에 쌓는다."""

    def __init__(self):
        self.a, self.b, self.rejected = [], [], []

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
            row = _parse(text[i + len(PREFIX):])
            if row is None:
                self.rejected.append(raw)
            elif row["kind"] == "A":
                self.a.append(row)
            else:
                self.b.append(row)

    @property
    def max_cycle(self):
        """A 로그가 본 마지막 사이클. 제안-6(매 사이클 실시간)이 전제다."""
        return max((r["cycle"] for r in self.a), default=0)


def _parse(body: str):
    from mock_engine import _checksum
    if " sum=" not in body:
        return None
    payload, _, chk = body.rpartition(" sum=")
    try:
        if int(chk, 16) != _checksum(payload):
            return None                       # 비트 반전 · 행 잘림 · 두 행 붙음
    except ValueError:
        return None
    parts = payload.split()
    if not parts or parts[0] not in ("A", "B"):
        return None
    row = {"kind": parts[0]}
    for kv in parts[1:]:
        k, _, v = kv.partition("=")
        row[k] = v
    if "cycle" not in row:
        return None
    try:
        row["cycle"] = int(row["cycle"])
    except ValueError:
        return None
    return row


# ── 재개 판단 — 로그 41 `[D41-21]` ────────────────────────────────────────
NORMAL, HOST_DIED, HALT_CALL_HUMAN, TALLY_LATE = (
    "normal", "host_died", "halt_call_human", "tally_late")


def decide_resume(info, host_log_max):
    """`d` 3구간 + `d >= 100` 분기. 「큰 쪽 채택」은 하지 않는다 (`[D41-20]`).

    반환: (판정, 채택한 사이클 수)
    """
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
    return HALT_CALL_HUMAN, None
