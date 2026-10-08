#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

from amac.utils.exception import ExecuteFailed


class ExecProcess:
    def __init__(
            self, 
            executable, 
            workdir="", 
            omp_threads=1, 
            env={},
            prefix=""
        ):

        self.executable = Path(executable).expanduser() if executable else None
        self.workdir = Path(workdir).expanduser() if workdir else Path(".")
        self.prefix = prefix
        self.omp_threads = omp_threads
        self.env = env

    def execute(self, check=True, timeout=None):

        if self.executable is None:
            raise EnvironmentError("No executable configured")

        exe = self.executable.resolve()
        if not exe.is_file():
            raise FileNotFoundError(f"Executable not found: {exe}")
        if not os.access(exe, os.X_OK):
            raise PermissionError(f"Executable not runnable: {exe}")

        wd = self.workdir.resolve()
        if not wd.is_dir():
            raise NotADirectoryError(f"Working directory missing: {wd}")

        _env = {**os.environ, **self.env}

        try:
            result = subprocess.run(
                [str(exe)],
                cwd=str(wd),
                env=_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except OSError as err:
            raise EnvironmentError(f'Failed to execute "{exe}"') from err

        if check and result.returncode != 0:
            raise ExecuteFailed(
                f'Calculator "{self.prefix}" failed with return code '
                f"{result.returncode} in {wd}\nstderr:\n{result.stderr}"
            )

        return result













