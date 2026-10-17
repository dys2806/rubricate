"""Command-line entry point for rubricate."""  # docstring describing this module

from __future__ import annotations  # lets type hints like `list[str] | None` work on Python 3.10

import argparse  # standard-library parser for command-line flags and subcommands
import json  # machine-readable output for --format json
import sys  # gives access to stdout/stderr and exit codes
from pathlib import Path  # filesystem paths that work on every OS

from rubricate import __version__  # the package version, shown by `rubricate --version`
from rubricate.spec import FileReport, check_file  # per-file validation with line numbers

EXIT_OK = 0  # every file passed
EXIT_INVALID = 1  # at least one file has problems (what CI should fail on)
EXIT_USAGE = 2  # bad arguments, missing files, or nothing to check

RUBRIC_GLOB = "*.rubric.yaml"  # naming convention used when a directory is given


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
    sub = parser.add_subparsers(dest="command", metavar="<command>")  # container for subcommands

    validate = sub.add_parser(  # `rubricate validate ...`
        "validate",  # the subcommand name
        help="check rubric files against the spec",  # shown in `rubricate --help`
        description="Check rubric files against the rubricate spec and JSON Schema.",
    )
    validate.add_argument(  # one or more files or folders to check
        "paths",  # positional argument name
        nargs="+",  # require at least one
        type=Path,  # convert each argument to a Path
        help=f"rubric files, or folders to search for {RUBRIC_GLOB}",
    )
    validate.add_argument(  # output style
        "--format",  # flag name
        choices=["text", "json"],  # human-readable or machine-readable
        default="text",  # humans by default
        help="output format (default: text)",
    )
    return parser  # hand the finished parser back to the caller


def _collect(paths: list[Path]) -> tuple[list[Path], list[Path]]:  # expand folders into files
    found: list[Path] = []  # rubric files to check
    missing: list[Path] = []  # arguments that don't exist on disk
    for path in paths:  # look at each argument the user gave
        if path.is_dir():  # a folder...
            found.extend(sorted(path.rglob(RUBRIC_GLOB)))  # ...search it recursively, stable order
        elif path.is_file():  # a single file...
            found.append(path)  # ...check it whatever its name is
        else:  # neither file nor folder
            missing.append(path)  # report it instead of crashing
    return found, missing  # both lists back to the caller


def _print_text(reports: list[FileReport]) -> None:  # human-readable output
    for report in reports:  # one block per file
        if report.ok:  # nothing wrong
            print(f"{report.path}: valid")  # short confirmation
            continue  # next file
        for err in report.errors:  # one line per problem, editor-friendly `file:line: ...`
            where = f"{report.path}:{err.line}" if err.line else str(report.path)  # file[:line]
            print(f"{where}: {err}")  # e.g. a.rubric.yaml:14: criteria[0].scale: ...
    bad = [r for r in reports if not r.ok]  # files that failed
    total_errors = sum(len(r.errors) for r in bad)  # problems across all failed files
    summary = f"{len(reports)} file(s) checked, {len(bad)} invalid"  # headline numbers
    if bad:  # add the error count only when there is one
        summary += f" ({total_errors} error(s))"
    print(summary)  # final line, easy to spot in CI logs


def _print_json(reports: list[FileReport]) -> None:  # machine-readable output for tools and CI
    payload = [  # one object per file
        {
            "path": str(r.path),  # which file
            "valid": r.ok,  # pass/fail
            "errors": [  # each problem with its location
                {"line": e.line, "path": e.path, "message": e.message} for e in r.errors
            ],
        }
        for r in reports
    ]
    print(json.dumps(payload, indent=2))  # pretty-printed so it's also readable


def _cmd_validate(args: argparse.Namespace) -> int:  # runs `rubricate validate`
    files, missing = _collect(args.paths)  # figure out what to check
    for path in missing:  # tell the user about bad arguments
        print(f"rubricate: no such file or folder: {path}", file=sys.stderr)
    if missing:  # don't half-run with bad input
        return EXIT_USAGE
    if not files:  # folders given, but nothing matched the naming convention
        print(f"rubricate: no {RUBRIC_GLOB} files found", file=sys.stderr)
        return EXIT_USAGE
    reports = [check_file(path) for path in files]  # check every file
    if args.format == "json":  # pick the output style
        _print_json(reports)
    else:
        _print_text(reports)
    return EXIT_OK if all(r.ok for r in reports) else EXIT_INVALID  # CI fails on 1


def main(argv: list[str] | None = None) -> int:  # entry point; argv is injectable for tests
    parser = build_parser()  # construct the parser
    args = parser.parse_args(argv)  # parse sys.argv (or the test-provided list)
    if args.command is None:  # no subcommand given
        parser.print_help(sys.stdout)  # show usage instead of failing silently
        return EXIT_OK  # asking for help isn't an error
    if args.command == "validate":  # dispatch to the matching handler
        return _cmd_validate(args)
    return EXIT_USAGE  # unreachable today; guards future subcommands


if __name__ == "__main__":  # allows `python -m rubricate.cli` as well as the installed command
    sys.exit(main())  # turn main()'s return value into the process exit code
