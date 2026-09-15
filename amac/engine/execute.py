"""Local execution of external programs and management of run directories."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from amac.exceptions import RunError

if TYPE_CHECKING:
    from amac.parameter.parameters import ExecutionSpec

DEFAULT_LABEL = "amac"
IMAGE_DIRECTORY = "image_{index:03d}"


@dataclass(frozen=True)
class ExecResult:
    """Outcome of a command that ran to completion.

    Attributes:
        return_code: Exit code; negative when the process was killed by a signal.
        stdout: Standard output, ``None`` when redirected to ``stdout_file``.
        stderr: Standard error.
        duration: Wall-clock duration in seconds.
        stdout_file: File that received the standard output, if any.
    """

    return_code: int
    stdout: str | None
    stderr: str
    duration: float
    stdout_file: Path | None = None


def build_environment(
    cpu: int, env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Return the environment of a run.

    The current environment is completed by ``OMP_NUM_THREADS`` set to ``cpu``, then
    updated with ``env``, which may therefore override both.

    Args:
        cpu: Number of cores.
        env: Additional variables, e.g. ``ExecutionSpec.env``.

    Returns:
        A new dict.
    """
    return {**os.environ, "OMP_NUM_THREADS": str(cpu), **(env or {})}


class LocalExecutor:
    """Runs a command synchronously on the local machine (POSIX only)."""

    def run(
        self,
        cmd: list[str],
        cwd: str | Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        stdin: str | Path | None = None,
        stdout_file: str | Path | None = None,
    ) -> ExecResult:
        """Run ``cmd`` in ``cwd`` and wait for it to finish.

        The command is never run through a shell. The process starts in a new
        session, so that a timeout kills the program and every process it spawned.

        Args:
            cmd: Program and its arguments.
            cwd: Working directory.
            env: Complete environment of the process, ``None`` to inherit the
                current one (see :func:`build_environment`).
            timeout: Maximum duration in seconds, ``None`` for no limit.
            stdin: File fed to the standard input, relative to ``cwd``; the
                standard input is empty when ``None``.
            stdout_file: File receiving the standard output, relative to ``cwd``;
                the output is captured in ``ExecResult.stdout`` when ``None``.

        Returns:
            The result, whatever the exit code.

        Raises:
            TypeError: If ``cmd`` is not a list of str or path-like objects.
            ValueError: If ``cmd`` is empty.
            FileNotFoundError: If ``stdin`` does not exist.
            RunError: If the program cannot be started, or exceeds ``timeout``; in
                the latter case its process group is killed first.
        """
        _check_command(cmd)
        cwd = Path(cwd)
        output = None if stdout_file is None else cwd / stdout_file
        with ExitStack() as stack:
            stdin_stream: Any = subprocess.DEVNULL
            if stdin is not None:
                stdin_stream = stack.enter_context((cwd / stdin).open("rb"))
            stdout_stream: Any = subprocess.PIPE
            if output is not None:
                stdout_stream = stack.enter_context(output.open("wb"))
            start = time.perf_counter()
            try:
                process = stack.enter_context(
                    subprocess.Popen(
                        cmd,
                        cwd=cwd,
                        env=env,
                        stdin=stdin_stream,
                        stdout=stdout_stream,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        start_new_session=True,
                    )
                )
            except OSError as err:
                raise RunError(f"Cannot start {cmd[0]!s}: {err}") from err
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(process)
                raise RunError(f"{cmd[0]!s} timed out after {timeout} s") from None
            duration = time.perf_counter() - start
        return ExecResult(process.returncode, stdout, stderr, duration, output)


def make_run_directory(exec_spec: ExecutionSpec, image: int | None = None) -> Path:
    """Create the directory of a run and return it.

    The directory is ``workdir/<label>`` for a single image and
    ``workdir/<label>/image_XXX`` for the image ``XXX`` of a multi-image run.
    ``label`` defaults to :data:`DEFAULT_LABEL`.

    Args:
        exec_spec: Execution specification (``workdir``, ``label``, ``overwrite``).
        image: Index of the image, ``None`` for a single-image run.

    Returns:
        The existing or created directory.

    Raises:
        ValueError: If ``label`` is not a plain directory name, or ``image`` is
            negative.
        FileExistsError: If the directory is not empty and ``overwrite`` is false,
            or if the path exists and is not a directory.
    """
    label = exec_spec.label or DEFAULT_LABEL
    if label in {".", ".."} or Path(label).name != label:
        raise ValueError(f"label must be a plain directory name, got {label!r}")
    directory = exec_spec.workdir / label
    if image is not None:
        if image < 0:
            raise ValueError(f"image index must be >= 0, got {image}")
        directory /= IMAGE_DIRECTORY.format(index=image)
    if directory.is_dir() and any(directory.iterdir()) and not exec_spec.overwrite:
        raise FileExistsError(
            f"{directory} is not empty; use overwrite=True to reuse it"
        )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def finalize_run_directory(directory: Path, exec_spec: ExecutionSpec) -> Path | None:
    """Copy a run directory to ``outdir``, then remove it unless ``keep_files``.

    Call it once the produced files have been read: with ``keep_files=False`` the
    directory is removed, with or without ``outdir``.

    Args:
        directory: Directory returned by :func:`make_run_directory`.
        exec_spec: Execution specification (``workdir``, ``outdir``,
            ``keep_files``).

    Returns:
        The copy, placed at the same path relative to ``outdir`` as ``directory``
        relative to ``workdir``; ``None`` when ``outdir`` is not set.

    Raises:
        ValueError: If ``outdir`` is set and ``directory`` is not inside
            ``workdir``.
    """
    destination = None
    if exec_spec.outdir is not None:
        destination = exec_spec.outdir / Path(directory).relative_to(exec_spec.workdir)
        shutil.copytree(directory, destination, dirs_exist_ok=True)
    if not exec_spec.keep_files:
        shutil.rmtree(directory)
    return destination


def _check_command(cmd: Any) -> None:
    if not isinstance(cmd, list):
        raise TypeError(f"cmd must be a list, got {type(cmd).__name__}")
    if not cmd:
        raise ValueError("cmd must not be empty")
    if not all(isinstance(arg, str | os.PathLike) for arg in cmd):
        raise TypeError("cmd items must be str or path-like objects")


def _kill_group(process: subprocess.Popen[str]) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
