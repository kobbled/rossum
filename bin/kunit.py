#!/usr/bin/python

import argparse
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import yaml

from rossum_cli import CliError, Console, fail_missing_file, main_guard, write_text


FILE_MANIFEST = ".man_log"
KUNIT_LOG_NAME = "kunit.log"

FAILURE_MARKERS = (
    "failed",
    "failure",
    "error:",
    "exception",
    "traceback",
)


def main():
    parser = argparse.ArgumentParser(
        prog="kunit",
        description="Run KUnit test programs through the robot HTTP endpoint.",
    )
    parser.add_argument("--build-dir", default=os.getcwd(), metavar="PATH",
        help="build directory containing .man_log")
    parser.add_argument("--manifest", default=FILE_MANIFEST, metavar="PATH",
        help="manifest path, relative to build dir unless absolute")
    parser.add_argument("--ip", metavar="ADDRESS",
        help="override the robot IP address from .man_log")
    parser.add_argument("--program", action="append", default=[], metavar="NAME",
        help="test program name to run; may be repeated")
    parser.add_argument("--timeout", type=int, default=30, metavar="SECONDS",
        help="HTTP timeout")
    parser.add_argument("--dry-run", action="store_true",
        help="show the request without contacting the robot")
    parser.add_argument("--no-color", action="store_true",
        help="disable colored output")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="show response details")
    args = parser.parse_args()

    console = Console(no_color=args.no_color, verbose=args.verbose)
    build_dir = Path(args.build_dir).resolve()
    manifest_path = resolve_path(build_dir, args.manifest)
    log_path = build_dir / KUNIT_LOG_NAME

    manifest = load_manifest(manifest_path)
    ip = args.ip or manifest.get("ip")
    if not ip:
        raise CliError(
            "Robot IP address missing",
            detail="No 'ip' value was found in {}".format(manifest_path),
            hints=["Set Ftp in robot.ini or set ROSSUM_SERVER_IP, then rerun rossum."],
        )

    programs = args.program or test_programs_from_manifest(manifest)
    if not programs:
        console.warning("No KUnit test programs were found in .man_log.")
        return 0

    query = urlencode({"filenames": ",".join(programs)})
    url = "http://{}/KAREL/KUnit?{}".format(ip, query)
    console.table("KUnit request", ("Field", "Value"), [
        ("Robot", ip),
        ("Programs", ", ".join(programs)),
        ("URL", url),
    ])

    if args.dry_run:
        console.success("Dry run completed. Robot was not contacted.")
        return 0

    try:
        with console.status("[cyan]Running KUnit request...[/cyan]"):
            with urlopen(url, timeout=args.timeout) as response:
                status = response.getcode()
                body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        write_text(str(log_path), body)
        raise CliError(
            "KUnit HTTP request failed",
            detail="HTTP {}\nLog: {}\n\n{}".format(exc.code, log_path, clipped(body)),
            hints=["Check that the KUnit KAREL HTTP endpoint is installed and enabled on the robot."],
        ) from exc
    except URLError as exc:
        raise CliError(
            "Could not connect to robot KUnit endpoint",
            detail="{}\nURL: {}".format(exc.reason, url),
            hints=["Check robot IP, network connection, and whether the robot web server is enabled."],
        ) from exc
    except TimeoutError as exc:
        raise CliError(
            "KUnit request timed out",
            detail="Timeout: {} seconds\nURL: {}".format(args.timeout, url),
            hints=["Increase --timeout if the test is expected to run longer."],
        ) from exc

    write_text(str(log_path), body)
    if args.verbose or body.strip():
        console.panel("KUnit response", clipped(body), style="cyan")

    suspicious = find_failure_lines(body)
    if status < 200 or status >= 300:
        raise CliError(
            "KUnit returned a non-success HTTP status",
            detail="HTTP {}\nLog: {}".format(status, log_path),
        )
    if suspicious:
        raise CliError(
            "KUnit response contains possible failures",
            detail="Log: {}\n\n{}".format(log_path, "\n".join(suspicious[:20])),
            hints=["Open the KUnit log and confirm the failing test details."],
        )

    console.success("KUnit completed without detected failures. Log: {}".format(log_path))
    return 0


def resolve_path(base_dir, value):
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def load_manifest(path):
    if not path.exists():
        fail_missing_file(str(path), "Manifest")
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            manifest = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise CliError(
            "Manifest YAML is invalid",
            detail="{}\n{}".format(path, exc),
            hints=["Regenerate the build with rossum."],
        ) from exc
    if not isinstance(manifest, dict):
        raise CliError("Manifest format is invalid", detail="Expected a YAML mapping in {}".format(path))
    return manifest


def test_programs_from_manifest(manifest):
    tests = manifest.get("test")
    if not isinstance(tests, dict):
        return []
    return [os.path.splitext(name)[0] for name in tests.keys()]


def clipped(text, limit=4000):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def find_failure_lines(body):
    suspicious = []
    for line in body.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in FAILURE_MARKERS):
            if "0 failed" in lowered or "failures: 0" in lowered or "failed: 0" in lowered:
                continue
            suspicious.append(line)
    return suspicious


if __name__ == "__main__":
    sys.exit(main_guard(main, tool_name="kunit"))
