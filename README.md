# rossum

`rossum` is a CMake-like Ninja build-file generator for FANUC Robotics KAREL projects. Projects are package-based: each package declares sources, dependencies, and optional TP, test, interface, form, and data targets in `package.json`.

See [MODERN_CLI.md](MODERN_CLI.md) for the complete modern command-line workflow and troubleshooting reference.

## Quick start

Rossum requires an out-of-source build directory. From the build directory, configure the source tree and build it:

```powershell
mkdir C:\work\build
cd C:\work\build
rossum .. -l -nn
```

`-l` includes the package's LS/TP files and `-nn` runs Ninja immediately after configuration. The normal deployment and test sequence is:

```powershell
kpush
kunit
```

For a complete build configuration, use the flags needed for your package:

```powershell
rossum .. -s -l -t -i -f -nn
```

- `-s`, `--buildsource`: KAREL source from manifests.
- `-l`, `--build-tp`: LS/TP files from manifests.
- `-t`, `--include-tests`: test programs and test dependencies.
- `-i`, `--build-interfaces`: generated TP interfaces for KAREL routines.
- `-f`, `--build-forms`: FANUC forms.
- `-b`, `--buildall`: build dependency objects as well.
- `-tp`, `--compiletp`: compile TP+ output to `.tp`; otherwise retain interpreted output.
- `-DNAME=VALUE`: define a preprocessor macro.
- `-o`, `--preserve-build-paths`: retain package-relative output paths.

`rossum <SRC> <BUILD> --ninja` is the long-form equivalent of `-nn`; use `--ninja-target TARGET` (repeatable) and `--ninja-jobs N` to control that invocation. `-n` means `--no-env`; it does not run Ninja.

## Modern CLI

Run `rossum` without arguments in a valid build directory to open the interactive build console. You can also open it explicitly with `rossum --shell [SRC] [BUILD]`.

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

The non-interactive equivalents are suitable for scripts and CI:

```powershell
rossum build .\build -j 4
rossum manifest check .\build
rossum timings .\build --top 12
rossum doctor .\src --build-dir .\build
```

`rossum build` wraps Ninja with clearer Rossum failure reporting. `manifest check` finds manifest entries whose generated files are missing; `timings` summarizes `.ninja_log`; and `doctor` checks paths, `robot.ini`, package locations, and expected build files.

### Uploading with kpush

`kpush` validates `.man_log` and the selected local files, writes `ftp.txt`, runs Windows FTP, and saves FTP output to `<build>\ftp.log`.

```powershell
kpush --check                 # Validate only
kpush --dry-run               # Show the deployment plan
kpush --only karel,tp         # Limit selected groups
kpush --skip data --script-only
kpush --delete                # Delete manifest files from the controller
```

Groups are `karel`, `tp`, `forms`, `data`, and `interface`. `--ip ADDRESS`, `--build-dir PATH`, `--manifest PATH`, and `--timeout SECONDS` override the normal values.

### Running KUnit

`kunit` calls the controller HTTP endpoint directly and writes its response to `<build>\kunit.log`.

```powershell
kunit --dry-run
kunit --program TEST_ONE --program TEST_TWO
```

It also accepts `--ip`, `--build-dir`, `--manifest`, and `--timeout`.

### Cleaning

Clean only from the generated build directory:

```powershell
cd .\build
rossum --clean
```

Rossum refuses to clean unless the current directory is the target, is named `build`, and contains `build.ninja`. Cleanup sends items to the recycle bin. `rossum --clean --force` overrides those safety checks and should be used only after verifying the target directory.

## Installation

1. Install Git, Python, Ninja, and FANUC Roboguide/OLPC tooling.
2. Clone Rossum and its submodules:

   ```powershell
   git clone https://github.com/kobbled/rossum --recurse-submodules
   ```

3. Run the installer, optionally passing a virtual-environment path:

   ```powershell
   . .\install.ps1 <path-to-venv> <update-env-variables>
   ```

Alternatively, install the Python dependencies manually and ensure `bin`, Ninja, and the required FANUC tools are on `PATH`:

```powershell
pip install -r requirements.txt
```

Add dependency package roots to `ROSSUM_PKG_PATH` (semicolon-separated). The installer configures the bundled `ktransw` and `yamljson2xml` dependencies; a manual setup must make their required executables available as well.

## Configuration

Create `robot.ini` in the source root with `setrobot`, then add the Rossum-specific controller and TP+ environment settings when applicable:

```ini
[WinOLPC_Util]
Robot=\path\to\workcell
Version=V9.10-1
Path=C:\Program Files (x86)\FANUC\WinOLPC\Versions\V910-1\bin
Support=\path\to\support
Output=\path\to\output
Ftp=127.0.0.1
Env=C:\absolute\path\to\env.tpp
```

`Env` must be an absolute path. Important environment variables are:

- `ROSSUM_CORE_VERSION`: default KAREL core version (for example, `V910-1`).
- `ROSSUM_PKG_PATH`: dependency package roots.
- `ROSSUM_SERVER_IP`: default controller IP for FTP transfers.

## Package manifests

Packages use `package.json` (or another `p*.json` manifest) to declare build content. Common keys include `source`, `includes`, `depends`, `tp`, `tests`, `tests-depends`, `tp-interfaces`, `forms`, `macros`, and `tpp_compile_env`.

```json
{
  "manver": "1",
  "project": "example-package",
  "version": "0.0.1",
  "source": ["src/example.kl"],
  "includes": ["include"],
  "depends": ["Strings"],
  "tp": ["tp/move.ls"],
  "tests": ["test/test_example.kl"],
  "macros": ["DEBUG=TRUE"]
}
```

Supported source types include KAREL (`.kl`), LS/TP (`.ls`), TP+ (`.tpp`), dictionaries (`.utx`), forms (`.ftx`), and JSON/YAML/CSV controller data.

## Example workspace

See [rossum_example_ws](https://github.com/kobbled/rossum_example_ws) for a working multi-package project.

## Disclaimer

WinOLPC, OLPCpro, and Roboguide are products of FANUC America Corporation. The Rossum authors are not affiliated with FANUC.
