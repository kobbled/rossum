# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Rossum** is a CMake-like build file generator for FANUC Robotics (Karel) projects. It implements a package-based workflow that generates Ninja build files from JSON package manifests, supporting out-of-source builds.

## Build & Development Commands

```powershell
# Install dependencies (from repo root)
pip install -r requirements.txt

# Standard build workflow
mkdir C:\project\build
cd C:\project\build
rossum C:\project\src    # Generate build.ninja
ninja                    # Execute build
kpush                    # Transfer files to controller

# Common rossum options
rossum <src> -s          # Build source files from package.json
rossum <src> -t -s       # Include test files
rossum <src> -i          # Build TP interfaces for Karel routines
rossum <src> -b          # Build all dependencies
rossum <src> -g          # Keep preprocessor output for debugging
rossum <src> -DDEBUG=TRUE  # Define preprocessor macro
rossum --clean           # Clean build directory

# Transfer files to controller
kpush                    # Push built files via FTP
kpush --delete           # Delete files from controller
```

## Architecture

### Pipeline Flow

```
Source Directory (packages with p*.json manifests)
    ↓
Package Discovery (find_pkgs)
    ↓
Manifest Parsing (parse_manifest → RossumManifest)
    ↓
Dependency Graph Resolution (create_dependency_graph)
    ↓
Include Path Resolution (resolve_includes)
    ↓
Macro Processing (resolve_macros)
    ↓
EmPy Template Generation (build.ninja.em)
    ↓
Ninja Build File Output (build.ninja)
```

### Key Files

- `bin/rossum.py` - Main orchestrator (~1,600 lines), handles entire build pipeline
- `bin/kpush.py` - FTP wrapper for transferring compiled files to FANUC controller
- `bin/kunit.py` - Unit test runner via controller HTTP API
- `bin/templates/build.ninja.em` - EmPy template for Ninja build file generation
- `bin/templates/ftp.txt.em` - EmPy template for FTP transfer scripts

### Data Structures (namedtuples in rossum.py)

- `RossumManifest` - Parsed package.json contents
- `RossumPackage` - Package with dependencies, includes, and object files
- `RossumWorkspace` - Build/source spaces and packages
- `robotiniInfo` - Parsed robot.ini configuration
- `KtransInfo` - Karel compiler tools location
- `Graph` - Dependency graph (lines 1491-1582)

### Git Submodules

- `deps/ktransw` - Karel translator wrapper (ktransw.py)
- `deps/yamljson2xml` - YAML/JSON to XML converter for controller

## Configuration Files

### robot.ini (project root)
Generated via `setrobot` command. Add `Ftp` and `Env` fields manually:
```ini
[WinOLPC_Util]
Robot=\path\to\workcell
Version=V9.10-1
Path=C:\Program Files (x86)\FANUC\WinOLPC\Versions\V910-1\bin
Support=\path\to\support
Output=\path\to\output
Ftp=127.0.0.1
Env=C:\path\to\env.tpp
```

### package.json (in each package directory)
Manifest file with fields: `manver`, `project`, `version`, `source`, `includes`, `depends`, `tp`, `tests`, `tests-depends`, `tp-interfaces`, `macros`, `tpp_compile_env`

## Environment Variables

- `ROSSUM_CORE_VERSION` - Default Karel core version (e.g., `V910-1`)
- `ROSSUM_PKG_PATH` - Search paths for dependency packages (semicolon-separated)
- `ROSSUM_SERVER_IP` - Default controller IP for FTP transfers

## Supported File Types

| Extension | Type | Compiled To |
|-----------|------|-------------|
| `.kl` | Karel source | `.pc` (p-code) |
| `.ls` | TP list | Direct use |
| `.tpp` | TP-Plus | `.tp` or `.ls` |
| `.utx` | Dictionary | `.tx` |
| `.ftx` | Form | `.tx` |
| `.json`, `.yaml`, `.csv` | Data | `.xml` via yamljson2xml |

## Key Implementation Details

- `BUILD_STANDALONE` flag in rossum.py switches between script mode (`.cmd` wrappers) and exe mode (`.exe` tools)
- Package manifests are matched with glob pattern `p*.json` (e.g., `package.json`, `pkg.json`)
- EmPy 3.3.4 is pinned due to compatibility (recent fix for EmPy 4.2)
- Paths with spaces in folder names require special handling in ninja manifests
