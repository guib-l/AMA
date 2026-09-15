"""Tests of amac.engine.execute and of the run phase of FileIOSoftware."""

import json
import sys
import time
from pathlib import Path

import pytest

from amac.assets._dummy.dummy import DummySoftware
from amac.engine.context import RunContext
from amac.engine.execute import (
    ExecResult,
    LocalExecutor,
    build_environment,
    finalize_run_directory,
    make_run_directory,
)
from amac.exceptions import RunError
from amac.parameter.parameters import CalculationSpec, ExecutionSpec

PYTHON = sys.executable

SPAWN_AND_SLEEP = """\
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
with open("child.pid", "w") as stream:
    stream.write(str(child.pid))
time.sleep(10)
"""


class FailingDummy(DummySoftware):
    def command(self, ctx):
        return [PYTHON, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"]


class SleepingDummy(DummySoftware):
    def command(self, ctx):
        return [PYTHON, "-c", "import time; time.sleep(10)"]


class RedirectedDummy(DummySoftware):
    def stdout_file(self, ctx):
        return Path("dummy.log")


def python(code: str) -> list[str]:
    return [PYTHON, "-c", code]


def make_ctx(directory: Path, **exec_kwargs) -> RunContext:
    spec = CalculationSpec.from_kwargs(
        method="DFT",
        method_args={"variant": "PBE"},
        parameters={"BASIS": "sto-3g"},
    )
    exec_spec = ExecutionSpec(workdir=directory, **exec_kwargs)
    return RunContext(None, spec, exec_spec, directory)


def is_dead(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    # The process may vanish between opening and reading its stat file.
    except (FileNotFoundError, ProcessLookupError):
        return True
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def test_run_trivial_command(tmp_path):
    code = "open('out.txt', 'w').write('x'); print('hello')"
    result = LocalExecutor().run(python(code), tmp_path)
    assert isinstance(result, ExecResult)
    assert (result.return_code, result.stdout, result.stderr) == (0, "hello\n", "")
    assert result.duration > 0
    assert result.stdout_file is None
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "x"


def test_non_zero_return_code_does_not_raise(tmp_path):
    code = "import sys; sys.stderr.write('bad'); sys.exit(3)"
    result = LocalExecutor().run(python(code), tmp_path)
    assert (result.return_code, result.stderr) == (3, "bad")


def test_stdin_and_stdout_redirection(tmp_path):
    (tmp_path / "in.txt").write_text("from stdin", encoding="utf-8")
    code = "import sys; print(sys.stdin.read().upper())"
    result = LocalExecutor().run(
        python(code), tmp_path, stdin="in.txt", stdout_file="out.log"
    )
    assert result.stdout is None
    assert result.stdout_file == tmp_path / "out.log"
    assert result.stdout_file.read_text(encoding="utf-8") == "FROM STDIN\n"


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="needs /proc")
def test_timeout_kills_process_group(tmp_path):
    start = time.monotonic()
    with pytest.raises(RunError, match="timed out"):
        LocalExecutor().run(python(SPAWN_AND_SLEEP), tmp_path, timeout=0.4)
    assert time.monotonic() - start < 1.0
    pid = int((tmp_path / "child.pid").read_text(encoding="utf-8"))
    deadline = time.monotonic() + 0.5
    while not is_dead(pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert is_dead(pid)


@pytest.mark.parametrize(
    ("env", "expected"),
    [({}, "3"), ({"OMP_NUM_THREADS": "1"}, "1")],
    ids=["from-cpu", "overridden"],
)
def test_omp_num_threads(tmp_path, env, expected):
    environment = build_environment(3, env)
    assert environment["OMP_NUM_THREADS"] == expected
    code = "import os; print(os.environ['OMP_NUM_THREADS'])"
    result = LocalExecutor().run(python(code), tmp_path, env=environment)
    assert result.stdout == f"{expected}\n"


@pytest.mark.parametrize(
    ("cmd", "error"),
    [
        (f"{PYTHON} -c pass", TypeError),
        ((PYTHON, "-c", "pass"), TypeError),
        ([PYTHON, "-c", 1], TypeError),
        ([], ValueError),
    ],
    ids=["str", "tuple", "non-str-item", "empty"],
)
def test_invalid_command(tmp_path, cmd, error):
    with pytest.raises(error):
        LocalExecutor().run(cmd, tmp_path)


def test_missing_program(tmp_path):
    with pytest.raises(RunError, match="Cannot start"):
        LocalExecutor().run([str(tmp_path / "missing")], tmp_path)


@pytest.mark.parametrize(
    ("image", "relative"),
    [(None, "calc"), (0, "calc/image_000"), (12, "calc/image_012")],
)
def test_make_run_directory(tmp_path, image, relative):
    exec_spec = ExecutionSpec(workdir=tmp_path, label="calc")
    directory = make_run_directory(exec_spec, image)
    assert directory == tmp_path / relative
    assert directory.is_dir()


def test_make_run_directory_default_label(tmp_path):
    assert make_run_directory(ExecutionSpec(workdir=tmp_path)) == tmp_path / "amac"


@pytest.mark.parametrize("label", ["../calc", "a/b", ".."])
def test_make_run_directory_invalid_label(tmp_path, label):
    with pytest.raises(ValueError, match="label"):
        make_run_directory(ExecutionSpec(workdir=tmp_path, label=label))


def test_make_run_directory_refuses_non_empty(tmp_path):
    (tmp_path / "calc").mkdir()
    exec_spec = ExecutionSpec(workdir=tmp_path, label="calc")
    assert make_run_directory(exec_spec) == tmp_path / "calc"
    (tmp_path / "calc" / "old.txt").write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite"):
        make_run_directory(exec_spec)
    overwrite = ExecutionSpec(workdir=tmp_path, label="calc", overwrite=True)
    reused = make_run_directory(overwrite)
    assert (reused / "old.txt").exists()


def test_overwrite_round_trip():
    exec_spec = ExecutionSpec(overwrite=True, keep_files=False)
    assert ExecutionSpec.from_dict(exec_spec.to_dict()) == exec_spec


def test_finalize_copies_to_outdir(tmp_path):
    exec_spec = ExecutionSpec(
        workdir=tmp_path / "work", outdir=tmp_path / "out", label="calc"
    )
    directory = make_run_directory(exec_spec, 0)
    (directory / "result.txt").write_text("42", encoding="utf-8")
    copy = finalize_run_directory(directory, exec_spec)
    assert copy == tmp_path / "out" / "calc" / "image_000"
    assert (copy / "result.txt").read_text(encoding="utf-8") == "42"
    assert (directory / "result.txt").exists()


@pytest.mark.parametrize("outdir", [None, "out"])
def test_finalize_removes_files_unless_kept(tmp_path, outdir):
    exec_spec = ExecutionSpec(
        workdir=tmp_path / "work",
        outdir=None if outdir is None else tmp_path / outdir,
        label="calc",
        keep_files=False,
    )
    directory = make_run_directory(exec_spec)
    (directory / "result.txt").write_text("42", encoding="utf-8")
    copy = finalize_run_directory(directory, exec_spec)
    assert not directory.exists()
    assert (tmp_path / "work").is_dir()
    if outdir is None:
        assert copy is None
    else:
        assert (copy / "result.txt").exists()


def test_dummy_prepare_run_collect(tmp_path):
    ctx = make_ctx(tmp_path, cpu=2)
    software = DummySoftware()
    software.prepare(ctx)
    software.run(ctx)
    software.collect(ctx)
    assert ctx.return_code == 0
    assert ctx.stdout == "dummy: done\n"
    assert ctx.timings["run"] > 0
    assert ctx.files == {"output.json": tmp_path / "output.json"}
    output = json.loads(ctx.files["output.json"].read_text(encoding="utf-8"))
    assert output == {"energy": -1.0, "forces": [], "keywords": ["PBE"]}


def test_dummy_stdout_redirection(tmp_path):
    ctx = make_ctx(tmp_path)
    software = RedirectedDummy()
    software.prepare(ctx)
    software.run(ctx)
    assert ctx.stdout is None
    assert (tmp_path / "dummy.log").read_text(encoding="utf-8") == "dummy: done\n"


def test_dummy_non_zero_return_code_raises(tmp_path):
    ctx = make_ctx(tmp_path)
    with pytest.raises(RunError, match="code 3") as excinfo:
        FailingDummy().run(ctx)
    assert excinfo.value.ctx is ctx
    assert (ctx.return_code, ctx.stderr) == (3, "bad")


def test_dummy_non_zero_return_code_recorded(tmp_path):
    ctx = make_ctx(tmp_path, raise_on_error=False)
    FailingDummy().run(ctx)
    assert (ctx.return_code, ctx.stderr) == (3, "bad")


def test_dummy_timeout(tmp_path):
    ctx = make_ctx(tmp_path, timeout=0.2, raise_on_error=False)
    with pytest.raises(RunError, match="timed out") as excinfo:
        SleepingDummy().run(ctx)
    assert excinfo.value.ctx is ctx
    assert ctx.return_code is None
