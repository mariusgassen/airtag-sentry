import os
import subprocess
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parent.parent / "docker-entrypoint.sh"


def _write_stub(bin_dir: Path, name: str, body: str) -> Path:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def test_entrypoint_shell_syntax():
    res = subprocess.run(["sh", "-n", str(ENTRYPOINT)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_entrypoint_runs_directly_when_non_root(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"

    _write_stub(bin_dir, "id", 'echo "10001"')
    _write_stub(bin_dir, "chown", f'echo "chown:$*" >> "{log}"')
    _write_stub(bin_dir, "setpriv", f'echo "setpriv:$*" >> "{log}"')
    _write_stub(bin_dir, "python", f'echo "python:$*" >> "{log}"')

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    res = subprocess.run(["sh", str(ENTRYPOINT), "serve"], env=env, capture_output=True, text=True)

    assert res.returncode == 0, res.stderr
    assert log.read_text().splitlines() == ["python:-m airtag_sentry serve"]


def test_entrypoint_fixes_data_ownership_and_drops_privileges_when_root(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"

    _write_stub(bin_dir, "id", 'echo "0"')
    _write_stub(bin_dir, "mkdir", f'echo "mkdir:$*" >> "{log}"')
    _write_stub(bin_dir, "chown", f'echo "chown:$*" >> "{log}"')
    _write_stub(bin_dir, "setpriv", f'echo "HOME=$HOME setpriv:$*" >> "{log}"')

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}", "HOME": "/root"}
    res = subprocess.run(["sh", str(ENTRYPOINT), "poll"], env=env, capture_output=True, text=True)

    assert res.returncode == 0, res.stderr
    assert log.read_text().splitlines() == [
        "mkdir:-p /app/data",
        "chown:-R appuser:appuser /app/data",
        "HOME=/home/appuser setpriv:--reuid=appuser --regid=appuser --clear-groups -- python -m airtag_sentry poll",
    ]
