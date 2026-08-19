from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

for name in [
    "build_real_citi_jpm_pair.py",
    "build_real_citi_jpm_risk.py",
    "build_real_citi_jpm_dashboard.py",
]:
    cmd = [sys.executable, str(ROOT / "scripts" / name)]
    print("\n>>>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)

print("\nCITI/JPM PM dashboard refreshed.")
