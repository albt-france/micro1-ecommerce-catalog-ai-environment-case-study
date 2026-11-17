"""Rebuild everything in order (about 25 minutes). Usage: python src/run_all.py [--skip-download]"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = ["src/download_data.py", "src/build_catalog.py", "src/build_taxonomy.py", "src/build_schema.py",
         "src/evaluate_detection.py", "src/build_scenarios.py", "-m pytest", "env/run_baselines.py",
         "src/build_dashboard.py", "src/build_notebook.py", "src/build_pdf.py"]

if __name__ == "__main__":
    steps = STEPS[1:] if "--skip-download" in sys.argv else STEPS
    for s in steps:
        t0 = time.time()
        subprocess.run([sys.executable, *s.split()], cwd=ROOT, check=True)
        print(f"[ok] {s} ({time.time() - t0:.0f}s)", flush=True)
