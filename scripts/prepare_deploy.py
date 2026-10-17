"""Create the generated Posit Connect bundle from locked inputs."""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build" / "connect"


def prepare():
    """Copy only runtime sources, synthetic data and compiled frontend assets."""
    web = ROOT / "app" / "frontend" / "dist"
    if not (web / "index.html").is_file():
        raise SystemExit("Build the React frontend before preparing the deployment bundle.")
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)
    shutil.copy2(ROOT / "app" / "api.py", BUNDLE / "api.py")
    shutil.copytree(ROOT / "app" / "dockwatch", BUNDLE / "dockwatch",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(web, BUNDLE / "frontend" / "dist")
    (BUNDLE / "data").mkdir()
    for name in ("normal.csv", "disruption.csv", "edge_cases.csv", "stations.json", "settings.json"):
        shutil.copy2(ROOT / "data" / name, BUNDLE / "data" / name)
    shutil.copy2(ROOT / ".python-version", BUNDLE / ".python-version")
    subprocess.run([
        "uv", "export", "--frozen", "--extra", "api", "--no-dev",
        "--no-emit-project", "--no-hashes", "--no-annotate", "--no-header",
        "--output-file", str(BUNDLE / "requirements.txt"),
    ], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    print(f"Prepared {BUNDLE}")


if __name__ == "__main__":
    prepare()
