# CLAUDE.md

## Project overview

Rossum generates Ninja build files for FANUC KAREL projects. A source space contains packages (directories with `p*.json` manifests); Rossum configures an out-of-source build directory, then Ninja produces the controller artifacts.

The command-line workflow is deliberately small:

```powershell
# From an existing build directory.
rossum .. -l -nn   # Configure TP/LS outputs and build them.
kpush              # Upload the generated outputs.
kunit              # Run KUnit programs, if configured.
```

Use `-s` for KAREL source, `-t` for tests, `-i` for generated TP interfaces, `-f` for forms, and `-b` to build dependency objects as well. `-l` includes the manifest's LS/TP files. Modes can be combined:

```powershell
rossum .. -s -l -t -i -f -nn
```

## Modern CLI

Run `rossum` with no arguments from a valid build directory to open the interactive shell. The same shell is available explicitly with `rossum --shell [SRC] [BUILD]`.

```text
/status
/config [tp|tests|source|all]
/build [tp|tests|source|all]
/send [--dry|--only tp|--skip data]
/test [--list|program]
/clean
/check [tools|manifest|robot]
/log [build|send|test]
/exit
```

For automation, use the non-interactive commands:

```powershell
rossum build .\build -j 4               # Ninja with Rossum error summaries
rossum manifest check .\build           # Check .man_log against local outputs
rossum timings .\build --top 12         # Show slow Ninja edges
rossum doctor .\src --build-dir .\build # Check tools, robot.ini, and paths
```

`rossum <SRC> <BUILD> -nn` configures and invokes Ninja in one command. Use `--ninja-target TARGET` (repeatable) and `--ninja-jobs N` to control that Ninja invocation. `-nn`, `-N`, and `--ninja` are equivalent; `-n` continues to mean `--no-env`.

### Clean safety

`rossum --clean` must be run from the target build directory. It refuses to clean unless that directory is named `build` and contains `build.ninja`; items are sent to the recycle bin. `--force` is valid only with `--clean` and overrides those guards, so use it only after verifying the target:

```powershell
cd .\build
rossum --clean
```

### Upload and test commands

`kpush` reads `.man_log`, validates the selected local files, writes `ftp.txt`, runs Windows FTP, and saves its output as `ftp.log` in the build directory. Start with a no-transfer check when diagnosing deployment:

```powershell
kpush --check
kpush --dry-run
kpush --only karel,tp
kpush --skip data --script-only
kpush --delete
```

Available deployment groups are `karel`, `tp`, `forms`, `data`, and `interface`. `--ip ADDRESS`, `--build-dir PATH`, `--manifest PATH`, and `--timeout SECONDS` support automation and overrides.

`kunit` calls the robot HTTP endpoint directly and saves the response as `kunit.log` in the build directory:

```powershell
kunit --dry-run
kunit --program TEST_ONE --program TEST_TWO
```

Use `--ip`, `--build-dir`, and `--timeout` when the defaults from `.man_log` are not appropriate.

## Architecture

```text
Package manifests -> package discovery -> dependency/include/macro resolution
                  -> build.ninja and .man_log -> Ninja -> kpush / kunit
```

- `bin/rossum.py` is the configuration tool, modern subcommands, interactive shell, manifest maintenance, and Ninja diagnostics.
- `bin/rossum_cli.py` provides the shared console, subprocess, and error UI.
- `bin/kpush.py` builds and executes validated FTP deployment plans.
- `bin/kunit.py` runs KUnit requests through the controller HTTP endpoint.
- `bin/templates/build.ninja.em` renders generated Ninja rules.

## Development

```powershell
pip install -r requirements.txt
python -m unittest discover -s tests
python bin\rossum.py --help
python bin\kpush.py --help
python bin\kunit.py --help
```

Keep generated artifacts out of source package directories. When changing CLI behaviour, keep `README.md` and `MODERN_CLI.md` aligned with the actual `--help` output.

## Configuration

`robot.ini` is normally in the source root and is created with `setrobot`. Rossum additionally uses `Ftp` for controller address and `Env` for the absolute TP+ environment-file path.

Important environment variables:

- `ROSSUM_CORE_VERSION`: default FANUC support/core version.
- `ROSSUM_PKG_PATH`: semicolon-separated dependency package roots.
- `ROSSUM_SERVER_IP`: default FTP controller address.
