"""Python execution sandboxes.

`DockerSandbox` is the strong boundary: no network, read-only root, dropped
capabilities, non-root user and resource limits. `SubprocessSandbox` is a
development fallback with weak isolation; it must not be described as secure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    backend: str = "disabled"
    duration_ms: float = 0.0


class PythonSandbox(Protocol):
    backend: str

    def run(self, code: str) -> tuple[bool, str]: ...


class DisabledSandbox:
    backend = "disabled"

    def run(self, code: str) -> tuple[bool, str]:
        return False, "python sandbox is disabled"

    def run_detailed(self, code: str) -> SandboxResult:
        return SandboxResult(
            ok=False,
            stderr="python sandbox is disabled",
            backend=self.backend,
        )


class SubprocessSandbox:
    """Weak isolation for local development; no network or filesystem boundary."""

    backend = "subprocess"

    def __init__(self, *, timeout: float = 10.0, max_output: int = 10_000) -> None:
        self.timeout = timeout
        self.max_output = max_output

    def run(self, code: str) -> tuple[bool, str]:
        result = self.run_detailed(code)
        output = result.stdout or result.stderr
        return result.ok, output

    def run_detailed(self, code: str) -> SandboxResult:
        started = time.perf_counter()
        workdir = Path(tempfile.mkdtemp(prefix="scout-python-"))
        script = workdir / "main.py"
        script.write_text(code, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONSTARTUP", None)
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                check=False,
            )
            stdout = completed.stdout[: self.max_output]
            stderr = completed.stderr[: self.max_output]
            return SandboxResult(
                ok=completed.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=completed.returncode,
                backend=self.backend,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                ok=False,
                stderr=f"timeout after {self.timeout}s",
                timed_out=True,
                backend=self.backend,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


class DockerSandbox:
    backend = "docker"

    def __init__(
        self,
        *,
        image: str = "python:3.10-slim",
        timeout: float = 10.0,
        max_output: int = 10_000,
    ) -> None:
        self.image = image
        self.timeout = timeout
        self.max_output = max_output

    def build_command(self, workdir: Path) -> list[str]:
        mount = str(workdir.resolve()).replace("\\", "/")
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=64m",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "-v",
            f"{mount}:/work:rw",
            "-w",
            "/work",
            self.image,
            "python",
            "-I",
            "/work/main.py",
        ]

    def run(self, code: str) -> tuple[bool, str]:
        result = self.run_detailed(code)
        output = result.stdout or result.stderr
        return result.ok, output

    def run_detailed(self, code: str) -> SandboxResult:
        started = time.perf_counter()
        if shutil.which("docker") is None:
            return SandboxResult(
                ok=False,
                stderr="docker is not installed",
                backend=self.backend,
            )
        workdir = Path(tempfile.mkdtemp(prefix="scout-docker-"))
        script = workdir / "main.py"
        script.write_text(code, encoding="utf-8")
        try:
            completed = subprocess.run(
                self.build_command(workdir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            return SandboxResult(
                ok=completed.returncode == 0,
                stdout=completed.stdout[: self.max_output],
                stderr=completed.stderr[: self.max_output],
                exit_code=completed.returncode,
                backend=self.backend,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                ok=False,
                stderr=f"timeout after {self.timeout}s",
                timed_out=True,
                backend=self.backend,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def make_sandbox(
    backend: str,
    *,
    image: str = "python:3.10-slim",
    timeout: float = 10.0,
) -> DisabledSandbox | SubprocessSandbox | DockerSandbox:
    if backend == "docker":
        return DockerSandbox(image=image, timeout=timeout)
    if backend == "subprocess":
        return SubprocessSandbox(timeout=timeout)
    return DisabledSandbox()
