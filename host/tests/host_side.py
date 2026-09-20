"""호스트 쪽 — 명령·응답·행 문법과 파서, 재개 절차.

**이 파일이 호스트 쪽 문자열의 유일한 정본이다** (`docs/spec/s4.blackbox_tb.md` §5.2).
mock(`mock_engine.py`)도 UART 어댑터(`host/run/wear_link.py`)도 여기 함수만 쓴다 —
문자열을 만들거나 해석하는 코드가 두 군데 있으면 어긋났을 때 어느 쪽이 맞는지 알 수 없다.

명령 · 응답 (S-4 §5.2 — 글자 단위 정본):

    WEAR START base=<n> n_sectors=<n> pattern=0x<2hex> cycle=<n> delta=<n> session=<n> req=<n> sum=<4hex>
    WEAR STATUS req=<n> sum=<4hex>
    WEAR RESUME req=<n> sum=<4hex>
    WEAR BLANK base=<n> n_sectors=<n> req=<n> sum=<4hex>
    WEAR TALLY req=<n> sum=<4hex>
    WEAR DUMP req=<n> sum=<4hex>
    WEAR UID req=<n> sum=<4hex>
    WEAR REERASE base=<n> n_sectors=<n> req=<n> sum=<4hex>
    WEAR HALT req=<n> sum=<4hex>

    OK req=<n> <핵심 인자·반환값 key=value> sum=<4hex>
    REJECT req=<n> code=<E_*> sum=<4hex>

행 (제안-3·4 · `[D44-5]`·`[D44-13]`):

    #WEAR H session=<n> chip_id=<16hex> git_rev=<hex> base_sector=<n> n_sectors=<n> pattern=0x<2hex>
            cycle=<n> delta=<n> ts=<n> sum=<4hex>
    #WEAR A cycle=<n> sector=<n> t_erase_us=<n> t_program_us=<n> ts=<n> sum=<4hex>
    #WEAR B cycle=<n> erase_residual_bits=<n> program_fail_bits=<n>
            p_addr_count=<n> p_addrs=<p:b:k;...> p_worst_page=<n> p_worst_bits=<n>
            e_addr_count=<n> e_addrs=<p:b:k;...> e_worst_page=<n> e_worst_bits=<n>
            die_temp_mc=<n> uid_ok=<0|1> ts=<n> sum=<4hex>
    #WEAR R kind=<reerase|wip_timeout|program_fail|erase_fail|uid_mismatch|halt>
            cycle=<n> sector=<n> op=<program|erase|> t_us=<n> ok=<0|1>
            resid_before=<n> resid_after=<n> ts=<n> sum=<4hex>
    #WEAR D copy=<0|1> off=<n> hex=<256hex> sum=<4hex>

  * 체크섬은 접두 다음부터 ` sum=` 앞까지의 바이트 합 mod 0x10000. 행은 `#WEAR ` 다음부터,
    명령은 `WEAR ` 다음부터. **응답은 접두가 없으므로 `OK`/`REJECT` 부터** — 행의 종류
    글자(`A`)와 명령의 동사(`START`)가 본문에 들어가는 것과 같은 자리다 (로그 45 `[D45-1]`)
  * 유효 접두 `#WEAR ` 는 줄 앞에 쓰레기가 붙어도 찾는다 (`sweep_uart_capture.py:164`)
  * 쓰지 않는 필드는 빈 값이다 (`die_temp_mc=` · R 행의 `op=`)
"""

from collections import namedtuple

PREFIX = "#WEAR "
CMD_PREFIX = "WEAR "
ROW_KINDS = ("H", "A", "B", "R", "D")
INT_FIELDS = ("session", "cycle", "delta", "sector", "t_erase_us", "t_program_us", "ts",
              "erase_residual_bits", "program_fail_bits",
              "p_addr_count", "p_worst_page", "p_worst_bits",
              "e_addr_count", "e_worst_page", "e_worst_bits",
              "addr_count", "worst_page", "worst_bits",
              "die_temp_mc", "uid_ok", "base_sector", "base", "n_sectors",
              "t_us", "ok", "resid_before", "resid_after", "copy", "off",
              "defect_seen", "tally_a", "tally_b", "mismatch", "next_byte", "write_ok",
              "count_a", "count_b")
ADDR_FIELDS = ("p_addrs", "e_addrs", "addrs")

# 명령별 인자 순서 — S-4 §5.2 코드 블록과 같다. `req` 는 항상 마지막
CMD_ARGS = {
    "START":   ("base", "n_sectors", "pattern", "cycle", "delta", "session"),
    "STATUS":  (),
    "RESUME":  (),
    "BLANK":   ("base", "n_sectors"),
    "TALLY":   (),
    "DUMP":    (),
    "UID":     (),
    "REERASE": ("base", "n_sectors"),
    "HALT":    (),
}

REJECT_CODES = ("E_SUM", "E_DUP", "E_NSECT0", "E_RANGE", "E_TALLY_OVERLAP",
                "E_CTRL_OVERLAP", "E_CAP", "E_RUNNING", "E_STATE", "E_DIRTY", "E_CYCLE")

# 경계 3·4·8 의 반환 모양 (`pe_engine.md` §2) — mock 과 UART 어댑터가 같은 것을 돌려준다.
# tally 값은 **사이클 단위**(바이트 수 × 100) 다. 명령 채널은 바이트 수를 실어 오고 어댑터가 곱한다
ResumeInfo = namedtuple("ResumeInfo", "tally_a tally_b mismatch next_byte write_ok")
BlankCheck = namedtuple("BlankCheck", "erase_residual_bits program_fail_bits "
                                      "addrs addr_count worst_page_idx worst_page_bits")
Reerase = namedtuple("Reerase", "ok t_erase_us resid_after")


class Reject(ValueError):
    """`REJECT code=<E_*>` — 제안-2. 열한 거부가 코드로 갈린다.

    사유 문자열로만 두면 「거부했다」는 알아도 **무엇을 거부했는지** 를 채점할 수 없다.
    """

    def __init__(self, code):
        assert code in REJECT_CODES, f"모르는 거부 코드: {code}"
        self.code = code
        super().__init__(f"REJECT {code}")


def checksum(body: str) -> int:
    """제안-4 — 비트 반전을 잡는다. UART 에 패리티가 없다."""
    return sum(body.encode()) & 0xFFFF


def with_sum(body: str) -> str:
    return f"{body} sum={checksum(body):04x}"


def _split_sum(body: str):
    """`payload sum=<hex>` → payload, 체크섬 일치 여부. ` sum=` 이 없으면 None."""
    if " sum=" not in body:
        return None
    payload, _, chk = body.rpartition(" sum=")
    try:
        ok = int(chk.strip(), 16) == checksum(payload)
    except ValueError:
        ok = False
    return payload, ok


def _kv(parts):
    row = {}
    for kv in parts:
        k, _, v = kv.partition("=")
        row[k] = v
    return row


def _typed(row):
    """정수 필드는 int, 빈 값은 None. 주소 목록은 (p, b, k) 튜플 목록."""
    for k in INT_FIELDS:
        if k in row:
            v = row[k]
            if v == "":
                row[k] = None
                continue
            try:
                row[k] = int(v, 0) if k == "next_byte" else int(v)
            except ValueError:
                return None
    for k in ADDR_FIELDS:
        if k in row:
            row[k] = _parse_addrs(row[k])
            if row[k] is None:
                return None
    return row


# ── 명령 (호스트 → 보드) ───────────────────────────────────────────────────
def format_cmd(verb: str, req: int, **args) -> str:
    """`WEAR <verb> k=v … req=<n> sum=<4hex>`. 인자 순서는 `CMD_ARGS` (S-4 §5.2)."""
    keys = CMD_ARGS[verb]
    assert set(args) == set(keys), f"{verb} 인자 {sorted(args)} != {keys}"
    parts = [verb]
    for k in keys:
        parts.append(f"{k}=0x{args[k]:02x}" if k == "pattern" else f"{k}={args[k]}")
    parts.append(f"req={req}")
    return CMD_PREFIX + with_sum(" ".join(parts))


Cmd = namedtuple("Cmd", "verb req args sum_ok")


def parse_cmd(line: str):
    """엔진 쪽 파서 (mock 이 쓴다). `WEAR ` 로 시작하지 않으면 None.

    체크섬이 틀려도 verb·req 는 돌려준다 — `REJECT req=<n> code=E_SUM` 에 req 가 필요하다.
    """
    line = line.strip()
    if not line.startswith(CMD_PREFIX):
        return None
    body = line[len(CMD_PREFIX):]
    split = _split_sum(body)
    if split is None:
        payload, sum_ok = body, False
    else:
        payload, sum_ok = split
    parts = payload.split()
    if not parts:
        return None
    verb = parts[0]
    kv = _kv(parts[1:])
    try:
        req = int(kv.pop("req", "0"))
    except ValueError:
        req = 0
    args = {}
    for k, v in kv.items():
        try:
            args[k] = int(v, 0)
        except ValueError:
            args[k] = v
    return Cmd(verb, req, args, sum_ok)


# ── 응답 (보드 → 호스트) ───────────────────────────────────────────────────
Response = namedtuple("Response", "kind req fields")


def format_response(kind: str, req: int, **fields) -> str:
    """`OK req=<n> k=v … sum=` / `REJECT req=<n> code=<E_*> sum=`. 체크섬은 `OK` 부터."""
    assert kind in ("OK", "REJECT")
    parts = [kind, f"req={req}"] + [f"{k}={v}" for k, v in fields.items()]
    return with_sum(" ".join(parts))


def parse_response(line: str):
    """`OK`/`REJECT` 행을 해석한다. 체크섬 불일치·형식 불량이면 None (행이 아닌 것도 None)."""
    text = line.strip()
    parts0 = text.split(maxsplit=1)
    if not parts0 or parts0[0] not in ("OK", "REJECT"):
        return None
    split = _split_sum(text)
    if split is None or not split[1]:
        return None
    parts = split[0].split()
    row = _typed(_kv(parts[1:]))
    if row is None or "req" not in row:
        return None
    try:
        req = int(row.pop("req"))
    except ValueError:
        return None
    if parts[0] == "REJECT" and row.get("code") not in REJECT_CODES:
        return None
    return Response(parts[0], req, row)


# ── 행 (보드 → 호스트, 실험 로그) ─────────────────────────────────────────
class WearLog:
    """받은 바이트를 H·A·B·R·D 행으로 가른다. 깨진 행은 세지 않고 `rejected` 에 쌓는다."""

    def __init__(self, verify=True):
        self.verify = verify
        self.h, self.a, self.b, self.r, self.d, self.rejected = [], [], [], [], [], []

    def feed(self, data: bytes):
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            self.feed_line(raw)

    def feed_line(self, raw: bytes):
        """행 하나. `#WEAR` 접두가 없는 줄(응답 등)은 조용히 버린다 — 반환값으로 알린다."""
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            self.rejected.append(raw)
            return False
        i = text.find(PREFIX)
        if i < 0:
            self.rejected.append(raw)
            return False
        row = parse_row(text[i + len(PREFIX):], verify=self.verify)
        if row is None:
            self.rejected.append(raw)
            return False
        {"H": self.h, "A": self.a, "B": self.b, "R": self.r, "D": self.d}[row["type"]].append(row)
        return True

    @property
    def max_cycle(self):
        """A 로그가 본 마지막 사이클. 제안-6(매 사이클 실시간)이 전제다."""
        return max((r["cycle"] for r in self.a), default=0)


def parse_row(body: str, verify=True):
    """`#WEAR ` 다음부터. 종류·체크섬·정수 필드·주소 목록을 검사한다."""
    split = _split_sum(body.strip())
    if split is None:
        return None
    payload, ok = split
    if verify and not ok:
        return None                       # 비트 반전 · 행 잘림 · 두 행 붙음
    parts = payload.split()
    if not parts or parts[0] not in ROW_KINDS:
        return None
    row = _kv(parts[1:])
    row["type"] = parts[0]                # H·A·B·R·D — R 행의 `kind=` 와 이름이 겹치지 않게
    if row["type"] in ("A", "B", "R") and "cycle" not in row:
        return None
    return _typed(row)


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


def format_addrs(addrs) -> str:
    return ";".join(f"{p}:{b}:{k}" for p, b, k in addrs)


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

    엔진 1(UID 판독) · 2(tally 판독 — 이 뒤 엔진은 `recovering`) · 4(blank check · 재소거,
    경계 8), 호스트 1(등록부 대조) · 3(대조·채택) · 5(이어서 진행 여부).
    엔진이 채택하거나 중단을 스스로 정하지 않는다 (제안-5 · §8.3 1).
    6(`wear_start(cycle=채택값)`)은 호출자가 한다.
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
    reerased = bool(engine.reerase(base_sector, n_sectors).ok) if before else False
    after = engine.blank_check(base_sector, n_sectors).erase_residual_bits
    return Resume(verdict, restored, info.mismatch, before, reerased, after)
