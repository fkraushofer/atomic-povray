"""Asynchronous, latest-request-wins POV-Ray preview rendering."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

from ..backends.povray_sdl import (
    RenderConfig,
    RenderResult,
    _hidden_windows_process_kwargs,
    write_ini,
    write_scene,
)
from ..scene import Scene

@dataclass(frozen=True)
class RenderTimings:
    generation: int
    full_quality: bool
    scene_export_s: float
    process_s: float
    total_s: float


@dataclass(frozen=True)
class InteractiveRenderResult:
    png: bytes
    timings: RenderTimings
    render_result: RenderResult


@dataclass(frozen=True)
class _RenderJob:
    generation: int
    scene: Scene
    config: RenderConfig
    full_quality: bool


class _LatestRenderController:
    """Serialize POV-Ray jobs while retaining only the latest pending state."""

    def __init__(
        self,
        *,
        output: Path,
        on_result: Callable[[InteractiveRenderResult], None],
        on_status: Callable[[str], None],
        debounce_s: float,
        max_wait_s: float,
    ) -> None:
        self.output = output
        self.on_result = on_result
        self.on_status = on_status
        self.debounce_s = debounce_s
        self.max_wait_s = max_wait_s
        self.generation = 0
        self.pending: _RenderJob | None = None
        self.worker: asyncio.Task[None] | None = None
        self.start_task: asyncio.Task[None] | None = None
        self.first_pending_at: float | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.last_error: str | None = None

    @property
    def is_rendering(self) -> bool:
        return self.worker is not None and not self.worker.done()

    def request(
        self,
        scene: Scene,
        config: RenderConfig,
        *,
        full_quality: bool = False,
        immediate: bool = False,
    ) -> int:
        self.generation += 1
        job = _RenderJob(self.generation, scene, config, full_quality)
        self.pending = job
        if self.is_rendering:
            self.on_status(
                f"rendering; request {job.generation} is pending"
            )
            return job.generation
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self.first_pending_at is None:
            self.first_pending_at = now
        if self.start_task is not None:
            self.start_task.cancel()
        deadline = min(
            now + self.debounce_s,
            self.first_pending_at + self.max_wait_s,
        )
        delay = 0.0 if immediate else max(0.0, deadline - now)
        self.start_task = asyncio.create_task(self._start_after(delay))
        mode = "full-quality render" if full_quality else "preview"
        self.on_status(f"{mode} {job.generation} queued")
        return job.generation

    async def _start_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if not self.is_rendering and self.pending is not None:
            self.first_pending_at = None
            self.worker = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            while self.pending is not None:
                job = self.pending
                self.pending = None
                mode = "full quality" if job.full_quality else "preview"
                self.on_status(f"rendering {mode} {job.generation}")
                try:
                    result = await asyncio.to_thread(self._render_sync, job)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    detail = str(error).strip() or type(error).__name__
                    self.last_error = f"{type(error).__name__}: {detail}"
                    self.on_status(f"render failed: {self.last_error}")
                    continue
                self.last_error = None
                self.on_result(result)
                timing = result.timings
                if job.generation == self.generation and self.pending is None:
                    self.on_status(
                        f"{mode} {job.generation}: {timing.total_s:.3f} s total "
                        f"({timing.scene_export_s:.3f} s export, "
                        f"{timing.process_s:.3f} s POV-Ray)"
                    )
                else:
                    self.on_status(
                        f"showing stale {mode} {job.generation}; "
                        f"request {self.generation} is pending"
                    )
        finally:
            self.process = None

    def _render_sync(self, job: _RenderJob) -> InteractiveRenderResult:
        total_start = perf_counter()
        temporary: tempfile.TemporaryDirectory[str] | None = None
        if job.full_quality:
            image_path = self.output
            image_path.parent.mkdir(parents=True, exist_ok=True)
            scene_path = image_path.with_suffix(".pov")
            ini_path = image_path.with_suffix(".ini")
        else:
            temporary = tempfile.TemporaryDirectory(
                prefix="atomic-povray-preview-"
            )
            job_dir = Path(temporary.name)
            image_path = job_dir / "preview.png"
            scene_path = job_dir / "preview.pov"
            ini_path = job_dir / "preview.ini"
        try:
            export_start = perf_counter()
            write_scene(
                job.scene,
                scene_path,
                width=job.config.width,
                height=job.config.height,
                povray_version=job.config.povray_version,
                max_trace_level=job.config.max_trace_level,
                radiosity=job.config.radiosity,
                additional_pov=job.config.additional_pov,
                profile=job.config.profile,
            )
            write_ini(
                scene_path,
                image_path,
                job.config,
                filename=ini_path,
            )
            export_s = perf_counter() - export_start
            executable_name = Path(job.config.executable).name.lower()
            if executable_name.startswith(("pvengine", "povwin")):
                command = (
                    job.config.executable,
                    "/NR",
                    "/RENDER",
                    ini_path.name,
                    "/EXIT",
                )
            else:
                command = (job.config.executable, ini_path.name)
            kwargs = (
                _hidden_windows_process_kwargs()
                if not job.config.display
                else {}
            )
            process_start = perf_counter()
            try:
                process = subprocess.Popen(
                    command,
                    cwd=image_path.parent.resolve(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **kwargs,
                )
            except Exception as error:
                detail = str(error).strip() or type(error).__name__
                raise RuntimeError(
                    f"could not start POV-Ray ({type(error).__name__}: {detail}); "
                    f"command={command!r}"
                ) from error
            self.process = process
            try:
                stdout_bytes, stderr_bytes = process.communicate()
            finally:
                self.process = None
            process_s = perf_counter() - process_start
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            if process.returncode != 0:
                detail = stderr.strip() or stdout.strip() or "no process output"
                raise RuntimeError(
                    f"POV-Ray exited with code {process.returncode}: {detail}; "
                    f"command={command!r}"
                )
            if not image_path.is_file() or image_path.stat().st_size == 0:
                raise RuntimeError(
                    "POV-Ray exited successfully but did not create a non-empty PNG; "
                    f"command={command!r}; stdout={stdout.strip()!r}; "
                    f"stderr={stderr.strip()!r}"
                )
            png = image_path.read_bytes()
            render_result = RenderResult(
                image_path=image_path,
                scene_path=scene_path,
                ini_path=ini_path,
                command=command,
                stdout=stdout,
                stderr=stderr,
            )
            timings = RenderTimings(
                job.generation,
                job.full_quality,
                export_s,
                process_s,
                perf_counter() - total_start,
            )
            return InteractiveRenderResult(png, timings, render_result)
        finally:
            if temporary is not None:
                temporary.cleanup()

    async def cancel(self) -> None:
        self.pending = None
        self.first_pending_at = None
        if self.start_task is not None:
            self.start_task.cancel()
        process = self.process
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(process.wait), 2.0)
            except TimeoutError:
                process.kill()
                await asyncio.to_thread(process.wait)
        if self.worker is not None and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        self.on_status("render cancelled")
