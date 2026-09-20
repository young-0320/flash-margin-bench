"""가짜 P/E 엔진 — `docs/interface/pe_engine.md` §2 경계 9개를 채운다.

실칩 없이 `docs/spec/s4.blackbox_tb.md` 의 채점표를 돌리기 위한 것이다.
흉내 내는 것은 **엔진 밖에서 나는 고장**뿐이고 칩 물리는 건드리지 않는다 (로그 41 `[D41-9]`).
예외가 하나 있다 — **소거 중 차단이 남기는 부분 소거** 는 S-1 §13 B 의 두 번째 통과 조건이
직접 요구하는 것이라 「잔류 비트가 있다/없다」까지만 둔다. 잔류량의 물리는 실칩 몫이다.

두 가지를 주입한다 — 서로 다른 목적이다.
  * `faults`: 실험에서 나는 고장 (S-4 §3). 엔진은 정상이고 환경이 나쁘다
  * `bugs`  : 엔진 구현의 결함. **채점표가 이것을 잡아야 한다** (S-4 §7 T6)

경계는 Python 함수이고, 그 위에 **명령 문자열 입구** `command(line)` 이 있다 (S-4 §5.2 제안-1).
체크섬·`req`·`E_SUM`·`E_DUP` 는 문자열 위에서만 생기므로 거기서 두드린다. 문자열의 생성·해석은
`host_side.py` 의 함수만 쓴다 — 여기서 문법을 따로 갖지 않는다.

엔진은 무상태다 (`pe_engine.md` §1). 이어 가는 값은 `wear_start` 의 `cycle`·`delta`·`session`
과 칩의 tally 에서만 온다.
"""

from dataclasses import dataclass, field

import host_side as hs

SECTOR_PAGES = 16          # 7섹터 = 112페이지 (S-1 §1)
PAGE_BYTES = 256
CHIP_SECTORS = 2048        # W25Q64JV 8MB / 4KB
TALLY_SECTORS = (512, 1536)
CTRL_RANGES = ((7, 13), (2041, 2047))   # 근접·원격 대조군 (S-1 §2.1) — 엔진 상수 `[D44-2]`
TALLY_BYTES = 4096         # §8.1
TALLY_STRIDE = 100         # 100사이클마다 1바이트 — **절대 사이클 기준**
TALLY_CAP = TALLY_BYTES * TALLY_STRIDE   # 409,600 (§8.1)
CHECK_PERIOD = 100         # §7 기본 검사 주기
DENSE_PERIOD = 10          # §7 조밀화 주기 (결함 비트 1회 검출 뒤)
DEFECT_STOP = 4588         # S-1 §10 정지 문턱
CYCLE_US = 405_000         # §1 typ 405ms — mock 은 재지 않고 상수로 쓴다
ERASE_US = 45_000          # §1 typ. A6 는 mock 에서 채점하지 않는다 (S-4 §2)
PROGRAM_US = SECTOR_PAGES * 800   # 섹터 16페이지 **합계** (S-4 §5.2)
REGISTRY_UID = "D1654CB09B352233"   # chip01 (`docs/chip_registry.md`)
GIT_REV = "d6f6a28"
SESSION = 1_758_412_800    # 호스트가 주는 세션 id — UTC epoch 초 (`[D44-5]`)
PARTIAL_RESIDUAL_BITS = 512         # 소거 중 차단이 남기는 잔류 (있다/없다만 쓴다)
STATES = ("idle", "running", "checkpoint_due", "recovering", "halted", "error")

FAULTS = {
    # 중단 — 진행이 멈춘다 (S-4 §3.1)
    "power_cut", "host_death", "board_hang", "link_drop", "spi_dead",
    # 전송 손상 — 진행은 되는데 받은 바이트가 틀리다 (S-4 §3.2)
    "garbage_prefix", "truncate", "glue", "bitflip", "buffer_overflow",
    # 명령 채널 손상 (S-4 §3.2 마지막 두 줄, `[D44-14]`) — 엔진이 아니라 명령 문자열에 주입한다
    "cmd_corrupt", "cmd_dup",
}

BUGS = {
    "undercount":         "중간에 한 번 카운터를 안 올린다 (최종 −1)",
    "tally_rewrite":      "tally 를 같은 바이트에 다시 쓴다 (§8.1 금지)",
    "tally_single":       "tally 를 한 벌만 쓴다 (§8.1 2벌)",
    "no_checkpoint_due":  "체크포인트에 도달해도 state 를 올리지 않는다",
    "drop_b_row":         "무결성 로그(B) 를 내보내지 않는다",
    "resume_picks_larger":"재개에서 엔진이 큰 쪽을 채택한다 (`[D41-20]` 이 폐기한 동작)",
    "drop_sector_rows":   "A 로그를 섹터별이 아니라 사이클당 1행만 뱉는다 (§9 A)",
    "uid_wrong":          "로그의 chip_id 가 등록부와 다르다 — 경계 7 은 맞는 값을 준다",
    "no_reerase":         "부분 소거를 알고도 재소거하지 않는다 (§8.3 5)",
    "program_check_dead": "`program_fail_bits` 를 늘 0 으로 돌려준다 — 세는 경로가 죽었다",
    "tally_by_delta":     "tally 눈금을 절대 사이클이 아니라 delta 상대로 찍는다 — 60+40 에서 100 눈금이 안 나온다 (J)",
}

REJECTS = {   # S-4 §4 의 열한 줄과 1:1. 순서가 우선순위다 (`E_RUNNING`/`E_STATE` 는 같은 자리)
    "E_SUM":           "명령 체크섬 불일치 (제안-4 · `[D44-14]`)",
    "E_DUP":           "이미 처리한 req 재도착 — 재실행 없음 (`[D44-14]`)",
    "E_NSECT0":        "n_sectors=0",
    "E_RANGE":         "주소 범위 초과",
    "E_TALLY_OVERLAP": "tally 섹터 침범 (S-1 §2.3 하드 가드)",
    "E_CTRL_OVERLAP":  "근접·원격 대조군 침범 (S-1 §2.3 · `[D44-2]`)",
    "E_CAP":           "cycle+delta 가 tally 용량 초과 (§8.1 409,600)",
    "E_RUNNING":       "running 중 wear_start 재호출 (`[D29-7]`)",
    "E_STATE":         "상태에 맞지 않는 명령 (recovering 밖의 reerase 등, `[D44-3]`)",
    "E_DIRTY":         "tally 에 마크가 있는데 cycle=0 — §8.1 초기화 미실행 (`[D44-10]`)",
    "E_CYCLE":         "cycle 이 tally×100 과 d 규칙(0 ≤ d < 100) 밖 (`[D44-10]`)",
}
assert tuple(REJECTS) == hs.REJECT_CODES


class PowerCut(Exception):
    """전원이 끊겼다. 엔진 객체는 여기서 죽고 칩 상태만 남는다."""


Reject = hs.Reject                                  # 거부 예외와 경계 반환 모양은 host_side 가 정본
ResumeInfo, BlankCheck, Reerase = hs.ResumeInfo, hs.BlankCheck, hs.Reerase


@dataclass
class Chip:
    """전원이 끊겨도 남는 것 — 칩 안의 상태."""
    uid: str = REGISTRY_UID
    tally: list = field(default_factory=lambda: [bytearray(b"\xff" * TALLY_BYTES)
                                                 for _ in range(2)])
    writable: bool = True      # False = 플래시가 안 써진다 (SPI 무응답·WP)
    worn_cycles: int = 0       # 실제로 마모된 횟수. 채점표는 이것을 못 본다
    residual_bits: int = 0     # 부분 소거 잔류 — 소거 중 차단에서만 생긴다 (§13 B)
    residual_sector: int = None
    area_erased: bool = True   # 마모 영역이 지금 `0xFF` 인가 `0x00` 인가 (제안-10)
    defects: list = field(default_factory=list)   # (page, byte, bit) — 씨앗으로만 준다

    def tally_count(self, copy):
        return self.tally[copy].count(0x00) * TALLY_STRIDE

    def tally_marked(self):
        """§3 #5 — 두 벌 중 어느 하나라도 `0xFF` 가 아닌 바이트가 있으면 마크가 있다."""
        return any(b != 0xFF for c in self.tally for b in c)

    def next_tally_byte(self, copy):
        """다음에 쓸 자리의 값. 앞에서부터 순서대로 쓰므로 `0x00` 개수가 그 자리다 (§8.1).

        `0xFF` 면 아직 안 쓴 것, **그 외 값이면 쓰다 만 것** 이다 — §8.2 의 ±1 불확실.
        """
        i = self.tally[copy].count(0x00)
        return None if i >= TALLY_BYTES else self.tally[copy][i]


class Link:
    """엔진 → 호스트 단방향 바이트 링크. 전송 손상은 전부 여기서 난다."""

    def __init__(self, faults=frozenset(), capacity=None):
        self.faults, self.capacity = set(faults), capacity
        self.buf = bytearray()
        self.dropped = 0
        self._n = 0
        self._open = True

    def emit(self, line: str):
        self._n += 1
        if not self._open:                      # 연결이 끊긴 동안은 통째로 없어진다
            self.dropped += 1
            return
        data = line.encode() + b"\n"
        if "garbage_prefix" in self.faults and self._n == 1:
            data = b"\x00\xfe\x7f" + data       # rst 쓰레기 (sweep_uart_capture.py:164)
        if "truncate" in self.faults and self._n == 3:
            data = data[: len(data) // 2]
        if "glue" in self.faults and self._n == 4:
            data = data.rstrip(b"\n")           # 다음 행이 같은 줄에 붙는다
        if "bitflip" in self.faults and self._n == 5:
            data = _flip_cycle_digit(data)      # 숫자가 숫자로 남는 반전
        if self.capacity is not None and len(self.buf) + len(data) > self.capacity:
            self.dropped += 1                   # 버퍼 넘침 — 새로 온 것이 버려진다
            return
        self.buf += data

    def set_open(self, is_open):
        self._open = is_open

    def drain(self) -> bytes:
        out, self.buf = bytes(self.buf), bytearray()
        return out


def _flip_cycle_digit(data: bytes) -> bytes:
    """`cycle=` 값의 첫 자리에서 1비트를 뒤집는다.

    `^0x01` 은 숫자를 **숫자로** 바꾼다(`'1'↔'0'`, `'9'↔'8'`). 그래서 행은 멀쩡해 보이고
    행 수도 그대로다 — 체크섬이 없으면 아무도 못 잡는다는 것이 제안-4 의 근거다.
    """
    i = data.find(b"cycle=")
    if i < 0:
        return data
    j = i + len(b"cycle=")
    return data[:j] + bytes([data[j] ^ 0x01]) + data[j + 1:]


def _overlaps(base, n, lo, hi):
    return base <= hi and lo <= base + n - 1


def check_range(base_sector, n_sectors):
    """START·BLANK·REERASE 공통 인자 검사 — §3 #2 의 순서."""
    if n_sectors <= 0:
        raise Reject("E_NSECT0")
    if base_sector < 0 or base_sector + n_sectors > CHIP_SECTORS:
        raise Reject("E_RANGE")
    if any(_overlaps(base_sector, n_sectors, s, s) for s in TALLY_SECTORS):
        raise Reject("E_TALLY_OVERLAP")
    if any(_overlaps(base_sector, n_sectors, lo, hi) for lo, hi in CTRL_RANGES):
        raise Reject("E_CTRL_OVERLAP")


class MockEngine:
    """경계 9개 + 명령 입구. 각 메서드의 근거 조항은 `pe_engine.md` §2 표."""

    def __init__(self, chip, link, faults=frozenset(), bugs=frozenset(),
                 cut_at=None, cut_phase="between", halt_at=None):
        assert set(faults) <= FAULTS, f"모르는 fault: {set(faults) - FAULTS}"
        assert set(bugs) <= set(BUGS), f"모르는 bug: {set(bugs) - set(BUGS)}"
        self.chip, self.link = chip, link
        self.faults, self.bugs = set(faults), set(bugs)
        self.cut_at, self.cut_phase = cut_at, cut_phase
        self.halt_at = halt_at              # 이 사이클을 마친 경계에서 HALT 가 도착한 것으로 본다
        self.state, self.cycle, self.defect_seen = "idle", 0, False
        self.last_reject = ""
        self._true = self._skew = 0         # 실제로 돈 누적 / 보고값과의 어긋남
        self._seg_step = 0                  # 이번 START 구간 안에서 돈 횟수 (`tally_by_delta` 용)
        self.base, self.n_sectors, self.pattern, self.session = None, None, 0x00, None
        self._host_alive = "host_death" not in self.faults
        self._tally_slot = [0, 0]
        self._last_bc = None                # recovering 이 드는 마지막 blank_check (base, n, resid)
        self._last_req = None               # 세션 안 마지막 처리 req (§3 #1)
        self._halt_pending = False
        if "spi_dead" in self.faults:
            self.chip.writable = False

    # ── 경계 1 ────────────────────────────────────────────────────────────
    def wear_start(self, base_sector, n_sectors, pattern, cycle, delta, session):
        """검사 순서 — 인자 범위 → 상태 → (tally 읽기 뒤) E_DIRTY → E_CYCLE (§3 #2).
        전부 통과한 뒤에만 플래시를 만진다."""
        check_range(base_sector, n_sectors)
        if cycle + delta > TALLY_CAP:
            raise Reject("E_CAP")
        if self.state == "running":
            raise Reject("E_RUNNING")
        counts = [c.count(0x00) for c in self.chip.tally]          # tally 읽기
        if cycle == 0 and self.chip.tally_marked():
            # §8.1 초기화가 안 돌았다. 자동 소거하지 않는다 — 재개를 신규로 착각하면
            # X축이 통째로 날아간다. 이어서 돌리려면 cycle=채택값 이다 (`[D44-10]`)
            raise Reject("E_DIRTY")
        d = cycle - max(counts) * TALLY_STRIDE                     # §3 #6
        if not 0 <= d < TALLY_STRIDE:
            raise Reject("E_CYCLE")
        self.base, self.n_sectors, self.pattern = base_sector, n_sectors, pattern
        self.session = session
        self._tally_slot = counts                                   # §3 #7
        self._true = self.cycle = cycle
        self._seg_step = 0
        self._last_bc = None
        self.state = "running"
        self._emit_header(cycle, delta)
        self._run(delta)

    def _emit_header(self, cycle, delta):
        """세션 헤더 1행 — START 마다 (`[D44-5]`). `session`·`cycle`·`delta` 를 되돌린다."""
        uid = "0" * 16 if "uid_wrong" in self.bugs else self.chip.uid
        self._emit(f"H session={self.session} chip_id={uid} git_rev={GIT_REV} "
                   f"base_sector={self.base} n_sectors={self.n_sectors} "
                   f"pattern=0x{self.pattern:02x} cycle={cycle} delta={delta} "
                   f"ts={self._true * CYCLE_US}")

    def _run(self, delta):
        for _ in range(delta):
            if "board_hang" in self.faults:
                raise TimeoutError("보드 행 — 응답 없음")
            self._cycle_once()
            if self.state != "running":                 # 정지 사유 (§10) 로 error 로 갔다
                return
            if self._halt_pending or self._true == self.halt_at:   # §3 #3 — 사이클 경계
                self._halt_pending = False
                self.state = "halted"
                self._emit_r("halt", None, "", None, 1, None, None)
                return
        if "no_checkpoint_due" not in self.bugs:
            self.state = "checkpoint_due"

    def _cycle_once(self):
        """제안-10 — **검사 사이클만** ①프로그램 → ①'검사 → ②소거 로 분기한다 (S-1 §6).

        tally 눈금과 검사 주기는 **절대 사이클** 기준이다 — 60+40 으로 나눠 돌려도 100 에서
        정확히 한 번 (J 의 근거).
        """
        target = self._true + 1
        period = DENSE_PERIOD if self.defect_seen else CHECK_PERIOD
        checking = target % period == 0
        tally_due = (self._seg_step + 1 if "tally_by_delta" in self.bugs
                     else target) % TALLY_STRIDE == 0
        self._maybe_cut(target, "program")            # ① 프로그램 중 차단
        if self.chip.writable:
            self.chip.area_erased = False             # ① 0x00 프로그램
        p = self.blank_check(self.base, self.n_sectors) if checking else None   # ①' 프로그램 직후
        self._maybe_cut(target, "erase")              # ② 소거 중 차단 — 잔류가 남는다
        if self.chip.writable:
            self.chip.worn_cycles += 1                # ① 프로그램 ② 소거
            self.chip.area_erased = True
        if "undercount" in self.bugs and target == 50:
            self._skew = 1                            # 한 번 놓치고 회복하지 않는다
        self._true, self._seg_step = target, self._seg_step + 1
        self.cycle = target - self._skew              # ③
        e = None
        if checking:                                  # ④ 검사 주기
            e = self.blank_check(self.base, self.n_sectors)      # 소거 직후
            if p.program_fail_bits or e.erase_residual_bits:
                self.defect_seen = True
        if tally_due:
            self._write_tally()
            self._maybe_cut(target, "tally")
        sectors = ([self.base] if "drop_sector_rows" in self.bugs
                   else range(self.base, self.base + self.n_sectors))
        for sector in sectors:                        # ⑥ A 로그
            self._emit(f"A cycle={self.cycle} sector={sector} "
                       f"t_erase_us={ERASE_US} t_program_us={PROGRAM_US} "
                       f"ts={target * CYCLE_US}")
        if checking and "drop_b_row" not in self.bugs:
            self._emit_b(target, p, e)
        if checking and max(p.program_fail_bits, e.erase_residual_bits) > DEFECT_STOP \
                and self.chip.writable:               # §10 정지 — spi_dead 는 전량이라 제외
            kind = "program_fail" if p.program_fail_bits > DEFECT_STOP else "erase_fail"
            self._emit_r(kind, self.base, kind.split("_")[0], None, 0,
                         max(p.program_fail_bits, e.erase_residual_bits), None)
            self.state = "error"
        self._maybe_cut(target, "between")

    def _emit_b(self, target, p, e):
        """B 행은 **두 시점의 값** 을 phase 별로 싣는다 (`[D44-13]`) — `p_*` 프로그램 직후,
        `e_*` 소거 직후. 정상이면 둘 다 0 부근이다. 두 count 에 229,376 규칙을 적용하지 않는다."""
        uid_ok = 0 if "uid_wrong" in self.bugs else 1
        self._emit(f"B cycle={self.cycle} erase_residual_bits={e.erase_residual_bits} "
                   f"program_fail_bits={p.program_fail_bits} "
                   f"p_addr_count={p.addr_count} p_addrs={hs.format_addrs(p.addrs)} "
                   f"p_worst_page={p.worst_page_idx} p_worst_bits={p.worst_page_bits} "
                   f"e_addr_count={e.addr_count} e_addrs={hs.format_addrs(e.addrs)} "
                   f"e_worst_page={e.worst_page_idx} e_worst_bits={e.worst_page_bits} "
                   f"die_temp_mc= uid_ok={uid_ok} ts={target * CYCLE_US}")

    def _emit_r(self, kind, sector, op, t_us, ok, resid_before, resid_after):
        """사건 1건 1행 (`[D44-6]`). 쓰지 않는 필드는 빈 값."""
        def s(v):
            return "" if v is None else v
        self._emit(f"R kind={kind} cycle={self.cycle} sector={s(sector)} op={op} "
                   f"t_us={s(t_us)} ok={ok} resid_before={s(resid_before)} "
                   f"resid_after={s(resid_after)} ts={self._true * CYCLE_US}")

    def _write_tally(self):
        copies = [0] if "tally_single" in self.bugs else [0, 1]
        for c in copies:
            if not self.chip.writable:
                continue
            i = self._tally_slot[c]
            if i >= TALLY_BYTES:
                continue
            self.chip.tally[c][i] = 0x00
            if "tally_rewrite" not in self.bugs:          # §8.1 바이트 재기록 금지
                self._tally_slot[c] += 1

    def _maybe_cut(self, cycle, phase):
        if self.cut_at != cycle or self.cut_phase != phase:
            return
        if phase == "erase" and self.chip.writable:
            # §13 B 두 번째 조건 — 소거가 중간에 끊기면 지워지다 만 비트가 남는다
            self.chip.residual_bits = PARTIAL_RESIDUAL_BITS
            self.chip.residual_sector = self.base
            self.chip.area_erased = True
        self.state = "halted"
        raise PowerCut(f"cycle {cycle} {phase}")

    def _emit(self, body):
        if not self._host_alive:
            return                                        # 호스트만 죽었다
        self.link.emit(hs.PREFIX + hs.with_sum(body))

    def _not_running(self):
        if self.state == "running":
            raise Reject("E_STATE")

    # ── 경계 2·3·4·5·6·7·8·9 ──────────────────────────────────────────────
    def wear_status(self):
        return self.cycle, self.state, self.defect_seen, self.last_reject

    def wear_resume(self):
        """제안-5 — 채택하지 않고 재료만 돌려준다 (로그 41 `[D41-20]`). 뒤는 `recovering` (`[D44-3]`)."""
        self._not_running()
        self.state = "recovering"
        self._last_bc = None
        a, b = self.chip.tally_count(0), self.chip.tally_count(1)
        if "resume_picks_larger" in self.bugs:
            return ResumeInfo(max(a, b), max(a, b), False, 0xFF, self.chip.writable)
        return ResumeInfo(a, b, a != b, self.chip.next_tally_byte(0), self.chip.writable)

    def blank_check(self, base_sector, n_sectors):
        """**부를 때 실제로 읽어서 센다.** 마지막 결과를 캐시해 두지 않는다 (제안-10).

        `program_fail_bits` 는 패턴 불일치, `erase_residual_bits` 는 잔류(§3 #9). 씨앗 결함의
        주소는 두 phase 에 같이 실린다 — 인코딩만 두드리는 것이다.
        """
        if n_sectors <= 0:
            raise Reject("E_NSECT0")
        if base_sector < 0 or base_sector + n_sectors > CHIP_SECTORS:
            raise Reject("E_RANGE")                       # 읽기라 tally·대조군은 막지 않는다
        total = n_sectors * SECTOR_PAGES * PAGE_BYTES * 8
        if not self.chip.writable:                        # SPI 무응답 — 전량 0x00 으로 보인다
            bc = BlankCheck(total, 0, [], 0, 0, PAGE_BYTES * 8)
        else:
            resid = 0
            worst_idx = 0
            if self.chip.residual_sector is not None and \
                    base_sector <= self.chip.residual_sector < base_sector + n_sectors:
                resid = self.chip.residual_bits
                worst_idx = (self.chip.residual_sector - base_sector) * SECTOR_PAGES
            if self.chip.area_erased:
                p_fail = total - resid                    # 지워져 있으니 0x00 과는 전부 다르다
            else:
                p_fail, resid = 0, total                  # 프로그램돼 있으니 0xFF 와 전부 다르다
            if "program_check_dead" in self.bugs:
                p_fail = 0                                # 세는 경로가 죽었다
            addrs = self.chip.defects[:64]                # §7 최대 64개 + 총 개수
            bc = BlankCheck(resid, p_fail, addrs, len(self.chip.defects), worst_idx,
                            min(resid, PAGE_BYTES * 8))
        if self.state == "recovering":
            self._last_bc = (base_sector, n_sectors, bc.erase_residual_bits)
        return bc

    def reerase(self, base_sector, n_sectors):
        """경계 8 (`[D44-6]`) — `recovering` 에서, 마지막 blank_check 가 그 범위에서 잔류를
        봤을 때만. 카운터에 더하지 않고 R 행으로만 남긴다. 자동 재시도 없음."""
        check_range(base_sector, n_sectors)
        if self.state != "recovering":
            raise Reject("E_STATE")
        if self._last_bc is None or self._last_bc[:2] != (base_sector, n_sectors) \
                or self._last_bc[2] == 0:
            raise Reject("E_STATE")
        before = self._last_bc[2]
        if "no_reerase" in self.bugs or not self.chip.writable:
            return Reerase(0, ERASE_US, before)
        sector = self.chip.residual_sector
        self.chip.residual_bits, self.chip.residual_sector = 0, None
        self._emit_r("reerase", sector, "erase", ERASE_US, 1, before, 0)
        self._last_bc = (base_sector, n_sectors, 0)
        return Reerase(1, ERASE_US, 0)

    def halt(self):
        """경계 9 (`[D44-4]`) — 다음 사이클 경계에서 멈춘다. `running` 밖에서는 `E_STATE`."""
        if self.state != "running":
            raise Reject("E_STATE")
        self._halt_pending = True

    def tally_read(self):
        """2벌을 따로, **사이클 단위** (×100). 바이트 수는 `command("TALLY")` 가 돌려준다."""
        self._not_running()
        a, b = self.chip.tally_count(0), self.chip.tally_count(1)
        return a, b, a != b

    def tally_dump(self):
        self._not_running()
        return bytes(self.chip.tally[0]), bytes(self.chip.tally[1])

    def uid_read(self):
        self._not_running()
        return self.chip.uid

    # ── 명령 입구 (S-4 §5.2 제안-1) ───────────────────────────────────────
    def command(self, line: str):
        """명령 문자열 하나 → 응답 행 목록 (`OK`/`REJECT`, DUMP 는 뒤에 `#WEAR D` 64행).

        체크섬 → `req` → (경계 메서드의) 인자 범위 → 상태 → E_DIRTY/E_CYCLE 순.
        실험 로그(H·A·B·R)는 여기가 아니라 `link` 로 나간다.
        """
        cmd = hs.parse_cmd(line)
        if cmd is None:
            return []
        if not cmd.sum_ok:
            return [self._reject(cmd.req, "E_SUM")]
        if self._last_req is not None and cmd.req <= self._last_req:
            return [self._reject(cmd.req, "E_DUP")]
        self._last_req = cmd.req                                    # 「처리」됐다 (§3 #1)
        try:
            return self._dispatch(cmd)
        except Reject as e:
            return [self._reject(cmd.req, e.code)]

    def _reject(self, req, code):
        self.last_reject = code
        return hs.format_response("REJECT", req, code=code)

    def _dispatch(self, cmd):
        a, req = cmd.args, cmd.req
        if cmd.verb == "START":
            self.wear_start(a["base"], a["n_sectors"], a["pattern"], a["cycle"],
                            a["delta"], a["session"])
            return [hs.format_response("OK", req, base=a["base"], n_sectors=a["n_sectors"],
                                       pattern=f"0x{a['pattern']:02x}", cycle=a["cycle"],
                                       delta=a["delta"], session=a["session"])]
        if cmd.verb == "STATUS":
            c, s, dseen, lr = self.wear_status()
            return [hs.format_response("OK", req, cycle=c, state=s, defect_seen=int(dseen),
                                       last_reject=lr)]
        if cmd.verb == "RESUME":
            i = self.wear_resume()
            return [hs.format_response("OK", req, tally_a=i.tally_a // TALLY_STRIDE,
                                       tally_b=i.tally_b // TALLY_STRIDE,
                                       mismatch=int(i.mismatch),
                                       next_byte="" if i.next_byte is None else i.next_byte,
                                       write_ok=int(i.write_ok))]
        if cmd.verb == "BLANK":
            b = self.blank_check(a["base"], a["n_sectors"])
            return [hs.format_response("OK", req, erase_residual_bits=b.erase_residual_bits,
                                       program_fail_bits=b.program_fail_bits,
                                       addr_count=b.addr_count, addrs=hs.format_addrs(b.addrs),
                                       worst_page=b.worst_page_idx, worst_bits=b.worst_page_bits)]
        if cmd.verb == "TALLY":
            ta, tb, m = self.tally_read()
            return [hs.format_response("OK", req, count_a=ta // TALLY_STRIDE,
                                       count_b=tb // TALLY_STRIDE, mismatch=int(m))]
        if cmd.verb == "DUMP":
            out = [hs.format_response("OK", req)]
            for copy, data in enumerate(self.tally_dump()):
                for off in range(0, TALLY_BYTES, 128):
                    out.append(hs.PREFIX + hs.with_sum(
                        f"D copy={copy} off={off} hex={data[off:off + 128].hex()}"))
            return out
        if cmd.verb == "UID":
            return [hs.format_response("OK", req, uid=self.uid_read())]
        if cmd.verb == "REERASE":
            r = self.reerase(a["base"], a["n_sectors"])
            return [hs.format_response("OK", req, ok=r.ok, t_erase_us=r.t_erase_us,
                                       resid_after=r.resid_after)]
        if cmd.verb == "HALT":
            self.halt()
            return [hs.format_response("OK", req)]
        raise Reject("E_STATE")                                     # 모르는 동사


