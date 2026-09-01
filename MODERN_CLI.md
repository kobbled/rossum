# Rossum CLI

CLI means command-line interface: the commands typed in PowerShell.

The goal is to keep the workflow simple:

```powershell
rossum -l ..
ninja
kpush
kunit
```

The upgrade is not meant to make users memorize many new commands. The main
improvements are inside the existing tools:

- better formatted output
- clearer failures with suggested fixes
- safer robot upload behavior
- useful log files when external tools fail
- color/tables/status output when `rich` is installed
- plain text output when `--no-color` is used or `NO_COLOR` is set

## Normal workflow

Configure:

```powershell
rossum .. -l
```

Build:

```powershell
ninja
```

Configure and build in one command:

```powershell
rossum .. -l -nn
```

`-nn` means run Ninja after Rossum configures the build. Lowercase `-n` is not
used because it already means `--no-env`. `-N` still works as a compatibility
alias.

Upload:

```powershell
kpush
```

Run KUnit:

```powershell
kunit
```

## kpush

`kpush` now validates the manifest and local files before contacting the robot.
It generates `ftp.txt`, runs Windows FTP itself, captures FTP output, and reports
likely transfer failures.

Simple safe checks:

```powershell
kpush --check
kpush --dry-run
```

The FTP log is written to:

```text
<build>\ftp.log
```

Windows FTP does not always return precise error codes. Rossum therefore checks
the FTP output for common controller/network failure messages and reports the
matching lines with the full log path.

## Cleaning

Run clean only from the generated build directory:

```powershell
cd .\build
rossum --clean
```

Rossum refuses to clean when the current directory is not the clean target,
when the directory is not named `build`, or when `build.ninja` is missing.
`rossum --clean --force` overrides those checks and should only be used after
verifying the target directory.

## kunit

`kunit` now sends the robot HTTP request directly instead of shelling out to
`curl`.

Simple safe check:

```powershell
kunit --dry-run
```

The KUnit response is written to:

```text
<build>\kunit.log
```

## Troubleshooting commands

These are optional. They are not part of the normal workflow.

```powershell
rossum doctor .. --build-dir .\build
rossum manifest check .\build
rossum timings .\build
rossum build .\build --dry-run
```

Use them when diagnosing tool paths, stale manifests, slow build files, or Ninja
failures.
