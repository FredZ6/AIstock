#!/usr/bin/env python3
"""Start and supervise the complete local paper-only runtime."""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import time
from pathlib import Path
from types import FrameType
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import dotenv_values
from stock_platform.operations.paper_runtime import (
    ManagedProcess,
    RuntimeConfigurationError,
    build_runtime_plan,
    render_command,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
LOG_DIR = RUNTIME_DIR / "logs"


def load_environment() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / "web" / ".env.local"):
        if path.is_file():
            merged.update({key: value for key, value in dotenv_values(path).items() if value})
    merged.update(os.environ)
    return merged


def wait_for_url(url: str, processes: list[subprocess.Popen[bytes]], timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        failed = next((process for process in processes if process.poll() is not None), None)
        if failed is not None:
            raise RuntimeError(f"managed process exited before readiness: pid={failed.pid}")
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - fixed local URLs
                if 200 <= response.status < 400:
                    return
        except (OSError, URLError):
            time.sleep(0.5)
    raise TimeoutError(f"runtime readiness timed out: {url}")


class PaperRuntime:
    def __init__(self, environment: dict[str, str]) -> None:
        self.plan = build_runtime_plan(ROOT, environment)
        self.environment = os.environ | environment | dict(self.plan.environment)
        self.processes: list[subprocess.Popen[bytes]] = []
        self.logs: list[object] = []
        self.stopping = False

    def start(self) -> None:
        RUNTIME_DIR.mkdir(exist_ok=True)
        LOG_DIR.mkdir(exist_ok=True)
        subprocess.run(
            ("docker", "compose", "up", "-d", "--wait", *self.plan.infrastructure),
            cwd=ROOT,
            env=self.environment,
            check=True,
        )
        subprocess.run(self.plan.migration, cwd=ROOT, env=self.environment, check=True)
        for spec in self.plan.processes:
            self._start_process(spec)
        celery = str(ROOT / ".venv" / "bin" / "celery")
        for task in self.plan.bootstrap_tasks:
            subprocess.run(
                (
                    celery,
                    "-A",
                    "stock_platform.workers.celery_app:celery_app",
                    "call",
                    task,
                ),
                cwd=ROOT,
                env=self.environment,
                check=True,
            )
        for spec in self.plan.processes:
            if spec.ready_url is not None:
                wait_for_url(spec.ready_url, self.processes)

    def _start_process(self, spec: ManagedProcess) -> None:
        log = (LOG_DIR / f"{spec.name}.log").open("ab", buffering=0)
        self.logs.append(log)
        self.processes.append(
            subprocess.Popen(
                spec.command,
                cwd=ROOT,
                env=self.environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )

    def stop(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 15
        for process in reversed(self.processes):
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in self.logs:
            log.close()  # type: ignore[attr-defined]

    def wait(self) -> int:
        while not self.stopping:
            for process in self.processes:
                code = process.poll()
                if code is not None:
                    return code or 1
            time.sleep(0.5)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate and print the process plan")
    args = parser.parse_args()
    environment = load_environment()
    try:
        plan = build_runtime_plan(ROOT, environment)
    except RuntimeConfigurationError as error:
        parser.error(str(error))
    if args.check:
        print("infrastructure:", ", ".join(plan.infrastructure))
        for process in plan.processes:
            print(f"{process.name}: {render_command(process.command)}")
        return 0

    RUNTIME_DIR.mkdir(exist_ok=True)
    with (RUNTIME_DIR / "paper-runtime.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("paper runtime is already managed by another process") from None
        lock.write(str(os.getpid()))
        lock.flush()
        runtime = PaperRuntime(environment)

        def stop(_signum: int, _frame: FrameType | None) -> None:
            runtime.stop()

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            runtime.start()
            print("paper runtime ready: http://127.0.0.1:3000", flush=True)
            return runtime.wait()
        finally:
            runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())
