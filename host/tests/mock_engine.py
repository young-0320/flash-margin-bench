"""가짜 P/E 엔진 — `docs/interface/pe_engine.md` §2 경계 7개를 채운다.

실칩 없이 `docs/spec/s4.blackbox_tb.md` 의 채점표를 돌리기 위한 것이다.
흉내 내는 것은 **엔진 밖에서 나는 고장**뿐이고 칩 물리는 건드리지 않는다 (로그 41 `[D41-9]`).

두 가지를 주입한다 — 서로 다른 목적이다.
  * `faults`: 실험에서 나는 고장 (S-4 §3). 엔진은 정상이고 환경이 나쁘다
  * `bugs`  : 엔진 구현의 결함. **채점표가 이것을 잡아야 한다** (S-4 §7 T6)

경계는 Python 함수다. 제안-1(호출면 문법)이 닫히기 전에 UART 문자열을 고르면 그것은
발명이고, `pe_engine.md` §4 가 「층위와 무관하다」이므로 밖에서 보이는 모양만 맞춘다.
"""

from dataclasses import dataclass, field

SECTOR_PAGES = 16          # 7섹터 = 112페이지 (S-1 §1)
TALLY_SECTORS = (512, 1536)
TALLY_BYTES = 4096         # §8.1
TALLY_STRIDE = 100         # 100사이클마다 1바이트
CHECK_PERIOD = 100         # §7 기본 검사 주기
CYCLE_US = 405_000         # §1 typ 405ms — mock 은 재지 않고 상수로 쓴다

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
}


class PowerCut(Exception):
    """전원이 끊겼다. 엔진 객체는 여기서 죽고 칩 상태만 남는다."""


@dataclass
class Chip:
    """전원이 끊겨도 남는 것 — 칩 안의 상태."""
    uid: str = "D1654CB09B352233"
    tally: list = field(default_factory=lambda: [bytearray(b"\xff" * TALLY_BYTES)
                                                 for _ in range(2)])
    writable: bool = True      # False = 플래시가 안 써진다 (SPI 무응답·WP)
    worn_cycles: int = 0       # 실제로 마모된 횟수. 채점표는 이것을 못 본다

    def tally_count(self, copy):
        return self.tally[copy].count(0x00) * TALLY_STRIDE

    def next_tally_byte(self, copy):
        i = self.tally[copy].find(0xFF)
        return None if i < 0 else self.tally[copy][i]


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
            data = bytes([data[0]]) + bytes([data[1] ^ 0x08]) + data[2:]
        if self.capacity is not None and len(self.buf) + len(data) > self.capacity:
            self.dropped += 1                   # 버퍼 넘침 — 새로 온 것이 버려진다
            return
        self.buf += data

    def set_open(self, is_open):
        self._open = is_open

    def drain(self) -> bytes:
        out, self.buf = bytes(self.buf), bytearray()
        return out


class MockEngine:
    """경계 7개. 각 메서드의 근거 조항은 `pe_engine.md` §2 표."""

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
            raise ValueError("REJECT running 중 wear_start 재호출")
        if n_sectors <= 0:
            raise ValueError("REJECT n_sectors=0")
        span = range(base_sector, base_sector + n_sectors)
        if any(s in span for s in TALLY_SECTORS):
            raise ValueError("REJECT tally 섹터 침범 (S-1 §2.3 하드 가드)")
        if base_sector + n_sectors > 2048:
            raise ValueError("REJECT 주소 범위 초과")
        remaining = TALLY_BYTES * TALLY_STRIDE - self.chip.tally_count(0)
        if cycles > remaining:
            raise ValueError("REJECT tally 용량 초과")
        if any(c.count(0x00) for c in self.chip.tally):
            # §8.1 초기화가 안 돌았다. 자동 소거하지 않는다 — 재개를 신규로
            # 착각하면 X축이 통째로 날아간다. 이어서 돌리려면 wear_resume() 이다.
            raise ValueError("REJECT tally 가 비어 있지 않다 — §8.1 초기화 미실행")
        self.base, self.n_sectors, self.pattern = base_sector, n_sectors, pattern
        self.state = "running"
        self._run(cycles)

    def _run(self, cycles):
        for _ in range(cycles):
            if "board_hang" in self.faults:
                raise TimeoutError("보드 행 — 응답 없음")
            self._cycle_once()
        if "no_checkpoint_due" not in self.bugs:
            self.state = "checkpoint_due"

    def _cycle_once(self):
        self._step += 1
        target = self._step
        self._maybe_cut(target, "program")
        self._maybe_cut(target, "erase")
        if self.chip.writable:
            self.chip.worn_cycles += 1                    # ① 프로그램 ② 소거
        if "undercount" in self.bugs and target == 50:
            self._skew = 1                            # 한 번 놓치고 회복하지 않는다
        self.cycle = target - self._skew
        for sector in range(self.base, self.base + self.n_sectors):   # ③ + A 로그
            self._emit(f"A cycle={self.cycle} sector={sector} "
                       f"t_erase_us=45000 t_program_us=800 ts={target * CYCLE_US}")
        if target % CHECK_PERIOD == 0:                    # ④ 검사 주기
            self._write_tally()
            self._maybe_cut(target, "tally")
            if "drop_b_row" not in self.bugs:
                self._emit(f"B cycle={self.cycle} erase_residual_bits=0 "
                           f"program_fail_bits=0 defect_addr_count=0 defect_addrs= "
                           f"worst_page_idx=0 worst_page_bits=0 "
                           f"die_temp_c=41.2 uid_ok=1 ts={target * CYCLE_US}")
        self._maybe_cut(target, "between")

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
        if self.cut_at == cycle and self.cut_phase == phase:
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
        if not self.chip.writable:                        # SPI 무응답 — 전량 0xFF 로 보인다
            bits = n_sectors * SECTOR_PAGES * 256 * 8
            return bits, 0, [], 0, SECTOR_PAGES * 256 * 8
        return 0, 0, [], 0, 0

    def tally_read(self):
        a, b = self.chip.tally_count(0), self.chip.tally_count(1)
        return a, b, a != b

    def tally_dump(self):
        return bytes(self.chip.tally[0]), bytes(self.chip.tally[1])

    def uid_read(self):
        return self.chip.uid


from collections import namedtuple  # noqa: E402

ResumeInfo = namedtuple("ResumeInfo", "tally_a tally_b mismatch next_byte write_ok")


def _checksum(body: str) -> int:
    """제안-4 — 비트 반전을 잡는다. UART 에 패리티가 없다."""
    return sum(body.encode()) & 0xFFFF
