"""Tests of the machine configuration file and of executable resolution."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets._dummy.dummy import DummyLibraryDriver, DummySoftware
from amac.assets._dummy.inprocess import DummyInProcess
from amac.config import clear_config_cache, config_path, load_config
from amac.engine import registry
from amac.engine.registry import get_software
from amac.engine.software import ExecutableLocation, FileIOSoftware, Software
from amac.exceptions import ConfigurationError, ExecutableNotFoundError
from amac.parameter.parameters import ExecutionSpec

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}
PROGRAM = "orca"
ENV_NAME = "FAKEPROG_EXECUTABLE"
SOURCES = ("explicit", "env", "file")
SCRIPT = """\
#!/bin/sh
echo "A=$AMAC_TEST_A B=$AMAC_TEST_B C=$AMAC_TEST_C OMP=$OMP_NUM_THREADS"
"""


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def write_config(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_program(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SCRIPT, encoding="utf-8")
    path.chmod(0o755)
    return path


def give_executable(source, value, monkeypatch, config) -> dict[str, str]:
    """Set ``value`` in ``source``; return the matching AMAC keyword arguments."""
    match source:
        case "explicit":
            return {"executable": value}
        case "env":
            monkeypatch.setenv(ENV_NAME, value)
        case "file":
            write_config(config, f'[software.FAKEPROG]\nexecutable = "{value}"\n')
    return {}


def source_label(source, config) -> str:
    return {"explicit": "executable=", "env": f"env:{ENV_NAME}"}.get(
        source, f"file:{config}"
    )


@pytest.fixture
def xdg_config():
    """Path of the default configuration file set by the conftest fixture."""
    return config_path()


@pytest.fixture
def fake_software(monkeypatch):
    """FILEIO software requiring an executable, which it runs without arguments."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())
    monkeypatch.delenv(ENV_NAME, raising=False)

    class FakeProgram(DummySoftware):
        NAME = "FAKEPROG"
        ALIASES = ("fake-prog",)
        REQUIRES_EXECUTABLE = True

        def command(self, ctx):
            return [self.resolve_executable(ctx.exec_spec)]

    return registry.register_software(FakeProgram)


@pytest.fixture
def program(tmp_path):
    """Executable script printing some variables of its environment."""
    return write_program(tmp_path / "bin" / PROGRAM)


@pytest.fixture
def program_in_path(program, monkeypatch):
    """Put the directory of ``program`` (named like ORCA) alone in PATH."""
    monkeypatch.setenv("PATH", str(program.parent))
    monkeypatch.delenv("ORCA_EXECUTABLE", raising=False)
    return program


def test_config_path_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path() == tmp_path / "xdg" / "amac" / "config.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert config_path() == tmp_path / "home" / ".config" / "amac" / "config.toml"
    monkeypatch.setenv("AMAC_CONFIG", str(tmp_path / "custom.toml"))
    assert config_path() == tmp_path / "custom.toml"


def test_missing_default_file_is_empty(xdg_config):
    config = load_config()
    assert (config.path, config.software) == (xdg_config, {})


def test_missing_amac_config_raises(tmp_path, monkeypatch):
    missing = tmp_path / "missing.toml"
    monkeypatch.setenv("AMAC_CONFIG", str(missing))
    with pytest.raises(ConfigurationError, match="does not exist") as info:
        load_config()
    assert str(missing) in str(info.value)


def test_amac_config_wins_over_xdg(tmp_path, monkeypatch, xdg_config):
    write_config(xdg_config, '[software.DUMMY]\nexecutable = "/xdg/prog"\n')
    custom = write_config(
        tmp_path / "custom.toml", '[software.DUMMY]\nexecutable = "/custom/prog"\n'
    )
    monkeypatch.setenv("AMAC_CONFIG", str(custom))
    assert load_config().for_software("DUMMY").executable == "/custom/prog"


def test_alias_resolved_to_canonical_name(xdg_config):
    write_config(
        xdg_config,
        '[software."DFTB+"]\nexecutable = "/opt/dftb/dftb+"\n'
        'env = { DFTB_PREFIX = "/data/slako/" }\n',
    )
    settings = load_config().for_software("DFTBP")
    assert settings.executable == "/opt/dftb/dftb+"
    assert settings.env == {"DFTB_PREFIX": "/data/slako/"}
    assert amac.which("dftb+") == ExecutableLocation(
        "/opt/dftb/dftb+", f"file:{xdg_config}"
    )


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("[software.DUMMY\n", "Invalid TOML"),
        ("[machine]\ncpu = 4\n", "unknown section"),
        ('software = "DUMMY"\n', "must be a table of"),
        ("[software]\nDUMMY = 3\n", r"\[software.DUMMY\] must be a table"),
        ("[software.DUMMY]\ncpu = 4\n", "unknown key.*cpu"),
        ("[software.DUMMY]\nexecutable = 3\n", "non-empty string"),
        ('[software.DUMMY]\nexecutable = ""\n', "non-empty string"),
        ("[software.DUMMY]\nenv = { A = 1 }\n", "env must be a table of strings"),
        ('[software.DUMMY]\nenv = "A=1"\n', "env must be a table of strings"),
        ('[software.NOPE]\nexecutable = "x"\n', "Unknown software 'NOPE'"),
        (
            '[software.DFTBP]\nexecutable = "a"\n'
            '[software."DFTB+"]\nexecutable = "b"\n',
            "both configure DFTBP",
        ),
    ],
)
def test_invalid_file(xdg_config, content, match):
    write_config(xdg_config, content)
    with pytest.raises(ConfigurationError, match=match) as info:
        load_config()
    assert str(xdg_config) in str(info.value)


def test_requires_executable_flags():
    assert Software.REQUIRES_EXECUTABLE is False
    assert FileIOSoftware.REQUIRES_EXECUTABLE is True
    assert DummyInProcess.REQUIRES_EXECUTABLE is False
    assert DummySoftware.REQUIRES_EXECUTABLE is False
    assert get_software("ORCA").REQUIRES_EXECUTABLE is True
    assert not hasattr(Software, "DEFAULT_EXECUTABLE")


def test_precedence(fake_software, monkeypatch, xdg_config):
    def location(calc):
        return calc.software.locate_executable(calc.exec_spec)

    assert location(AMAC(software="fakeprog", **PARAMETERS)) is None
    write_config(xdg_config, '[software.fake-prog]\nexecutable = "/file/prog"\n')
    clear_config_cache()
    assert amac.which("FAKEPROG") == ExecutableLocation(
        "/file/prog", f"file:{xdg_config}"
    )
    monkeypatch.setenv(ENV_NAME, "/env/prog")
    assert amac.which("FAKEPROG") == ExecutableLocation("/env/prog", f"env:{ENV_NAME}")
    amac.configure(software="FAKEPROG", executable="/configured/prog")
    configured = amac.calculator(PARAMETERS, "FAKEPROG")
    assert location(configured) == ExecutableLocation(
        "/configured/prog", "executable="
    )
    explicit = amac.calculator(PARAMETERS, "FAKEPROG", executable="/explicit/prog")
    assert location(explicit).path == "/explicit/prog"
    assert amac.which("FAKEPROG").path == "/env/prog"


def test_path_never_searched(fake_software, program_in_path, tmp_path, xdg_config):
    assert amac.which("ORCA") is None
    assert amac.which("FAKEPROG") is None
    calc = AMAC(software="FAKEPROG", workdir=tmp_path / "work", **PARAMETERS)
    assert calc.software.resolve_executable(calc.exec_spec) is None
    expected = (
        "FAKEPROG: executable not found. Tried: executable=/configure(), "
        f"${ENV_NAME}, {xdg_config} [software.FAKEPROG]. Set one of them to the "
        "absolute path of the executable"
    )
    with pytest.raises(ExecutableNotFoundError) as info:
        calc.execute(water(), raise_on_error=False)
    assert str(info.value) == expected
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("value", [PROGRAM, f"bin/{PROGRAM}"])
def test_non_absolute_executable_rejected(
    fake_software, program_in_path, tmp_path, monkeypatch, xdg_config, source, value
):
    monkeypatch.chdir(tmp_path)
    kwargs = give_executable(source, value, monkeypatch, xdg_config)
    calc = AMAC(software="FAKEPROG", workdir=tmp_path / "work", **PARAMETERS)
    exec_spec = replace(calc.exec_spec, **kwargs)
    assert calc.software.resolve_executable(exec_spec) == value
    with pytest.raises(ExecutableNotFoundError, match="must be an absolute") as info:
        calc.execute(water(), **kwargs)
    assert f"'{value}' ({source_label(source, xdg_config)})" in str(info.value)
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.filterwarnings("ignore:No handler declared")
def test_tilde_expanded(fake_software, tmp_path, monkeypatch, xdg_config, source):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    script = write_program(tmp_path / "home" / "opt" / "orca" / "orca")
    kwargs = give_executable(source, "~/opt/orca/orca", monkeypatch, xdg_config)
    calc = AMAC(software="FAKEPROG", workdir=tmp_path / "work", **PARAMETERS)
    result = calc.execute(water(), **kwargs)
    assert result.success
    assert result.context.metadata["executable"] == {
        "path": str(script),
        "source": source_label(source, xdg_config),
    }


@pytest.mark.parametrize("name", ["missing", "not-executable"])
def test_unusable_executable(fake_software, tmp_path, name):
    (tmp_path / "not-executable").write_text("", encoding="utf-8")
    calc = AMAC(software="FAKEPROG", workdir=tmp_path / "work", **PARAMETERS)
    with pytest.raises(ExecutableNotFoundError, match="does not exist or is not"):
        calc.execute(water(), executable=str(tmp_path / name))
    assert not (tmp_path / "work").exists()


@pytest.mark.filterwarnings("ignore:No handler declared")
def test_run_environment_and_provenance(
    fake_software, program, tmp_path, monkeypatch, xdg_config
):
    write_config(
        xdg_config,
        f'[software.FAKEPROG]\nexecutable = "{program}"\n'
        "env = { AMAC_TEST_A = 'file', AMAC_TEST_B = 'file', OMP_NUM_THREADS = '7' }\n",
    )
    for name in ("AMAC_TEST_A", "AMAC_TEST_B", "AMAC_TEST_C"):
        monkeypatch.setenv(name, "os")
    calc = AMAC(
        software="FAKEPROG",
        workdir=tmp_path / "work",
        cpu=2,
        env={"AMAC_TEST_B": "spec"},
        **PARAMETERS,
    )
    result = calc.execute(water())
    assert result.success
    assert result.context.stdout.strip() == "A=file B=spec C=os OMP=7"
    executable = result.context.metadata["executable"]
    assert executable == {"path": str(program), "source": f"file:{xdg_config}"}
    assert json.loads(json.dumps(executable)) == executable


@pytest.mark.filterwarnings("ignore:No handler declared")
def test_file_env_not_stored(fake_software, program, tmp_path, xdg_config):
    write_config(xdg_config, "[software.FAKEPROG]\nenv = { SECRET = 'from-file' }\n")
    calc = AMAC(
        software="FAKEPROG",
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


def test_driver_settings_include_file_env(fake_software, xdg_config):
    write_config(xdg_config, '[software.FAKEPROG]\nenv = { A = "file", B = "file" }\n')
    settings = DummyLibraryDriver().execution_settings(
        fake_software(), ExecutionSpec(env={"B": "spec"})
    )
    assert settings["env"] == {"A": "file", "B": "spec"}


def test_reset_configuration_clears_cache(fake_software, xdg_config):
    write_config(xdg_config, '[software.FAKEPROG]\nexecutable = "/first/prog"\n')
    assert amac.which("FAKEPROG").path == "/first/prog"
    write_config(xdg_config, '[software.FAKEPROG]\nexecutable = "/second/prog"\n')
    assert amac.which("FAKEPROG").path == "/first/prog"
    amac.reset_configuration()
    assert amac.which("FAKEPROG").path == "/second/prog"

