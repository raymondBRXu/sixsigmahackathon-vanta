"""Check reproducible bundle assembly without building React or using the network."""

import hashlib
import json
from pathlib import Path
import tomllib

import pytest

from scripts import prepare_deploy, verify_manifest


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    root = tmp_path / "project"
    bundle = root / "build" / "connect"
    sources = {
        "app/api.py": "app = object()\n",
        "app/dockwatch/__init__.py": "from .qc import individual_limits\n",
        "app/dockwatch/qc.py": "def individual_limits(values): return values\n",
        "app/dockwatch/__pycache__/qc.cpython-312.pyc": "ignored cache",
        "app/dockwatch/old.pyc": "ignored bytecode",
        "app/frontend/dist/index.html": '<script src="./assets/app.js"></script>',
        "app/frontend/dist/assets/app.js": "console.log('compiled frontend');\n",
        "app/frontend/src/App.jsx": "source frontend, excluded",
        "app/frontend/node_modules/unused/index.js": "node dependency, excluded",
        "app/streamlit_app.py": "unrelated old entrypoint, excluded",
        "data/normal.csv": "timestamp,station_id,bikes\n",
        "data/disruption.csv": "timestamp,station_id,bikes\n",
        "data/edge_cases.csv": "timestamp,station_id,bikes\n",
        "data/stations.json": "[]\n",
        "data/settings.json": "{}\n",
        "data/generate_data.py": "data generation code, excluded",
        "tests/test_qc.py": "development tests, excluded",
        ".python-version": "3.12.3\n",
        ".env": "unrelated local settings, excluded",
    }
    for relative, content in sources.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    monkeypatch.setattr(prepare_deploy, "ROOT", root)
    monkeypatch.setattr(prepare_deploy, "BUNDLE", bundle)
    monkeypatch.setattr(verify_manifest, "ROOT", root)
    monkeypatch.setattr(verify_manifest, "BUNDLE", bundle)
    commands = []

    def export_stub(command, **kwargs):
        commands.append((command, kwargs))
        destination = Path(command[command.index("--output-file") + 1])
        destination.write_text("fastapi==0.135.1\nnumpy==2.5.4\npandas==2.3.3\n")

    monkeypatch.setattr(prepare_deploy.subprocess, "run", export_stub)
    return root, bundle, commands


def write_manifest(root, bundle):
    files = {
        path.relative_to(bundle).as_posix(): {"checksum": hashlib.md5(path.read_bytes()).hexdigest()}
        for path in bundle.rglob("*") if path.is_file()
    }
    manifest = {
        "metadata": {"appmode": "python-fastapi", "entrypoint": "api:app"},
        "python": {"version": "3.12.3"},
        "files": files,
    }
    (root / "app" / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_bundle_contains_only_runtime_inputs_and_replaces_stale_output(deployment, capsys):
    root, bundle, commands = deployment
    bundle.mkdir(parents=True)
    (bundle / "stale.txt").write_text("old generated content")
    prepare_deploy.prepare()
    assert {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()} == {
        "api.py", "dockwatch/__init__.py", "dockwatch/qc.py",
        "frontend/dist/index.html", "frontend/dist/assets/app.js",
        "data/normal.csv", "data/disruption.csv", "data/edge_cases.csv",
        "data/stations.json", "data/settings.json", ".python-version", "requirements.txt",
    }
    assert (bundle / "api.py").read_bytes() == (root / "app" / "api.py").read_bytes()
    assert (bundle / "frontend" / "dist" / "index.html").read_bytes() == (
        root / "app" / "frontend" / "dist" / "index.html"
    ).read_bytes()
    assert len(commands) == 1
    command, options = commands[0]
    assert command[:2] == ["uv", "export"]
    assert "--frozen" in command and "--no-dev" in command and "--no-emit-project" in command
    assert command[command.index("--extra") + 1] == "api"
    assert options["cwd"] == root and options["check"] is True
    requirements = (bundle / "requirements.txt").read_text()
    assert "streamlit" not in requirements.lower()
    assert not any(line.startswith(("-e ", "file:", "./", "../")) for line in requirements.splitlines())
    assert f"Prepared {bundle}" in capsys.readouterr().out


def test_prepare_requires_compiled_frontend_without_removing_existing_bundle(deployment):
    root, bundle, commands = deployment
    (root / "app" / "frontend" / "dist" / "index.html").unlink()
    bundle.mkdir(parents=True)
    (bundle / "previous.txt").write_text("previous working bundle")
    with pytest.raises(SystemExit, match="Build the React frontend"):
        prepare_deploy.prepare()
    assert (bundle / "previous.txt").read_text() == "previous working bundle"
    assert not commands


def test_project_runtime_dependencies_do_not_include_streamlit_or_local_edits():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    dependencies = project["dependencies"] + project["optional-dependencies"]["api"]
    assert all("streamlit" not in dependency.lower() for dependency in dependencies)
    assert all("file:" not in dependency and not dependency.startswith("-e ") for dependency in dependencies)


def test_matching_manifest_verifies_every_bundle_file(deployment, capsys):
    root, bundle, _ = deployment
    prepare_deploy.prepare()
    manifest = write_manifest(root, bundle)
    verify_manifest.verify()
    assert f"Verified {len(manifest['files'])} bundle file checksums" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["changed", "missing"])
def test_manifest_detects_changed_or_missing_bundle_files(deployment, failure):
    root, bundle, _ = deployment
    prepare_deploy.prepare()
    write_manifest(root, bundle)
    target = bundle / "api.py"
    if failure == "changed":
        target.write_text("different content")
    else:
        target.unlink()
    with pytest.raises(AssertionError, match="api.py"):
        verify_manifest.verify()


@pytest.mark.parametrize("field,value", [("appmode", "python-streamlit"), ("entrypoint", "wrong:app")])
def test_manifest_rejects_wrong_runtime_metadata(deployment, field, value):
    root, bundle, _ = deployment
    prepare_deploy.prepare()
    manifest = write_manifest(root, bundle)
    manifest["metadata"][field] = value
    (root / "app" / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):
        verify_manifest.verify()
