from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> None:
    path = ROOT / "scripts" / script
    print(f"\n=== {script} ===")
    subprocess.run([sys.executable, str(path)], cwd=ROOT, check=True)


def main() -> None:
    run("run_pipeline.py")
    run("build_bac_jpm_case_study.py")
    run("run_rv_backtest.py")
    run("build_static_dashboard.py")
    print("\nResearch outputs refreshed successfully.")


if __name__ == "__main__":
    main()
