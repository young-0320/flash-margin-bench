"""
temp_logger.py — 온도 제어 아두이노(hw/temperature_controller.ino · TMP117 + DFR0457)의 시리얼 출력을
화면에 보여 주면서 파일로 저장한다. 시리얼 모니터 대신 쓴다 (포트는 한 프로그램만 열 수 있다).
명령(T65 · T=45 · OFF · STATUS · RESET · HELP)은 이 창에 쳐서 엔터 — 스케치는 고치지 않는다.

사용 (리포 최상위 폴더에서):
  python hw/temp_logger.py COM3 --label chip17_65C                    # 윈도우 (pip install pyserial)
  uv run python hw/temp_logger.py /dev/ttyACM0 --label chip17_65C     # 리눅스
저장 (리포 루트 data/ — git 에 안 올라간다. 파일 이름의 시각은 UTC):
  data/temp_<label>_<YYYYMMDDTHHMMSSZ>.csv          1초마다 한 줄 — host_utc,ms,target_c,temp_c,pwm,duty_pct,state,fault
  data/temp_<label>_<YYYYMMDDTHHMMSSZ>_events.txt   그 밖의 줄(시작 안내·STATUS·ARMED·REJECT·FAULT)과 보낸 명령(>>)
끝내기: Ctrl+C (줄마다 바로 저장되므로 따로 저장할 것 없음)

주의: 우노·나노는 프로그램이 포트를 새로 열 때 리셋될 수 있고, 리셋되면 스케치는 히터 OFF 로 시작한다.
켜자마자 STATUS 를 쳐서 state=OFF 면 바로 T65 (목표 온도) 를 다시 친다. 리셋은 csv 의 ms 가 작아지는 것으로도 보인다.
"""
import argparse
import datetime
import os
import sys
import threading

import serial


def utc():
    return datetime.datetime.now(datetime.timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="온도 제어 아두이노 로거 — 화면 + 파일")
    ap.add_argument("port", help="COM3 · /dev/ttyACM0 등")
    ap.add_argument("--label", default="run", help="파일 이름에 넣을 이름 (예: chip17_65C)")
    ap.add_argument("--dir", default="data", help="저장 폴더 (기본 data — 리포 최상위에서 실행)")
    ap.add_argument("--baud", type=int, default=115200)
    a = ap.parse_args(argv)

    os.makedirs(a.dir, exist_ok=True)
    base = os.path.join(a.dir, f"temp_{a.label}_{utc().strftime('%Y%m%dT%H%M%SZ')}")
    data = open(base + ".csv", "w", encoding="utf-8", buffering=1, newline="")
    events = open(base + "_events.txt", "w", encoding="utf-8", buffering=1)
    data.write("host_utc,ms,target_c,temp_c,pwm,duty_pct,state,fault\n")

    s = serial.Serial()
    s.port, s.baudrate, s.timeout = a.port, a.baud, 1
    s.dtr = False          # 포트를 열 때 아두이노가 리셋되지 않게 (보드·OS 에 따라 안 먹을 수 있다)
    s.rts = False
    s.open()
    print(f"[저장] {base}.csv")
    print(f"[저장] {base}_events.txt")
    print("[안내] 먼저 STATUS 를 쳐서 히터 상태를 확인하세요. state=OFF 면 목표 온도(T65 등)를 다시 친다")

    stopping = threading.Event()

    def reader():
        while True:
            try:
                raw = s.readline()
            except Exception as e:                               # 끝낼 때 포트를 닫으면 여기로 온다 — 그때는 조용히
                if stopping.is_set():
                    return
                msg = f"!! 시리얼 끊김: {e}"
                events.write(f"{utc().isoformat(timespec='milliseconds')},{msg}\n")
                print(msg)
                return
            if not raw:
                continue
            t = utc()
            line = raw.decode("utf-8", "replace").strip()
            f = line.split(",")
            if len(f) == 7 and f[0].isdigit():                 # 1초마다 오는 데이터 줄
                data.write(f"{t.isoformat(timespec='milliseconds')},{line}\n")
                fault = "" if f[6] == "NONE" else f"  FAULT={f[6]}"
                print(f"{t.astimezone().strftime('%H:%M:%S')}  {f[2]:>7} C  목표 {f[1]}  "
                      f"PWM {f[3]:>3} ({f[4]:>5}%)  {f[5]}{fault}")
            elif line and not line.startswith("ms,target_c"):    # 응답·안내 줄 (스케치 머리글은 버린다)
                events.write(f"{t.isoformat(timespec='milliseconds')},{line}\n")
                print(f"   -> {line}")

    threading.Thread(target=reader, daemon=True).start()
    try:
        for cmd in sys.stdin:                                    # 친 명령을 아두이노로 보내고 기록
            cmd = cmd.strip()
            if cmd:
                s.write((cmd + "\n").encode())
                events.write(f"{utc().isoformat(timespec='milliseconds')},>> {cmd}\n")
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        print(f"\n[종료] 저장됨: {base}.csv")
        s.close()
        data.close()
        events.close()


if __name__ == "__main__":
    main()
