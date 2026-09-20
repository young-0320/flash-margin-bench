import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

REPO = Path(__file__).resolve().parents[2]
SIM = REPO / "build" / "sim" / "flash_wear_sim"


@pytest.fixture(scope="session")
def sim_bin():
    """C 엔진 호스트 시뮬레이션 — ps/sim/build_sim.sh 로 빌드한다. gcc 가 없으면 skip."""
    if not shutil.which("gcc"):
        pytest.skip("gcc 가 없다 — 호스트 시뮬레이션을 빌드할 수 없다")
    subprocess.run([str(REPO / "ps" / "sim" / "build_sim.sh")], check=True, capture_output=True)
    return SIM
