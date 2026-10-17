"""Smoke tests for the rubricate CLI."""  # docstring for the test module

import pytest  # test framework; provides fixtures like capsys

from rubricate import __version__  # the version string we expect the CLI to print
from rubricate.cli import main  # the function behind the `rubricate` command


def test_version_flag_prints_version(capsys):  # capsys captures stdout/stderr
    with pytest.raises(SystemExit) as exc:  # argparse exits after printing --version
        main(["--version"])  # run the CLI as if the user typed `rubricate --version`
    assert exc.value.code == 0  # a clean exit, not an error
    assert __version__ in capsys.readouterr().out  # the printed text contains the version


def test_no_command_prints_help_and_succeeds(capsys):  # bare `rubricate` should be friendly
    assert main([]) == 0  # returns success instead of crashing
    assert "usage: rubricate" in capsys.readouterr().out  # and shows the usage line
