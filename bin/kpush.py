#!/usr/bin/python

import argparse
import os
import re
import sys
from pathlib import Path

import yaml
from ordered_set import OrderedSet

from rossum_cli import CliError, Console, fail_missing_file, main_guard, run_command, write_text


FILE_MANIFEST = ".man_log"
FTP_FILE_NAME = "ftp.txt"
FTP_LOG_NAME = "ftp.log"

DATA_TYPES = (
    "karel",
    "src",
    "test",
    "tp",
    "test_tp",
    "forms",
    "test_forms",
    "data",
    "test_data",
    "interface",
)

FTP_GROUPS = ("karel", "tp", "forms", "data", "interface")

KAREL_EXT = {".pc"}
TP_EXT = {".ls", ".tp"}
FORMS_EXT = {".tx"}
DATA_EXT = {".xml", ".csv"}

FTP_ERROR_PATTERNS = (
    "not connected",
    "connection timed out",
    "connection refused",
    "unknown host",
    "login failed",
    "not logged in",
    "permission denied",
    "no such file",
    "cannot find",
    "failed",
    "error",
    "550 ",
    "530 ",
    "425 ",
    "426 ",
)

EXPECTED_DELETE_MISS_PATTERNS = (
    "file not found",
    "program does not exist",
)


def main():
    parser = argparse.ArgumentParser(
        prog="kpush",
        description="Generate and run an FTP deployment batch from Rossum .man_log.",
    )
    parser.add_argument("-i", "--exclude-interfaces", action="store_true", dest="exclude_interface",
        help="do not deploy generated interface programs")
    parser.add_argument("-d", "--delete", action="store_true", dest="delete_only",
        help="delete files from the controller without uploading them")
    parser.add_argument("--dry-run", action="store_true",
        help="validate and show the deploy plan without writing ftp.txt or running FTP")
    parser.add_argument("--check", action="store_true",
        help="validate the manifest and local files without writing ftp.txt or running FTP")
    parser.add_argument("--script-only", action="store_true",
        help="write ftp.txt but do not run FTP")
    parser.add_argument("--build-dir", default=os.getcwd(), metavar="PATH",
        help="build directory containing .man_log and generated files")
    parser.add_argument("--manifest", default=FILE_MANIFEST, metavar="PATH",
        help="manifest path, relative to build dir unless absolute")
    parser.add_argument("--ftp-file", default=FTP_FILE_NAME, metavar="PATH",
        help="FTP script output path, relative to build dir unless absolute")
    parser.add_argument("--ip", metavar="ADDRESS",
        help="override the robot IP address from .man_log")
    parser.add_argument("--only", action="append", default=[], metavar="GROUPS",
        help="deploy only selected comma-separated groups: karel,tp,forms,data,interface")
    parser.add_argument("--skip", action="append", default=[], metavar="GROUPS",
        help="skip selected comma-separated groups: karel,tp,forms,data,interface")
    parser.add_argument("--timeout", type=int, default=120, metavar="SECONDS",
        help="timeout for the Windows ftp process")
    parser.add_argument("--no-color", action="store_true",
        help="disable colored output")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="show extra diagnostic information")
    args = parser.parse_args()

    console = Console(no_color=args.no_color, verbose=args.verbose)
    build_dir = Path(args.build_dir).resolve()
    manifest_path = resolve_path(build_dir, args.manifest)
    ftp_file = resolve_path(build_dir, args.ftp_file)
    ftp_log = build_dir / FTP_LOG_NAME

    manifest = load_manifest(manifest_path)
    ip = args.ip or manifest.get("ip")
    if not ip:
        raise CliError(
            "Robot IP address missing",
            detail="No 'ip' value was found in {}".format(manifest_path),
            hints=["Set Ftp in robot.ini or set ROSSUM_SERVER_IP, then rerun rossum."],
        )

    plan = build_deploy_plan(manifest, exclude_interface=args.exclude_interface)
    plan = filter_plan(plan, parse_groups(args.only), parse_groups(args.skip))
    if not any(len(files) for files in plan.values()):
        raise CliError(
            "Nothing to deploy",
            detail="The selected manifest groups contain no files.",
            hints=["Check .man_log or remove --only/--skip filters."],
        )

    missing = [] if args.delete_only else missing_local_files(build_dir, plan)
    show_plan(console, build_dir, ip, plan, args.delete_only, missing)
    if missing:
        raise CliError(
            "Deploy files are missing",
            detail="\n".join("  " + item for item in missing[:30]),
            hints=[
                "Run ninja before kpush.",
                "Run rossum manifest check to find stale manifest entries.",
                "Use --delete if the intent is only to delete controller files.",
            ],
        )

    if args.check or args.dry_run:
        console.success("Validation completed. FTP was not run.")
        return 0

    script = render_ftp_script(ip, plan, delete_only=args.delete_only)
    write_text(str(ftp_file), script)
    console.success("Wrote {}".format(ftp_file))

    if args.script_only:
        console.info("Script-only mode. FTP was not run.")
        return 0

    with console.status("[cyan]Running FTP transfer...[/cyan]"):
        result = run_ftp(ftp_file, ftp_log, build_dir, args.timeout)
    if result.returncode != 0:
        raise CliError(
            "FTP process failed",
            detail="Return code: {}\nLog: {}".format(result.returncode, ftp_log),
            hints=["Open the FTP log for the controller response.", "Check robot IP, FTP access, and network connection."],
        )

    suspicious = find_ftp_errors(result.output)
    if suspicious:
        raise CliError(
            "FTP reported possible transfer errors",
            detail="Log: {}\n\n{}".format(ftp_log, "\n".join(suspicious[:20])),
            hints=[
                "Review the FTP log for the exact controller response.",
                "Check whether files are in use on the robot.",
                "Check the robot storage target and permissions.",
            ],
        )

    console.success("FTP completed without detected errors. Log: {}".format(ftp_log))
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


def build_deploy_plan(manifest, *, exclude_interface):
    plan = {group: OrderedSet() for group in FTP_GROUPS}
    plan["karelvr"] = OrderedSet()

    for section, entries in manifest.items():
        if section not in DATA_TYPES or not isinstance(entries, dict):
            continue
        for parent, children in entries.items():
            for child in children or []:
                sort_child(child, plan)
            sort_parent(section, parent, plan, exclude_interface)
    return plan


def sort_parent(section, filename, plan, exclude_interface):
    if section in ("karel", "src", "test"):
        plan["karel"].add(filename)
        plan["karelvr"].add(os.path.splitext(filename)[0] + ".vr")
    if section in ("tp", "test_tp"):
        plan["tp"].add(filename)
    if section in ("forms", "test_forms"):
        plan["forms"].add(filename)
    if section in ("data", "test_data"):
        plan["data"].add(filename)
    if not exclude_interface and section == "interface":
        plan["interface"].add(filename)


def sort_child(filename, plan):
    ext = os.path.splitext(filename)[-1].lower()
    if ext in KAREL_EXT:
        plan["karel"].add(filename)
        plan["karelvr"].add(os.path.splitext(filename)[0] + ".vr")
    if ext in TP_EXT:
        plan["tp"].add(filename)
    if ext in FORMS_EXT:
        plan["forms"].add(filename)
    if ext in DATA_EXT:
        plan["data"].add(filename)


def parse_groups(values):
    groups = set()
    for value in values:
        for group in value.split(","):
            group = group.strip().lower()
            if not group:
                continue
            if group not in FTP_GROUPS:
                raise CliError(
                    "Unknown deploy group",
                    detail="Invalid group: {}".format(group),
                    hints=["Use one of: {}".format(", ".join(FTP_GROUPS))],
                )
            groups.add(group)
    return groups


def filter_plan(plan, only, skip):
    filtered = {group: OrderedSet(files) for group, files in plan.items()}
    for group in FTP_GROUPS:
        if only and group not in only:
            filtered[group].clear()
        if group in skip:
            filtered[group].clear()
    if "karel" not in filtered or not filtered["karel"]:
        filtered["karelvr"].clear()
    return filtered


def missing_local_files(build_dir, plan):
    missing = []
    for group in ("karel", "tp", "forms", "data", "interface"):
        for filename in plan[group]:
            if not (build_dir / filename).exists():
                missing.append("{}: {}".format(group, filename))
    return missing


def show_plan(console, build_dir, ip, plan, delete_only, missing):
    rows = []
    for group in ("karel", "karelvr", "tp", "forms", "data", "interface"):
        rows.append((group, len(plan[group])))
    console.table(
        "Deployment plan",
        ("Group", "Files"),
        rows,
    )
    console.info("Robot IP: {}".format(ip))
    console.info("Build dir: {}".format(build_dir))
    console.info("Mode: {}".format("delete only" if delete_only else "delete then upload"))
    if missing:
        console.warning("{} local file(s) are missing.".format(len(missing)))


def render_ftp_script(ip, plan, *, delete_only):
    lines = [
        "open {}".format(ip),
        "anon",
        "bin",
        "prompt",
        "cd md:\\",
    ]

    # Generated interfaces reference routines in their source Karel programs, so
    # release the interfaces before releasing the source programs.  FANUC also
    # requires each PC file to be deleted before its variable memory.
    interface_variables = [os.path.splitext(fl)[0] + ".vr" for fl in plan["interface"]]
    add_delete_block(lines, "interface", plan["interface"])
    add_delete_block(lines, "interface variable", interface_variables)
    add_delete_block(lines, "karel", plan["karel"])
    add_delete_block(lines, "karel variable", plan["karelvr"])
    add_delete_block(lines, "tp", plan["tp"])

    if plan["forms"]:
        lines.append("cd mf2:\\")
        add_delete_block(lines, "forms", plan["forms"])

    if plan["data"]:
        lines.append("cd fr:\\")
        add_delete_block(lines, "data", plan["data"])

    # Do not upload anything until every selected controller file has been
    # deleted.  VR files are created from the PC and must never be uploaded.
    if not delete_only:
        if plan["karel"] or plan["interface"] or plan["tp"]:
            lines.append("cd md:\\")
            add_put_block(lines, plan["karel"])
            add_put_block(lines, plan["interface"])
            add_put_block(lines, plan["tp"])

        if plan["forms"]:
            lines.append("cd mf2:\\")
            add_put_block(lines, plan["forms"])

        if plan["data"]:
            lines.append("cd fr:\\")
            add_put_block(lines, plan["data"])

    lines.append("quit")
    return "\n".join(lines) + "\n"


def add_put_block(lines, files):
    for filename in files:
        lines.append("put " + quote_ftp(filename))


def add_delete_block(lines, label, files):
    files = list(files)
    for filename in files:
        lines.append("delete " + quote_ftp(filename))


def quote_ftp(filename):
    return '"{}"'.format(filename)


def run_ftp(ftp_file, ftp_log, build_dir, timeout):
    result = run_command(["ftp", "-s:{}".format(ftp_file)], cwd=str(build_dir), timeout=timeout)
    write_text(str(ftp_log), result.output)
    return result


def find_ftp_errors(output):
    lines = []
    active_command = None
    active_files = []
    active_index = 0

    for line in output.splitlines():
        parsed = parse_ftp_command(line)
        if parsed:
            active_command, active_files = parsed
            active_index = 0
        elif line.strip().lower().startswith("ftp>"):
            # A new non-transfer FTP command ends the context of the preceding
            # put/delete command.  Do not suppress its errors as delete misses.
            active_command = None
            active_files = []
            active_index = 0

        lowered = line.lower()
        if any(pattern in lowered for pattern in FTP_ERROR_PATTERNS):
            if is_expected_delete_miss(active_command, lowered):
                if active_index < len(active_files) - 1:
                    active_index += 1
                continue
            filename = active_file(active_files, active_index)
            if filename:
                lines.append("{}: {} ({})".format(filename, line, active_command))
                if active_index < len(active_files) - 1:
                    active_index += 1
            elif active_command:
                lines.append("{}: {}".format(active_command, line))
            else:
                lines.append(line)
    return lines


def is_expected_delete_miss(command, lowered_line):
    return command in ("delete", "mdel") and any(
        pattern in lowered_line for pattern in EXPECTED_DELETE_MISS_PATTERNS
    )


def parse_ftp_command(line):
    match = re.match(r'^ftp>\s*(put|mput|delete|mdel)\s+(.+)$', line.strip(), re.IGNORECASE)
    if not match:
        return None
    command = match.group(1).lower()
    files = re.findall(r'"([^"]+)"', match.group(2))
    if not files:
        files = [part for part in match.group(2).split() if part]
    return command, files


def active_file(files, index):
    if not files:
        return None
    if index < 0:
        index = 0
    if index >= len(files):
        index = len(files) - 1
    return files[index]


if __name__ == "__main__":
    sys.exit(main_guard(main, tool_name="kpush"))
