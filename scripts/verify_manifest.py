"""Verify the generated bundle against the committed local manifest."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build" / "connect"


def verify():
    manifest = json.loads((ROOT / "app" / "manifest.json").read_text())
    assert manifest["metadata"]["appmode"] == "python-fastapi"
    assert manifest["metadata"]["entrypoint"] == "api:app"
    assert manifest["python"]["version"].startswith("3.12.")
    for name, metadata in manifest["files"].items():
        path = BUNDLE / name
        assert path.is_file(), f"Missing bundle file: {name}"
        assert hashlib.md5(path.read_bytes()).hexdigest() == metadata["checksum"], name
    print(f"Verified {len(manifest['files'])} bundle file checksums; FastAPI entrypoint api:app.")


if __name__ == "__main__":
    verify()
