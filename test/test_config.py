"""Tests of the machine configuration file and of executable resolution.

AMAC reads no environment variable: the file is given to a calculator with
``AMAC(config=...)`` or to the process with ``amac.set_config``, and without
either there is no configuration at all.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets.demonnano.demonnano import DeMonNano
from amac.config import Config, clear_config_cache, config_path, load_config
from amac.engine import registry
from amac.engine.drivers import Driver
from amac.engine.registry import get_software
from amac.engine.software import ExecutableLocation, FileIOSoftware, Software
from amac.exceptions import ConfigurationError, ExecutableNotFoundError
from amac.parameter.parameters import ExecutionSpec

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}
PROGRAM = "dftb+"
# A registered software, used where the configuration file needs a known name.
KNOWN = "DFTBP"
SOURCES = ("explicit", "file")
SCRIPT = """\
#!/bin/sh
echo "A=$AMAC_TEST_A B=$AMAC_TEST_B C=$AMAC_TEST_C OMP=$OMP_NUM_THREADS"
"""


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def write_config(path: Path, content: dict | list | str, default: bool = True) -> Path:
    """Write ``content`` to ``path``, as JSON unless it is already a string.

    The file already read is forgotten; ``default`` also makes it the
    configuration file of the process, as ``amac.set_config`` does.
    """
    if not isinstance(content, str):
        content = json.dumps(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    clear_config_cache()
    if default:
        amac.set_config(path)
    return path


def software_config(name: str, **section) -> dict:
    """Return a configuration with the single section ``software.<name>``."""
    return {"software": {name: section}}


def write_program(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SCRIPT, encoding="utf-8")
    path.chmod(0o755)
    return path


def give_executable(source, value, config) -> dict[str, str]:
    """Set ``value`` in ``source``; return the matching AMAC keyword arguments."""
    match source:
        case "explicit":
            return {"executable": value}
        case "file":
            write_config(config, software_config("FAKEPROG", executable=value))
    return {}


def source_label(source, config) -> str:
    return "executable=" if source == "explicit" else f"file:{config}"


@pytest.fixture
def config(tmp_path) -> Path:
    """Path of a configuration file; nothing is written and AMAC has none yet."""
    return tmp_path / "config-amac.json"


@pytest.fixture
def fake_software(monkeypatch):
    """FILEIO software requiring an executable, which it runs without arguments."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())

    class FakeProgram(FileIOSoftware):
        """Software without ``doc.json``: it writes nothing and runs one command."""

        NAME = "FAKEPROG"
        ALIASES = ("fake-prog",)
        REQUIRES_EXECUTABLE = True

        def prepare(self, ctx):
            """Write no input file: only the executable matters here."""

        def collect(self, ctx):
            """Produce no file: only the executable matters here."""

        def command(self, ctx):
            return [self.resolve_executable(ctx.exec_spec)]

    return registry.register_software(FakeProgram)


@pytest.fixture
def program(tmp_path):
    """Executable script printing some variables of its environment."""
    return write_program(tmp_path / "bin" / PROGRAM)


@pytest.fixture
def program_in_path(program, monkeypatch):
    """Put the directory of ``program`` (named like DFTB+) alone in PATH."""
    monkeypatch.setenv("PATH", str(program.parent))
    return program


def test_without_a_configuration_file():
    """No file given: an empty configuration, and no error anywhere."""
    assert config_path() is None
    assert load_config() == Config(None, {}, None)
    assert amac.which(KNOWN) is None
    assert get_software(KNOWN)().configured_env() == {}


def test_set_config_gives_the_file_of_the_process(config):
    write_config(config, software_config(KNOWN, executable="/opt/prog"))
    assert config_path() == config
    assert amac.which(KNOWN) == ExecutableLocation("/opt/prog", f"file:{config}")
    amac.set_config(None)
    assert amac.which(KNOWN) is None


def test_config_of_a_calculator_wins_over_set_config(tmp_path, config):
    write_config(config, software_config(KNOWN, executable="/process/prog"))
    other = write_config(
        tmp_path / "other.json",
        software_config(KNOWN, executable="/explicit/prog"),
        default=False,
    )
    calc = AMAC(software=KNOWN, config=other, method="TIGHT_BINDING", validate="off")
    assert calc.config == other
    assert calc.software.resolve_executable(calc.exec_spec) == "/explicit/prog"
    assert amac.which(KNOWN, config=other).path == "/explicit/prog"
    # The process still has its own file, which the calculator did not change.
    assert amac.which(KNOWN).path == "/process/prog"


@pytest.mark.parametrize("given", ["process", "calculator"])
def test_missing_file_raises(tmp_path, given):
    missing = tmp_path / "missing.json"
    if given == "process":
        amac.set_config(missing)
        with pytest.raises(ConfigurationError, match="does not exist") as info:
            load_config()
    else:
        with pytest.raises(ConfigurationError, match="does not exist") as info:
            AMAC(software=KNOWN, config=missing, method="TIGHT_BINDING", validate="off")
    assert str(missing) in str(info.value)


def test_alias_resolved_to_canonical_name(config):
    write_config(
        config,
        software_config(
            "DFTB+", executable="/opt/dftb/dftb+", env={"DFTB_PREFIX": "/data/slako/"}
        ),
    )
    settings = load_config().for_software("DFTBP")
    assert settings.executable == "/opt/dftb/dftb+"
    assert settings.env == {"DFTB_PREFIX": "/data/slako/"}
    assert amac.which("dftb+") == ExecutableLocation(
        "/opt/dftb/dftb+", f"file:{config}"
    )


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ('{"software": {"DFTBP": {}}', "Invalid JSON"),
        ('[software.DFTBP]\nexecutable = "x"\n', "Invalid JSON"),
        ([], "top level must be a JSON object"),
        ('"software"', "top level must be a JSON object"),
        ({"machine": {"cpu": 4}}, "unknown section"),
        ({"software": "DFTBP"}, "must be an object of"),
        ({"software": {"DFTBP": 3}}, r"\[software.DFTBP\] must be an object"),
        (software_config(KNOWN, cpu=4), "unknown key.*cpu"),
        (software_config(KNOWN, executable=3), "non-empty string"),
        (software_config(KNOWN, executable=""), "non-empty string"),
        (software_config(KNOWN, env={"A": 1}), "env must be an object of strings"),
        (software_config(KNOWN, env="A=1"), "env must be an object of strings"),
        (software_config("NOPE", executable="x"), "Unknown software 'NOPE'"),
        ({"workdir": 3}, "workdir must be a non-empty string"),
        ({"workdir": ""}, "workdir must be a non-empty string"),
        ({"workdir": "runs"}, "must be an absolute path"),
        (
            {"software": {"DFTBP": {"executable": "a"}, "DFTB+": {"executable": "b"}}},
            "both configure DFTBP",
        ),
        ('{"software": {}, "software": {}}', "duplicated key 'software'"),
        (
            '{"software": {"DFTBP": {}, "DFTBP": {}}}',
            "duplicated key 'DFTBP'",
        ),
        (
            '{"software": {"DFTBP": {"executable": "/a", "executable": "/b"}}}',
            "duplicated key 'executable'",
        ),
        (
            '{"software": {"DFTBP": {"env": {"A": "1", "A": "2"}}}}',
            "duplicated key 'A'",
        ),
    ],
)
def test_invalid_file(config, content, match):
    write_config(config, content)
    with pytest.raises(ConfigurationError, match=match) as info:
        load_config()
    assert str(config) in str(info.value)


def test_null_executable_is_not_set(config):
    write_config(config, software_config(KNOWN, executable=None))
    assert load_config().for_software(KNOWN).executable is None


def test_workdir_of_the_file_is_the_default_root(tmp_path, config, fake_software):
    runs = tmp_path / "runs"
    write_config(config, {"workdir": str(runs), "software": {}})
    assert load_config().workdir == runs
    assert AMAC(software="FAKEPROG", validate="off", **PARAMETERS).workdir == runs
    # A workdir given to the calculator, and one given to execute(), win over it.
    given = AMAC(
        software="FAKEPROG", workdir=tmp_path / "given", validate="off", **PARAMETERS
    )
    assert given.workdir == tmp_path / "given"
    assert given._exec_spec_for({"workdir": tmp_path / "call"}).workdir == (
        tmp_path / "call"
    )


def test_workdir_is_expanded_and_absent_by_default(tmp_path, config, fake_software):
    write_config(config, {"workdir": "~/amac-runs", "software": {}})
    assert load_config().workdir == Path.home() / "amac-runs"
    write_config(config, {"workdir": None, "software": {}})
    assert load_config().workdir is None
    calc = AMAC(software="FAKEPROG", validate="off", **PARAMETERS)
    assert calc.exec_spec.workdir == Path(".")


def test_requires_executable_flags():
    assert Software.REQUIRES_EXECUTABLE is False
    assert FileIOSoftware.REQUIRES_EXECUTABLE is True
    # deMonNano runs in process, but through an executable of its own library.
    assert DeMonNano.REQUIRES_EXECUTABLE is True
    assert get_software("DFTB+").REQUIRES_EXECUTABLE is True
    assert not hasattr(Software, "DEFAULT_EXECUTABLE")
    # No source is ever an environment variable.
    assert not hasattr(Software, "EXECUTABLE_ENV")


def test_precedence(fake_software, config):
    def location(calc):
        return calc.software.locate_executable(calc.exec_spec)

    assert location(AMAC(software="fakeprog", validate="off", **PARAMETERS)) is None
    write_config(config, software_config("fake-prog", executable="/file/prog"))
    assert amac.which("FAKEPROG") == ExecutableLocation("/file/prog", f"file:{config}")
    amac.configure(software="FAKEPROG", executable="/configured/prog")
    configured = amac.calculator(PARAMETERS, "FAKEPROG", validate="off")
    assert location(configured) == ExecutableLocation(
        "/configured/prog", "executable="
    )
    explicit = amac.calculator(
        PARAMETERS, "FAKEPROG", validate="off", executable="/explicit/prog"
    )
    assert location(explicit).path == "/explicit/prog"
    # which() ignores configure(): it only reads the configuration file.
    assert amac.which("FAKEPROG").path == "/file/prog"


def test_path_never_searched(fake_software, program_in_path, tmp_path, config):
    # A program named "dftb+" sits in PATH, and neither software finds it.
    assert amac.which("DFTB+") is None
    assert amac.which("FAKEPROG") is None
    write_config(config, {"software": {}})
    calc = AMAC(
        software="FAKEPROG", workdir=tmp_path / "work", validate="off", **PARAMETERS
    )
    assert calc.software.resolve_executable(calc.exec_spec) is None
    expected = (
        "FAKEPROG: executable not found. Tried: executable=/configure(), "
        f"{config} [software.FAKEPROG]. Set one of them to the absolute path of "
        "the executable"
    )
    with pytest.raises(ExecutableNotFoundError) as info:
        calc.execute(water(), raise_on_error=False)
    assert str(info.value) == expected
    assert not (tmp_path / "work").exists()


def test_message_without_a_configuration_file(fake_software, tmp_path):
    """Nothing to read: the message says how to give a configuration file."""
    calc = AMAC(
        software="FAKEPROG", workdir=tmp_path / "work", validate="off", **PARAMETERS
    )
    with pytest.raises(ExecutableNotFoundError, match="amac.set_config"):
        calc.execute(water())
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("value", [PROGRAM, f"bin/{PROGRAM}"])
def test_non_absolute_executable_rejected(
    fake_software, program_in_path, tmp_path, monkeypatch, config, source, value
):
    monkeypatch.chdir(tmp_path)
    kwargs = give_executable(source, value, config)
    calc = AMAC(
        software="FAKEPROG", workdir=tmp_path / "work", validate="off", **PARAMETERS
    )
    exec_spec = replace(calc.exec_spec, **kwargs)
    assert calc.software.resolve_executable(exec_spec) == value
    with pytest.raises(ExecutableNotFoundError, match="must be an absolute") as info:
        calc.execute(water(), **kwargs)
    assert f"'{value}' ({source_label(source, config)})" in str(info.value)
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.filterwarnings("ignore:No handler declared")
def test_tilde_expanded(fake_software, tmp_path, monkeypatch, config, source):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    script = write_program(tmp_path / "home" / "opt" / "orca" / "orca")
    kwargs = give_executable(source, "~/opt/orca/orca", config)
    calc = AMAC(
        software="FAKEPROG", workdir=tmp_path / "work", validate="off", **PARAMETERS
    )
    result = calc.execute(water(), **kwargs)
    assert result.success
    assert result.context.metadata["executable"] == {
        "path": str(script),
        "source": source_label(source, config),
    }


@pytest.mark.parametrize("name", ["missing", "not-executable"])
def test_unusable_executable(fake_software, tmp_path, name):
    (tmp_path / "not-executable").write_text("", encoding="utf-8")
    calc = AMAC(
        software="FAKEPROG", workdir=tmp_path / "work", validate="off", **PARAMETERS
    )
    with pytest.raises(ExecutableNotFoundError, match="does not exist or is not"):
        calc.execute(water(), executable=str(tmp_path / name))
    assert not (tmp_path / "work").exists()


@pytest.mark.filterwarnings("ignore:No handler declared")
def test_run_environment_and_provenance(
    fake_software, program, tmp_path, monkeypatch, config
):
    write_config(
        config,
        software_config(
            "FAKEPROG",
            executable=str(program),
            env={"AMAC_TEST_A": "file", "AMAC_TEST_B": "file", "OMP_NUM_THREADS": "7"},
        ),
    )
    # The subprocess still inherits the environment of the shell: C comes from it.
    for name in ("AMAC_TEST_A", "AMAC_TEST_B", "AMAC_TEST_C"):
        monkeypatch.setenv(name, "os")
    calc = AMAC(
        software="FAKEPROG",
        validate="off",
        workdir=tmp_path / "work",
        cpu=2,
        env={"AMAC_TEST_B": "spec"},
        **PARAMETERS,
    )
    result = calc.execute(water())
    assert result.success
    assert result.context.stdout.strip() == "A=file B=spec C=os OMP=7"
    executable = result.context.metadata["executable"]
    assert executable == {"path": str(program), "source": f"file:{config}"}
    assert json.loads(json.dumps(executable)) == executable


@pytest.mark.filterwarnings("ignore:No handler declared")
def test_file_env_not_stored(fake_software, program, tmp_path, config):
    write_config(config, software_config("FAKEPROG", env={"SECRET": "from-file"}))
    calc = AMAC(
        software="FAKEPROG",
        validate="off",
        workdir=tmp_path / "work",
        executable=str(program),
        env={"B": "spec"},
        **PARAMETERS,
    )
    result = calc.execute(water())
    assert calc.exec_spec.env == {"B": "spec"}
    assert calc.to_dict(mask_secrets=False)["exec_spec"]["env"] == {"B": "spec"}
    assert result.provenance["exec_spec"]["env"] == {"B": "***"}
    stored = calc.store(tmp_path / "results").read_text(encoding="utf-8")
    assert "SECRET" not in stored and "from-file" not in stored


def test_driver_settings_include_file_env(fake_software, config):
    """A driver sees the ``env`` of the file, under the one of the spec."""

    class SettingsDriver(Driver):
        NAME = "settings-test"
        PHASES = frozenset({"collect"})

        def collect(self, software, ctx):
            """Collect nothing: only the settings matter here."""

    write_config(config, software_config("FAKEPROG", env={"A": "file", "B": "file"}))
    settings = SettingsDriver().execution_settings(
        fake_software(), ExecutionSpec(env={"B": "spec"})
    )
    assert settings["env"] == {"A": "file", "B": "spec"}


def test_reset_configuration_clears_cache_and_forgets_the_file(fake_software, config):
    write_config(config, software_config("FAKEPROG", executable="/first/prog"))
    assert amac.which("FAKEPROG").path == "/first/prog"
    config.write_text(
        json.dumps(software_config("FAKEPROG", executable="/second/prog")),
        encoding="utf-8",
    )
    assert amac.which("FAKEPROG").path == "/first/prog"
    amac.reset_configuration()
    # The file is forgotten too: AMAC is left without any configuration.
    assert config_path() is None
    amac.set_config(config)
    assert amac.which("FAKEPROG").path == "/second/prog"
