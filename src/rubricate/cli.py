"""Command-line entry point for rubricate."""  # docstring describing this module

from __future__ import annotations  # lets type hints like `list[str] | None` work on Python 3.10

import argparse  # standard-library parser for command-line flags and subcommands
import json  # machine-readable output for --format json
import sys  # gives access to stdout/stderr and exit codes
import time  # pacing batch requests with --rpm
from collections import Counter  # counts findings per rule for the summary line
from pathlib import Path  # filesystem paths that work on every OS

from rubricate import __version__  # the package version, shown by `rubricate --version`
from rubricate.calibrate import (  # agreement reports
    CalibrationError,
    calibrate,
    load_human_ratings,
    load_judge_scores,
)
from rubricate.check import FAIL, PASS, UNCHECKED, check_trace  # assertion checks
from rubricate.export import EXPORTERS  # other tools' config formats
from rubricate.judge import DEFAULT_GEMINI_MODEL, JudgeError, make_judge  # LLM judges
from rubricate.lint import RULES, LintReport, lint_file  # quality rules
from rubricate.score import ScoreResult, score_response  # grading pipeline
from rubricate.spec import FileReport, check_file  # per-file validation with line numbers
from rubricate.trace import TraceError, load_traces  # recorded agent runs

EXIT_OK = 0  # every file passed
EXIT_INVALID = 1  # at least one file has problems (what CI should fail on)
EXIT_USAGE = 2  # bad arguments, missing files, or nothing to check
MAX_FAILURE_STREAK = 10  # `score --batch` stops after this many failures in a row

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

    lint = sub.add_parser(  # `rubricate lint ...`
        "lint",  # the subcommand name
        help="find quality problems in rubrics",  # shown in `rubricate --help`
        description="Check rubrics for problems that make scores noisy: missing examples, "
        "vague anchors, duplicate ids, and more. Runs `validate` first.",
    )
    lint.add_argument(  # files or folders, same as validate
        "paths",
        nargs="*",  # optional so `--list-rules` works on its own
        type=Path,
        help=f"rubric files, or folders to search for {RUBRIC_GLOB}",
    )
    lint.add_argument(  # output style
        "--format", choices=["text", "json"], default="text", help="output format (default: text)"
    )
    lint.add_argument(  # turn rules off, by code or name
        "--ignore",
        action="append",  # can be given more than once
        default=[],
        metavar="RULES",
        help="comma-separated rule codes or names to skip, e.g. R003,vague-anchor",
    )
    lint.add_argument(  # make warnings fail the run too
        "--strict", action="store_true", help="exit 1 on warnings as well as errors"
    )
    lint.add_argument(  # print the rule catalog and exit
        "--list-rules", action="store_true", help="show every rule and exit"
    )

    check = sub.add_parser(  # `rubricate check ...`
        "check",
        help="check agent traces against a rubric's assertions",
        description="Check recorded agent runs against the rubric's assertions (tool-call order, "
        "forbidden or required calls, call budgets). Deterministic: no model calls.",
    )
    check.add_argument("rubric", type=Path, help="the .rubric.yaml file with assertions")
    check.add_argument(
        "traces", nargs="+", type=Path, help="trace files: .jsonl (one run per line) or .json"
    )
    check.add_argument(
        "--strict", action="store_true", help="exit 1 on failed warnings as well as blockers"
    )
    check.add_argument(
        "--format", choices=["text", "json"], default="text", help="output format (default: text)"
    )
    score = sub.add_parser(  # `rubricate score ...`
        "score",
        help="grade responses against a rubric with an LLM judge",
        description="Grade one response, or a JSONL batch, against a rubric using an LLM judge. "
        "Needs an API key for the judge, e.g. GEMINI_API_KEY.",
    )
    score.add_argument("rubric", type=Path, help="the .rubric.yaml file to grade against")
    what = score.add_mutually_exclusive_group(required=True)  # exactly one source of responses
    what.add_argument("--output", help="the response text to grade")
    what.add_argument("--output-file", type=Path, help="read the response to grade from a file")
    what.add_argument(
        "--batch",
        type=Path,
        help='JSONL file, one response per line: {"id": ..., "input": ..., "output": ...}',
    )
    score.add_argument("--input", help="the prompt the response was answering (optional)")
    score.add_argument(
        "--judge",
        default=f"gemini:{DEFAULT_GEMINI_MODEL}",
        help=f"judge as provider:model (default: gemini:{DEFAULT_GEMINI_MODEL})",
    )
    score.add_argument(
        "--out", type=Path, help="write batch results as JSONL to this file (default: stdout)"
    )
    score.add_argument(
        "--rpm",
        type=float,
        default=0,
        help="max judge requests per minute, to stay under rate limits (default: no limit)",
    )
    score.add_argument(
        "--resume",
        action="store_true",
        help="with --out: keep items already scored there and only (re)score the rest",
    )
    score.add_argument(
        "--format", choices=["text", "json"], default="text", help="output for a single response"
    )
    export = sub.add_parser(  # `rubricate export ...`
        "export",
        help="export a rubric to another eval tool",
        description="Export a rubric's scored criteria to another eval tool's config format.",
    )
    export.add_argument("rubric", type=Path, help="the .rubric.yaml file to export")
    export.add_argument(
        "--to", choices=sorted(EXPORTERS), required=True, help="target tool (promptfoo)"
    )
    export.add_argument("-o", "--output", type=Path, help="write to this file (default: stdout)")
    export.add_argument(
        "--threshold",
        type=float,
        help="minimum 0-1 score for each exported assertion to pass (default: the tool's own)",
    )

    calibrate = sub.add_parser(  # `rubricate calibrate ...`
        "calibrate",
        help="measure agreement between human raters and the judge",
        description="Report, per criterion, how consistently humans apply the rubric "
        "(Krippendorff's alpha) and how closely the judge matches them (weighted kappa).",
    )
    calibrate.add_argument("rubric", type=Path, help="the .rubric.yaml file the ratings use")
    calibrate.add_argument(
        "--human",
        type=Path,
        required=True,
        help="CSV of human ratings with columns item,rater,criterion,score",
    )
    calibrate.add_argument(
        "--judge-scores",
        type=Path,
        help="JSONL from `rubricate score --batch`, with ids matching the CSV's items",
    )
    calibrate.add_argument(
        "--format", choices=["text", "json"], default="text", help="output format (default: text)"
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


def _resolve(paths: list[Path]) -> list[Path] | None:  # files to check, or None on bad input
    files, missing = _collect(paths)  # expand folders, find missing paths
    for path in missing:  # tell the user about bad arguments
        print(f"rubricate: no such file or folder: {path}", file=sys.stderr)
    if missing:  # don't half-run with bad input
        return None
    if not files:  # folders given, but nothing matched the naming convention
        print(f"rubricate: no {RUBRIC_GLOB} files found", file=sys.stderr)
        return None
    return files  # good to go


def _cmd_validate(args: argparse.Namespace) -> int:  # runs `rubricate validate`
    files = _resolve(args.paths)  # figure out what to check
    if files is None:  # bad arguments already explained on stderr
        return EXIT_USAGE
    reports = [check_file(path) for path in files]  # check every file
    if args.format == "json":  # pick the output style
        _print_json(reports)
    else:
        _print_text(reports)
    return EXIT_OK if all(r.ok for r in reports) else EXIT_INVALID  # CI fails on 1


def _print_rules() -> None:  # `rubricate lint --list-rules`
    for rule in RULES:  # one line per rule
        print(f"{rule.code}  {rule.name:<24}{rule.severity:<9}{rule.summary}")


def _print_lint_text(reports: list[LintReport]) -> None:  # human-readable lint output
    for report in reports:  # one block per file
        for err in report.schema_errors:  # structure problems come first
            where = f"{report.path}:{err.line}" if err.line else str(report.path)  # file[:line]
            print(f"{where}: schema error: {err}")
        for f in report.findings:  # then rule findings, e.g. a.rubric.yaml:14: R003 warning ...
            where = f"{report.path}:{f.line}" if f.line else str(report.path)
            print(f"{where}: {f.code} {f.severity}: {f.path}: {f.message}")
        if not report.schema_errors and not report.findings:  # nothing to say
            print(f"{report.path}: clean")
    errors = sum(r.errors for r in reports)  # totals across all files
    warnings = sum(r.warnings for r in reports)
    print(f"{len(reports)} file(s) linted: {errors} error(s), {warnings} warning(s)")
    by_rule = Counter(f.code for r in reports for f in r.findings)  # how often each rule fired
    if by_rule:  # a one-line breakdown helps decide what to fix first
        print("by rule: " + ", ".join(f"{code} x{n}" for code, n in sorted(by_rule.items())))


def _print_lint_json(reports: list[LintReport]) -> None:  # machine-readable lint output
    payload = [
        {
            "path": str(r.path),  # which file
            "errors": r.errors,  # counts, for quick checks
            "warnings": r.warnings,
            "schema_errors": [  # structural problems
                {"line": e.line, "path": e.path, "message": e.message} for e in r.schema_errors
            ],
            "findings": [  # rule results
                {
                    "code": f.code,
                    "severity": f.severity,
                    "line": f.line,
                    "path": f.path,
                    "message": f.message,
                }
                for f in r.findings
            ],
        }
        for r in reports
    ]
    print(json.dumps(payload, indent=2))  # pretty-printed


def _cmd_lint(args: argparse.Namespace) -> int:  # runs `rubricate lint`
    if args.list_rules:  # catalog only
        _print_rules()
        return EXIT_OK
    if not args.paths:  # nothing to lint
        print("rubricate: lint needs at least one file or folder", file=sys.stderr)
        return EXIT_USAGE
    ignore = frozenset(  # flatten "R003,vague-anchor" style values into one set
        item.strip() for value in args.ignore for item in value.split(",") if item.strip()
    )
    known = {r.code for r in RULES} | {r.name for r in RULES}  # valid things to ignore
    unknown = sorted(ignore - known)  # typos in --ignore
    if unknown:  # fail loudly rather than silently ignoring nothing
        print(f"rubricate: unknown rule(s) in --ignore: {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    files = _resolve(args.paths)  # figure out what to lint
    if files is None:  # bad arguments already explained
        return EXIT_USAGE
    reports = [lint_file(path, ignore) for path in files]  # lint every file
    if args.format == "json":
        _print_lint_json(reports)
    else:
        _print_lint_text(reports)
    errors = sum(r.errors for r in reports)  # anything that must fail the run
    warnings = sum(r.warnings for r in reports)  # fails only with --strict
    return EXIT_INVALID if errors or (args.strict and warnings) else EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:  # runs `rubricate check`
    if not args.rubric.is_file():
        print(f"rubricate: no such file: {args.rubric}", file=sys.stderr)
        return EXIT_USAGE
    report = check_file(args.rubric)  # validate the rubric first
    if not report.ok:
        for err in report.errors:
            print(f"{args.rubric}:{err.line or ''}: {err}", file=sys.stderr)
        print("rubricate: fix the rubric first (see `rubricate validate`)", file=sys.stderr)
        return EXIT_USAGE
    if not any(c.get("type") == "assertion" for c in report.data["criteria"]):
        print("rubricate: this rubric has no assertions to check", file=sys.stderr)
        return EXIT_USAGE
    traces = []  # every run from every file
    try:
        for path in args.traces:
            traces.extend(load_traces(path))
    except (OSError, TraceError) as exc:  # missing file or malformed trace
        print(f"rubricate: {exc}", file=sys.stderr)
        return EXIT_USAGE
    runs = [check_trace(report.data, t) for t in traces]  # evaluate every run
    if args.format == "json":
        payload = [
            {
                "trace": r.trace_id,
                "blocked": r.blocked,
                "results": [
                    {
                        "id": a.id,
                        "severity": a.severity,
                        "status": a.status,
                        "step": a.step,
                        "detail": a.detail,
                    }
                    for a in r.results
                ],
            }
            for r in runs
        ]
        print(json.dumps(payload, indent=2))
    else:
        marks = {PASS: "PASS", FAIL: "FAIL", UNCHECKED: "----"}  # fixed-width status labels
        for run in runs:  # one block per run
            verdict = "BLOCKED" if run.blocked else "ok"
            print(f"{run.trace_id}: {verdict}")
            for a in run.results:
                line = f"  {marks[a.status]}  {a.id} ({a.severity})"
                if a.detail:
                    line += f": {a.detail}"
                elif a.status == UNCHECKED:
                    line += ": no `check` defined; needs manual review"
                print(line)
        blocked = sum(r.blocked for r in runs)
        warned = sum(1 for r in runs if r.warnings)
        print(f"{len(runs)} run(s) checked: {blocked} blocked, {warned} with warnings")
    failed = any(r.blocked for r in runs) or (args.strict and any(r.warnings for r in runs))
    return EXIT_INVALID if failed else EXIT_OK


def _print_score_text(result: ScoreResult) -> None:  # human-readable single result
    for c in result.criteria:  # one line per criterion
        print(f"{c.id:<20} {c.score}/{c.max}  {c.rationale}")
    for cid in result.skipped:  # assertions aren't graded by the judge
        print(f"{cid:<20} skipped (assertion; verify with `rubricate check` on agent traces)")
    print(f"weighted score: {result.weighted:.0%}  (judge: {result.judge})")


def _read_batch(path: Path) -> list[dict]:  # parse a JSONL batch, with line-numbered errors
    items = []  # one dict per non-blank line
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():  # skip blank lines
            continue
        try:
            item = json.loads(line)  # each line is one JSON object
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{n}: not valid JSON ({exc.msg})") from exc
        if not isinstance(item, dict) or not isinstance(item.get("output"), str):
            raise ValueError(f'{path}:{n}: each line needs an "output" string')
        item.setdefault("id", str(n))  # default id: the line number
        items.append(item)
    return items


def _cmd_score(args: argparse.Namespace) -> int:  # runs `rubricate score`
    report = check_file(args.rubric) if args.rubric.is_file() else None  # validate first
    if report is None:
        print(f"rubricate: no such file: {args.rubric}", file=sys.stderr)
        return EXIT_USAGE
    if not report.ok:  # never grade against a broken rubric
        for err in report.errors:
            print(f"{args.rubric}:{err.line or ''}: {err}", file=sys.stderr)
        print("rubricate: fix the rubric first (see `rubricate validate`)", file=sys.stderr)
        return EXIT_USAGE
    rubric = report.data  # the parsed, valid rubric
    try:
        if args.batch:  # many responses from a JSONL file
            items = _read_batch(args.batch)
        elif args.output_file:  # one response from a file
            items = [
                {"id": "1", "input": args.input, "output": args.output_file.read_text("utf-8")}
            ]
        else:  # one response from the command line
            items = [{"id": "1", "input": args.input, "output": args.output}]
    except (OSError, ValueError) as exc:  # unreadable or malformed input
        print(f"rubricate: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        judge = make_judge(args.judge)  # fails fast on missing SDK or API key
    except JudgeError as exc:
        print(f"rubricate: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not args.batch:  # single response: print the result
        try:
            result = score_response(rubric, items[0]["output"], judge, items[0].get("input"))
        except JudgeError as exc:
            print(f"rubricate: {exc}", file=sys.stderr)
            return EXIT_INVALID
        if args.format == "json":
            print(json.dumps(result.to_dict(), indent=2))
        else:
            _print_score_text(result)
        return EXIT_OK
    done: dict[str, str] = {}  # id -> already-scored JSONL line, when resuming
    if args.resume:
        if not args.out:
            print("rubricate: --resume needs --out", file=sys.stderr)
            return EXIT_USAGE
        if args.out.exists():  # keep successes, drop failures so they're retried
            for line in args.out.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line) if line.strip() else {}
                if rec.get("criteria") and "error" not in rec:
                    done[str(rec["id"])] = line
        print(f"resuming: {len(done)} already scored", file=sys.stderr)
    todo = [item for item in items if str(item["id"]) not in done]  # what still needs a judge
    sink = args.out.open("w", encoding="utf-8") if args.out else sys.stdout  # where JSONL goes
    for line in done.values():  # carry earlier results forward
        sink.write(line + "\n")
    failures = 0  # items the judge couldn't grade
    streak = 0  # consecutive failures; a long run usually means a quota or key problem
    try:
        gap = 60 / args.rpm if args.rpm > 0 else 0  # seconds between requests, if throttled
        last = 0.0  # when the previous request started
        for i, item in enumerate(todo, start=1):  # grade each remaining response in turn
            wait = last + gap - time.monotonic()  # time left before the next request is allowed
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            record = {"id": item["id"]}  # every output line carries the input's id
            try:
                record.update(
                    score_response(rubric, item["output"], judge, item.get("input")).to_dict()
                )
                streak = 0  # a success resets the streak
            except JudgeError as exc:  # record the failure and keep going
                failures += 1
                streak += 1
                record["error"] = str(exc)
            sink.write(json.dumps(record) + "\n")  # one JSON object per line
            sink.flush()  # results survive an interrupted run
            print(f"scored {i}/{len(todo)}", file=sys.stderr)  # progress on stderr
            if streak >= MAX_FAILURE_STREAK:  # stop instead of failing every remaining item
                left = len(todo) - i
                print(
                    f"rubricate: {streak} failures in a row, stopping with {left} left. "
                    f"Last error: {record['error'][:200]}\n"
                    "Fix the cause (quota, key, model), then rerun with --resume.",
                    file=sys.stderr,
                )
                failures += left
                break
    finally:
        if args.out:
            sink.close()
    scored = len(items) - failures  # includes items carried over by --resume
    print(f"{scored}/{len(items)} scored, {failures} failed", file=sys.stderr)
    return EXIT_INVALID if failures else EXIT_OK


def _fmt(value: float | None, pct: bool = False, sign: bool = False) -> str:  # table cells
    if value is None:
        return "-"
    if pct:
        return f"{value:.0%}"
    return f"{value:+.2f}" if sign else f"{value:.2f}"


def _cmd_calibrate(args: argparse.Namespace) -> int:  # runs `rubricate calibrate`
    if not args.rubric.is_file():
        print(f"rubricate: no such file: {args.rubric}", file=sys.stderr)
        return EXIT_USAGE
    report = check_file(args.rubric)  # validate the rubric first
    if not report.ok:
        print("rubricate: fix the rubric first (see `rubricate validate`)", file=sys.stderr)
        return EXIT_USAGE
    try:
        human = load_human_ratings(args.human, report.data)
        judge = load_judge_scores(args.judge_scores) if args.judge_scores else None
    except (OSError, CalibrationError) as exc:
        print(f"rubricate: {exc}", file=sys.stderr)
        return EXIT_USAGE
    rows = calibrate(report.data, human, judge)
    if args.format == "json":
        print(json.dumps([r.to_dict() for r in rows], indent=2))
        return EXIT_OK
    head = f"{'criterion':<20}{'items':>6}{'raters':>7}{'alpha':>8}"
    if judge is not None:
        head += f"{'kappa':>8}{'exact':>7}{'+/-1':>6}{'bias':>7}"
    print(head + "  verdict")
    for r in rows:
        line = f"{r.criterion:<20}{r.items:>6}{r.raters:>7}{_fmt(r.human_alpha):>8}"
        if judge is not None:
            line += (
                f"{_fmt(r.judge_kappa):>8}{_fmt(r.exact, pct=True):>7}"
                f"{_fmt(r.within_one, pct=True):>6}{_fmt(r.bias, sign=True):>7}"
            )
        print(line + f"  {r.verdict}")
    print(
        "alpha = agreement among humans (Krippendorff; >= 0.80 reliable, < 0.67 unreliable). "
        + ("kappa = judge vs. the human median (quadratic weighted)." if judge else "")
    )
    return EXIT_OK


def _cmd_export(args: argparse.Namespace) -> int:  # runs `rubricate export`
    if not args.rubric.is_file():
        print(f"rubricate: no such file: {args.rubric}", file=sys.stderr)
        return EXIT_USAGE
    report = check_file(args.rubric)  # never export a broken rubric
    if not report.ok:
        print("rubricate: fix the rubric first (see `rubricate validate`)", file=sys.stderr)
        return EXIT_USAGE
    if args.threshold is not None and not 0 <= args.threshold <= 1:
        print("rubricate: --threshold must be between 0 and 1", file=sys.stderr)
        return EXIT_USAGE
    text = EXPORTERS[args.to](report.data, args.threshold)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:  # entry point; argv is injectable for tests
    parser = build_parser()  # construct the parser
    args = parser.parse_args(argv)  # parse sys.argv (or the test-provided list)
    if args.command is None:  # no subcommand given
        parser.print_help(sys.stdout)  # show usage instead of failing silently
        return EXIT_OK  # asking for help isn't an error
    if args.command == "validate":  # dispatch to the matching handler
        return _cmd_validate(args)
    if args.command == "lint":
        return _cmd_lint(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "calibrate":
        return _cmd_calibrate(args)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "score":
        return _cmd_score(args)
    return EXIT_USAGE  # unreachable today; guards future subcommands


if __name__ == "__main__":  # allows `python -m rubricate.cli` as well as the installed command
    sys.exit(main())  # turn main()'s return value into the process exit code
