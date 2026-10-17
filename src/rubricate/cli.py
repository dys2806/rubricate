"""Command-line entry point for rubricate."""  # docstring describing this module

from __future__ import annotations  # lets type hints like `list[str] | None` work on Python 3.10

import argparse  # standard-library parser for command-line flags and subcommands
import sys  # gives access to stdout/stderr and exit codes

from rubricate import __version__  # the package version, shown by `rubricate --version`


def build_parser() -> argparse.ArgumentParser:  # separate so tests can call it
    parser = argparse.ArgumentParser(  # the top-level `rubricate` command
        prog="rubricate",  # name shown in help and error messages
        description="Rubrics as code for AI evaluation.",  # one-line summary shown in --help
    )
    parser.add_argument(  # adds the --version flag
        "--version",  # flag name
        action="version",  # argparse prints the version string and exits
        version=f"rubricate {__version__}",  # the exact text printed
    )
    parser.add_subparsers(dest="command", metavar="<command>")  # subcommands land on Day 3+
    return parser  # hand the finished parser back to the caller


def main(argv: list[str] | None = None) -> int:  # entry point; argv is injectable for tests
    parser = build_parser()  # construct the parser
    args = parser.parse_args(argv)  # parse sys.argv (or the test-provided list)
    if args.command is None:  # no subcommand given yet
        parser.print_help(sys.stdout)  # show usage instead of failing silently
        return 0  # exit code 0 = success
    return 0  # subcommands will return their own exit codes once they exist


if __name__ == "__main__":  # allows `python -m rubricate.cli` as well as the installed command
    sys.exit(main())  # turn main()'s return value into the process exit code
