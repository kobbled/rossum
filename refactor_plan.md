# Rossum Refactoring Plan

This document outlines a plan to modularize `bin/rossum.py` from a monolithic ~1,600 line file into a proper Python package structure.

## Current Structure Analysis

### File Breakdown (1,586 lines)

| Section | Lines | Description |
|---------|-------|-------------|
| **Imports & Constants** | 1-114 | Version, suffixes, paths, tool names |
| **Exceptions** | 117-124 | 3 custom exception classes |
| **Data Structures** | 127-211 | 11 namedtuples for data containers |
| **main()** | 221-680 | Entry point, orchestration (~460 lines) |
| **Package Discovery** | 684-794 | Finding and parsing packages |
| **Dependency Resolution** | 796-891 | Graph building, filtering |
| **Include/Macro Resolution** | 893-953 | Path and macro processing |
| **TP Interface Generation** | 955-1206 | Karel wrapper code generation (~250 lines) |
| **Object Mapping** | 1208-1277 | Source-to-object file mapping |
| **Tool Discovery** | 1280-1367 | Finding FANUC tools, registry lookup |
| **robot.ini Handling** | 1369-1459 | INI file parsing |
| **Manifest Writing** | 1461-1487 | YAML manifest output |
| **Graph Class** | 1491-1582 | Dependency graph implementation |

---

## Proposed Modular Structure

```
rossum/
├── __init__.py              # Package init, version
├── __main__.py              # Entry point: python -m rossum
├── cli.py                   # Argument parsing, main() orchestration
├── config/
│   ├── __init__.py
│   ├── constants.py         # All constants, suffixes, paths, env vars
│   └── robot_ini.py         # robot.ini finding and parsing
├── models/
│   ├── __init__.py
│   └── types.py             # All namedtuples (data structures)
├── exceptions.py            # Custom exceptions
├── discovery/
│   ├── __init__.py
│   ├── packages.py          # Package finding, manifest parsing
│   └── tools.py             # FANUC tool discovery, registry lookup
├── resolution/
│   ├── __init__.py
│   ├── dependencies.py      # Dependency graph creation, filtering
│   ├── includes.py          # Include path resolution
│   └── macros.py            # Macro resolution
├── graph.py                 # Graph class for dependencies
├── generation/
│   ├── __init__.py
│   ├── interfaces.py        # TP interface Karel code generation
│   ├── mappings.py          # Source-to-object mappings
│   └── manifest.py          # Build manifest writing
└── templates/
    ├── build.ninja.em
    └── ftp.txt.em
```

---

## Module Breakdown

### 1. `rossum/config/constants.py`
**Lines to extract:** 44-114

Contains:
- `ROSSUM_VERSION`
- File suffixes (`KL_SUFFIX`, `PCODE_SUFFIX`, etc.)
- Environment variable names
- Search paths (`FANUC_SEARCH_PATH`, `KTRANS_SEARCH_PATH`)
- Tool binary names
- `BUILD_STANDALONE` flag

### 2. `rossum/exceptions.py`
**Lines to extract:** 117-124

Contains:
- `MissingKtransException`
- `InvalidManifestException`
- `MissingPkgDependency`

### 3. `rossum/models/types.py`
**Lines to extract:** 127-211

Contains all namedtuples:
- `KtransSupportDirInfo`, `KtransInfo`, `KtransWInfo`, `KtransRobotIniInfo`
- `RossumManifest`, `RossumPackage`, `RossumSpaceInfo`, `RossumWorkspace`
- `robotiniInfo`, `packages`, `TPInterfaces`

### 4. `rossum/config/robot_ini.py`
**Lines to extract:** 1369-1459

Functions:
- `find_robotini(source_dir, args)` - Locates robot.ini
- `parse_robotini(fpath)` - Parses INI into `robotiniInfo`

### 5. `rossum/discovery/packages.py`
**Lines to extract:** 684-794

Functions:
- `find_files_recur(top_dir, pattern)` - Recursive file search
- `parse_manifest(fpath, args)` - JSON to `RossumManifest`
- `find_pkgs(dirs, args)` - Discover packages
- `remove_duplicates(pkgs)` - Deduplicate packages
- `find_in_list(l, pred)` - Lambda-based list search

### 6. `rossum/discovery/tools.py`
**Lines to extract:** 1280-1367

Functions:
- `find_fr_install_dir(search_locs, is64bit)` - Registry/filesystem search for FANUC
- `find_program(tool, search_locs)` - Generic program finder
- `find_ktrans_support_dir(fr_base_dir, version_string)` - Support directory
- `find_tools(search_locs, tools, args)` - Multi-tool discovery

### 7. `rossum/resolution/dependencies.py`
**Lines to extract:** 796-891

Functions:
- `create_dependency_graph(source_pkgs, all_pkgs, args)` - Build graph
- `add_dependency(src_package, visited, args, graph, pkgs)` - Recursive traversal
- `log_dep_tree(graph)` - Debug logging
- `filter_packages(pkgs, graph)` - Filter to relevant packages

### 8. `rossum/resolution/includes.py`
**Lines to extract:** 893-943

Functions:
- `dedup(seq)` - Order-preserving deduplication
- `resolve_includes(pkgs, args)` - Gather include dirs
- `resolve_includes_for_pkg(pkg, visited, args)` - Recursive include resolution

### 9. `rossum/resolution/macros.py`
**Lines to extract:** 945-953

Functions:
- `resolve_macros(pkgs, args)` - Merge CLI and manifest macros

### 10. `rossum/graph.py`
**Lines to extract:** 1491-1582

Contains:
- `Graph` class - Dependency graph with DFS traversal
- `graph_tests()` - Test function (could move to tests/)

### 11. `rossum/generation/interfaces.py`
**Lines to extract:** 955-1206

Functions:
- `get_interfaces(pkgs)` - Extract TP interfaces from manifests
- `create_interfaces(interfaces)` - Generate Karel wrapper programs

This is the largest single module (~250 lines) and handles complex code generation.

### 12. `rossum/generation/mappings.py`
**Lines to extract:** 1208-1277

Functions:
- `gen_obj_mappings(pkgs, mappings, args, dep_graph)` - Source-to-object mapping

### 13. `rossum/generation/manifest.py`
**Lines to extract:** 1461-1487

Functions:
- `write_manifest(manifest, files, ipAddress)` - Write `.man_log` YAML

### 14. `rossum/cli.py`
**Lines to extract:** 221-680 (refactored)

Contains:
- `parse_args()` - Argument parsing (extracted from main)
- `validate_paths(args)` - Path validation
- `setup_logging(args)` - Logger configuration
- `configure_tools(args, robot_ini_info)` - Tool path setup
- `main()` - Orchestration (significantly smaller after extraction)

---

## Refactoring Benefits

| Benefit | Description |
|---------|-------------|
| **Testability** | Each module can be unit tested independently |
| **Maintainability** | Changes isolated to specific modules |
| **Readability** | Smaller files with clear responsibilities |
| **Reusability** | `Graph`, `discovery`, `generation` modules usable elsewhere |
| **Onboarding** | New contributors can understand smaller pieces |

---

## Suggested Implementation Order

### Phase 1: Extract data models
- `models/types.py`
- `exceptions.py`
- `config/constants.py`

### Phase 2: Extract utilities
- `graph.py`
- `config/robot_ini.py`

### Phase 3: Extract discovery
- `discovery/packages.py`
- `discovery/tools.py`

### Phase 4: Extract resolution
- `resolution/dependencies.py`
- `resolution/includes.py`
- `resolution/macros.py`

### Phase 5: Extract generation
- `generation/interfaces.py`
- `generation/mappings.py`
- `generation/manifest.py`

### Phase 6: Refactor CLI
- `cli.py`
- `__main__.py`

---

## Implementation Considerations

1. **Logger access** - Currently uses global `logger`. Should pass logger or use module-level loggers.

2. **Circular imports** - `models/types.py` should have no dependencies on other rossum modules.

3. **BUILD_STANDALONE flag** - Affects tool names; should be handled in `constants.py` with conditional logic.

4. **Backward compatibility** - Keep `bin/rossum.py` as a thin wrapper that imports from the package.

5. **Testing** - Add unit tests for each module as it's extracted.
