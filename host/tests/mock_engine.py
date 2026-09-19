"""가짜 P/E 엔진 — `docs/interface/pe_engine.md` §2 경계를 채운다.

실칩 없이 `docs/spec/s4.blackbox_tb.md` 의 채점표를 돌리기 위한 것이다.
흉내 내는 것은 **엔진 밖에서 나는 고장**뿐이고 칩 물리는 건드리지 않는다 (로그 41 `[D41-9]`).
예외가 하나 있다 — **소거 중 차단이 남기는 부분 소거** 는 S-1 §13 B 의 두 번째 통과 조건이
직접 요구하는 것이라 「잔류 비트가 있다/없다」까지만 둔다. 잔류량의 물리는 실칩 몫이다.

두 가지를 주입한다 — 서로 다른 목적이다.
  * `faults`: 실험에서 나는 고장 (S-4 §3). 엔진은 정상이고 환경이 나쁘다
  * `bugs`  : 엔진 구현의 결함. **채점표가 이것을 잡아야 한다** (S-4 §7 T6)

경계는 Python 함수다. 제안-1(호출면 문법)이 닫히기 전에 UART 문자열을 고르면 그것은
발명이고, `pe_engine.md` §4 가 「층위와 무관하다」이므로 밖에서 보이는 모양만 맞춘다.
"""

from collections import namedtuple
from dataclasses import dataclass, field

SECTOR_PAGES = 16          # 7섹터 = 112페이지 (S-1 §1)
PAGE_BYTES = 256
TALLY_SECTORS = (512, 1536)
TALLY_BYTES = 4096         # §8.1
TALLY_STRIDE = 100         # 100사이클마다 1바이트
CHECK_PERIOD = 100         # §7 기본 검사 주기
CYCLE_US = 405_000         # §1 typ 405ms — mock 은 재지 않고 상수로 쓴다
ERASE_US = 45_000          # §1 typ. A6 는 mock 에서 채점하지 않는다 (S-4 §2)
PROGRAM_US = SECTOR_PAGES * 800   # 섹터 16페이지 **합계** (S-4 §5.2)
DIE_TEMP_MC = 41_200       # 정수 밀리도 — `xil_printf` 는 부동소수를 못 찍는다
REGISTRY_UID = "D1654CB09B352233"   # chip01 (`docs/chip_registry.md`)
GIT_REV = "d6f6a28"
PARTIAL_RESIDUAL_BITS = 512         # 소거 중 차단이 남기는 잔류 (있다/없다만 쓴다)

FAULTS = {
    # 중단 — 진행이 멈춘다 (S-4 §3.1)
    "power_cut", "host_death", "board_hang", "link_drop", "spi_dead",
    # 전송 손상 — 진행은 되는데 받은 바이트가 틀리다 (S-4 §3.2)
    "garbage_prefix", "truncate", "glue", "bitflip", "buffer_overflow",
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
}

REJECTS = {   # 제안-2 기본값. S-4 §4 의 여섯 줄과 1:1 이다
    "E_NSECT0":        "n_sectors=0",
    "E_TALLY_OVERLAP": "tally 섹터 침범 (S-1 §2.3 하드 가드)",
    "E_RANGE":         "주소 범위 초과",
    "E_CAP":           "tally 용량 초과 (§8.1 409,600)",
    "E_RUNNING":       "running 중 wear_start 재호출 (`[D29-7]`)",
    "E_DIRTY":         "tally 가 비어 있지 않다 — §8.1 초기화 미실행",
}


class PowerCut(Exception):
    """전원이 끊겼다. 엔진 객체는 여기서 죽고 칩 상태만 남는다."""


class Reject(ValueError):
    """`REJECT <code>` — 제안-2. 여섯 거부가 코드로 갈린다.

    사유 문자열로만 두면 「거부했다」는 알아도 **무엇을 거부했는지** 를 채점할 수 없다.
    """

    def __init__(self, code):
        assert code in REJECTS, f"모르는 거부 코드: {code}"
        self.code = code
        super().__init__(f"REJECT {code} — {REJECTS[code]}")


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


class MockEngine:
    """경계 7개 + 재소거. 각 메서드의 근거 조항은 `pe_engine.md` §2 표."""

    def __init__(self, chip, link, faults=frozenset(), bugs=frozenset(),
                 cut_at=None, cut_phase="between"):
        assert set(faults) <= FAULTS, f"모르는 fault: {set(faults) - FAULTS}"
        assert set(bugs) <= set(BUGS), f"모르는 bug: {set(bugs) - set(BUGS)}"
        self.chip, self.link = chip, link
        self.faults, self.bugs = set(faults), set(bugs)
        self.cut_at, self.cut_phase = cut_at, cut_phase
        self.state, self.cycle, self.defect_seen = "idle", 0, False
        self._step = self._skew = 0   # 실제로 돈 횟수 / 보고값과의 어긋남
        self.base = self.n_sectors = self.pattern = None
        self._host_alive = "host_death" not in self.faults
        self._tally_slot = [0, 0]
        if "spi_dead" in self.faults:
            self.chip.writable = False

    # ── 경계 1 ────────────────────────────────────────────────────────────
    def wear_start(self, base_sector, n_sectors, pattern, cycles):
        if self.state == "running":
            raise Reject("E_RUNNING")
        if n_sectors <= 0:
            raise Reject("E_NSECT0")
        span = range(base_sector, base_sector + n_sectors)
        if any(s in span for s in TALLY_SECTORS):
            raise Reject("E_TALLY_OVERLAP")
        if base_sector + n_sectors > 2048:
            raise Reject("E_RANGE")
        remaining = TALLY_BYTES * TALLY_STRIDE - self.chip.tally_count(0)
        if cycles > remaining:
            raise Reject("E_CAP")
        if any(c.count(0x00) for c in self.chip.tally):
            # §8.1 초기화가 안 돌았다. 자동 소거하지 않는다 — 재개를 신규로
            # 착각하면 X축이 통째로 날아간다. 이어서 돌리려면 wear_resume() 이다.
            raise Reject("E_DIRTY")
        self.base, self.n_sectors, self.pattern = base_sector, n_sectors, pattern
        self.state = "running"
        self._emit_header()
        self._run(cycles)

    def _emit_header(self):
        """세션 헤더 1행 — S-1 §9 공통 필수(`chip_id`·`git_rev`·`base_sector`).

        매 A 행에 싣지 않는 이유는 300k 에서 A 가 2.1M행이기 때문이다. **어디에 싣나는
        재량**이고(jimin §4) 여기 기본값은 「세션당 1행」이다.
        """
        uid = "0" * 16 if "uid_wrong" in self.bugs else self.chip.uid
        self._emit(f"H chip_id={uid} git_rev={GIT_REV} base_sector={self.base} "
                   f"n_sectors={self.n_sectors} pattern=0x{self.pattern:02x} ts=0")

    def _run(self, cycles):
        for _ in range(cycles):
            if "board_hang" in self.faults:
                raise TimeoutError("보드 행 — 응답 없음")
            self._cycle_once()
        if "no_checkpoint_due" not in self.bugs:
            self.state = "checkpoint_due"

    def _cycle_once(self):
        """제안-10 — **검사 사이클만** ①프로그램 → 검사 → ②소거 로 분기한다.

        S-1 §7 이 `program_fail_bits` 를 *"프로그램 직후"* 에 재라고 하는데 §6 루프는
        검사를 ④(소거 뒤)에 두었다. 소거 뒤엔 기대 패턴이 사라져 그 문장이 실행될 수 없다.
        """
        self._step += 1
        target = self._step
        checking = target % CHECK_PERIOD == 0
        self._maybe_cut(target, "program")            # ① 프로그램 중 차단
        if self.chip.writable:
            self.chip.area_erased = False             # ① 0x00 프로그램
        p_fail = self.blank_check(self.base, self.n_sectors).program_fail_bits \
            if checking else 0                        # ← 프로그램 직후에 잰다
        self._maybe_cut(target, "erase")              # ② 소거 중 차단 — 잔류가 남는다
        if self.chip.writable:
            self.chip.worn_cycles += 1                # ① 프로그램 ② 소거
            self.chip.area_erased = True
        if "undercount" in self.bugs and target == 50:
            self._skew = 1                            # 한 번 놓치고 회복하지 않는다
        self.cycle = target - self._skew
        sectors = ([self.base] if "drop_sector_rows" in self.bugs
                   else range(self.base, self.base + self.n_sectors))
        for sector in sectors:                        # ③ + A 로그
            self._emit(f"A cycle={self.cycle} sector={sector} "
                       f"t_erase_us={ERASE_US} t_program_us={PROGRAM_US} "
                       f"ts={target * CYCLE_US}")
        if checking:                                  # ④ 검사 주기
            self._write_tally()
            self._maybe_cut(target, "tally")
            if "drop_b_row" not in self.bugs:
                self._emit_b(target, p_fail)
        self._maybe_cut(target, "between")

    def _emit_b(self, target, p_fail):
        """B 행은 **두 시점의 값** 을 싣는다 — `program_fail_bits` 는 프로그램 직후,
        `erase_residual_bits` 는 소거 직후. 정상이면 둘 다 0 부근이다."""
        bc = self.blank_check(self.base, self.n_sectors)
        addrs = ";".join(f"{p}:{b}:{k}" for p, b, k in bc.defect_addrs)
        uid_ok = 0 if "uid_wrong" in self.bugs else 1
        self._emit(f"B cycle={self.cycle} erase_residual_bits={bc.erase_residual_bits} "
                   f"program_fail_bits={p_fail} "
                   f"defect_addr_count={bc.defect_addr_count} defect_addrs={addrs} "
                   f"worst_page_idx={bc.worst_page_idx} "
                   f"worst_page_bits={bc.worst_page_bits} "
                   f"die_temp_mc={DIE_TEMP_MC} uid_ok={uid_ok} ts={target * CYCLE_US}")

    def _write_tally(self):
        copies = [0] if "tally_single" in self.bugs else [0, 1]
        for c in copies:
            if not self.chip.writable:
                continue
            i = self._tally_slot[c]
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
        self.link.emit(f"#WEAR {body} sum={_checksum(body):04x}")

    # ── 경계 2·3·4·5·6·7 ──────────────────────────────────────────────────
    def wear_status(self):
        return self.cycle, self.state, self.defect_seen

    def wear_resume(self):
        """제안-5 — 채택하지 않고 재료만 돌려준다 (로그 41 `[D41-20]`)."""
        a, b = self.chip.tally_count(0), self.chip.tally_count(1)
        if "resume_picks_larger" in self.bugs:
            return ResumeInfo(max(a, b), max(a, b), False, 0xFF, self.chip.writable)
        return ResumeInfo(a, b, a != b, self.chip.next_tally_byte(0), self.chip.writable)

    def blank_check(self, base_sector, n_sectors):
        """**부를 때 실제로 읽어서 센다.** 마지막 결과를 캐시해 두지 않는다 (제안-10).

        두 숫자는 같은 읽기에서 **기준만 달리해** 나온다 — 어떤 비트든 `0` 과 `1` 중
        정확히 하나와만 다르므로 `erase_residual + program_fail = 전량` 이 항상 성립한다.
        호스트는 이것으로 **세는 경로가 살아 있는지** 를 본다.
        """
        total = n_sectors * SECTOR_PAGES * PAGE_BYTES * 8
        if not self.chip.writable:                        # SPI 무응답 — 전량 0x00 으로 보인다
            return BlankCheck(total, 0, [], 0, 0, PAGE_BYTES * 8)
        resid = 0
        worst_idx = 0
        if self.chip.residual_sector is not None and \
                base_sector <= self.chip.residual_sector < base_sector + n_sectors:
            resid = self.chip.residual_bits
            worst_idx = (self.chip.residual_sector - base_sector) * SECTOR_PAGES
        if self.chip.area_erased:
            p_fail = total - resid                        # 지워져 있으니 0x00 과는 전부 다르다
        else:
            p_fail, resid = 0, total                      # 프로그램돼 있으니 0xFF 와 전부 다르다
        if "program_check_dead" in self.bugs:
            p_fail = 0                                    # 세는 경로가 죽었다
        addrs = self.chip.defects[:64]                    # §7 최대 64개 + 총 개수
        return BlankCheck(resid, p_fail, addrs, len(self.chip.defects), worst_idx,
                          min(resid, PAGE_BYTES * 8))

    def reerase(self, base_sector, n_sectors):
        """§8.3 5 의 재소거. **경계 7개에 이 수단이 없다 — 제안-9.**

        `wear_start` 는 §8.1 초기화가 안 돌면 거부하므로 재개 경로에서 부를 수 없고,
        `wear_resume()` 은 「채택하지 않는다」(제안-5)라 여기에 넣으면 모양이 어긋난다.
        지민이 정할 때까지 mock 이 임시로 들고 있는다.
        """
        if "no_reerase" in self.bugs or not self.chip.writable:
            return False
        self.chip.residual_bits, self.chip.residual_sector = 0, None
        return True

    def tally_read(self):
        a, b = self.chip.tally_count(0), self.chip.tally_count(1)
        return a, b, a != b

    def tally_dump(self):
        return bytes(self.chip.tally[0]), bytes(self.chip.tally[1])

    def uid_read(self):
        return self.chip.uid


ResumeInfo = namedtuple("ResumeInfo", "tally_a tally_b mismatch next_byte write_ok")
BlankCheck = namedtuple("BlankCheck", "erase_residual_bits program_fail_bits "
                                      "defect_addrs defect_addr_count "
                                      "worst_page_idx worst_page_bits")


def _checksum(body: str) -> int:
    """제안-4 — 비트 반전을 잡는다. UART 에 패리티가 없다."""
    return sum(body.encode()) & 0xFFFF
