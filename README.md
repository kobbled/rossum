# rossum
v0.2.1

This is `rossum`, a CMake-like build file generator for Fanuc Robotics (Karel)
projects.


## Overview

This tool introduces a package based workflow for Karel development: packages are directories that contain a marker file (a *manifest*) that contains some metadata describing the dependencies of that package and any translatable targets. Detection of packages and generation of the build file is done once at configuration time, relying on the build tool's dependency resolution to build all targets in the correct order.


## Requirements

* `rossum` was written in Python 3. Python dependencies can be installed with
```python
pip install -r requirements.txt
```
* This package will only work on Windows. Karel compilers currently have no support on linux machines, nor does Roboguide.
* The generated Ninja build files require a recent (> 1.7.1) version of [Ninja][] to be present.
* For translating Karel sources, `rossum` expects [ktransw][] version 0.2.2 or newer. Refer to the `ktransw` documentation for any additional requirements that `ktransw` may have.
* yaml and json conversion into xml is done with the [yamljson2xml](https://github.com/kobbled/yamljson2xml) python package. Follow readme file of the repository to install.
* FANUC Roboguide must also be installed with OPLC bin programs, **maketp**, **ktrans**, and **setrobot**. An emulation of your workcell should be made through Roboguide or OLPCpro, typically stored in *%USERPROFILE%/Documents\My Workcells*.


## Installation

The 0.2.0 release is a convenience release that includes all the necessary
tools to quickly setup a working installation of rossum. Download it from the
[releases][] page.

Alternatively, clone this repository to your machine and add the directory
containing `rossum.py` and `rossum.cmd` to your `PATH`. Command sessions
opened after setting up the `PATH` should be able to successfully run `rossum`
from anywhere.

For installation of `ktransw`, see [ktransw][].

For maximum convenience, make sure that `ninja.exe` and `ktransw.cmd` are also
on the `PATH`. An alternative would be to copy `ninja.exe` to the build
directory of the workspace (the one containing the generated build file) and
to specify the path to `ktransw.cmd` as a command line argument to `rossum`.
Note that this would have to be repeated each time a new build directory is
created.

| :warning: WARNING          |
|:---------------------------|

On windows machines the `python` alias can be overwritten by the py launcher where python is started in the terminal with `py -3`. The batch files are written with the `python` key. To create the alias type this into powershell:

```powershell
Set-Alias -Name python -Value "path\to\Python\Python39\python.exe"
```

replacing the value with the full path to the python executable in your PATH environment variables.

## Examples

Please see [rossum_example_ws][] for an example workspace with some packages
that show how to use `rossum`.

## currently handled files

* Karel (.kl)
* LS files (.ls)
* TP-Plus (.tpp)
* JSON (.json)
* YAML (.yaml)
* CSV (.csv)
* FANUC Dictionary (.utx)
* FANUC Form (.ftx)

> **_NOTE:_** Look at the User Form example in [rossum_example_ws][], *basic_test\lib_a*. Preprocessor directives have been expanded in .utx, and .ftx files using [ktransw][]. In order to properly compile dictionary files, `ninja` might have to be run twice to first create the karel include file, and then build the accompanying karel file. 


## Usage

**standard**

```
  mkdir C:\foo\bar\build
  cd C:\foo\bar\build
  rossum C:\foo\bar\src
  kpush
```

**clean out build file**

```
  cd C:\foo\bar\build
  rossum --clean
```

**use robot.ini version, and ip address**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -o
```

**output test files from package.json**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -t
```

**build programs to interface karel routines in TP programs**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -i
```

> **_NOTE:_**  This option depends on the [kl-TPE](https://github.com/kobbled/kl-TPE),[kl-pose](https://github.com/kobbled/kl-pose), and [kl-registers](https://github.com/kobbled/kl-registers) packages from the [Ka-Boost](https://github.com/kobbled/Ka-Boost) libraries. If Ka-Boost is installed make sure to add theses libraries to the dependencies of the package you are build in with this option.

```json
{
  "depends" : [
    "registers",
    "TPElib"
  ]
}
```

**keep preprocessor output in %TEMP%**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -g
```

**build all dependencies**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -b
```

**build with user macro %define DEBUG**

```
  cd C:\foo\bar\build
  rossum C:\foo\bar\src -DDEBUG=TRUE
```

**--help output**

```
usage: rossum [-h] [-v] [-V] [-q] [--rg64] [-c ID] [--support PATH] [-d]
              [--ktrans PATH] [--ktransw PATH] [-n] [-p PATH] [-r INI] [-w]
              SRC [BUILD]

Version 0.1.7

A cmake-like Makefile generator for Fanuc Robotics (Karel) projects
that supports out-of-source builds.

positional arguments:
  SRC                   Main directory with packages to build
  BUILD                 Directory for out-of-source builds (default: 'cwd')

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Be verbose
  -V, --version         show program's version number and exit
  -q, --quiet           Be quiet (only warnings and errors will be shown)
  --rg64                Assume 64-bit Roboguide version.
  -c ID, --core ID      Version of the core files used when translating
                        (default: V7.70-1). Use the 'ROSSUM_CORE_VERSION'
                        environment variable to configure an alternative
                        default without having to specify it on each
                        invocation of rossum.
  --support PATH        Location of KAREL support directory (default: auto-
                        detect based on selected core version and FANUC
                        registry keys)
  -d, --dry-run         Do everything except writing to build file
  --ktrans PATH         Location of ktrans (default: auto-detect)
  --ktransw PATH        Location of ktransw (default: assume it's on the
                        Windows PATH)
  -n, --no-env          Do not search the ROSSUM_PKG_PATH, even if it is set
  -p PATH, --pkg-dir PATH
                        Additional paths to search for packages (multiple
                        allowed). Note: this essentially extends the source
                        space.
  -r INI, --robot-ini INI
                        Location of robot.ini (default: source dir)
  -w, --overwrite       Overwrite any build file that may exist in the build
                        dir
  --ftp                 Use IP address in environment variable 
                        'ENV_SERVER_IP' to send files in build folder to
                        Controller with 'kpush' command.
  -o --override         Will override environment variables with contents of
                        robot.ini file.
  -b --buildall         build all dependencies as well
  -g --keepgpp          keep gpp preprocessor output in %TEMP% folder to
                        evaluate bugs.
  -tp --compiletp       compile .tpp files into .tp files. If false will 
                        just interpret to .ls.
  -t  --include-tests   include test files in build
  -i  --build-interfaces   build tp interfaces for karel 
                        routines specified in package.json.
                        This is needed to use karel routines within a tp program
  -D  /D                Define user macros from command line
  --clean               clean all files out of build directory
```

## robot.ini file example

create robot.ini file in the top level of the source directory calling **setrobot** through a command prompt, and selecting the correct workcell created with Roboguide. *Ftp*, and *Tpp-env* will need to be added afterwards as they are Rossum specific directives.

```
[WinOLPC_Util]
Robot=\C\Users\<user>\Documents\My Workcells\cell\Robot_1
Version=V9.10-1
Path=C:\Program Files (x86)\FANUC\WinOLPC\Versions\V910-1\bin
Support=C:\Users\<user>\Documents\My Workcells\cell\Robot_1\support
Output=C:\Users\<user>\Documents\My Workcells\cell\Robot_1\output
Ftp=127.0.0.1
Tpp-env=C:\Users\<user>\Documents\My Workcells\cell\tpp\vars.tpp
```

## package.json file example

```json
{
  "manver" : "1",
  "project" : "kl-lib",
  "description" : "",
  "version" : "0.0.2",
  "license" : "MIT",
  "author" : "name",
  "source" : [
    "src/source.kl"
  ],
  "tests" : [
    "test/test_source.kl"
  ],
  "includes" : [
    "include"
  ],
  "depends" : [
    "KUnit",
    "Strings",
    "math",
    "registers",
    "TPElib",
    "ktransw-macros"
  ],
  "tp-interfaces" : [
    {"routine" : "source__func01", "program_name" : "func01"},
    {"routine" : "source__func02", "program_name" : "func02"},
  ],
  "macros" : [
    "DEBUG=TRUE",
    "BUILD_LOG=FALSE"
  ]
}
```

### tp-interfaces

Teach pendant interfaces are a way of exposing karel routines, for usage in teach pendant (TP) programs. Inherently you are not allowed to access karel routines with the *CALL* function in TP programs. You are able to call karel programs within TP programs. Rossum provides a way to automatically create a karel program wrapper around a specified routine. For instance if you want to expose a routine definition:

```
ROUTINE func01(i : INTEGER; r : REAL; p : XYZWPR) : INTEGER
```

and create a wrapper program called **tp_func01**, you can define an interface in the package manifest:

```
"tp-interfaces" : [
    {"routine" : "func01", "program_name" : "tp_func01"}
  ]
```

This will output a karel program to \<src\>/tp/ . If there is a return type the last arguement will be the register number to store the result in.

If an input argument is a position type, the corresponding TPE arguement is the position register number where the input data is stored.

**currently handled types**

* INTEGER
* REAL
* STRING
* XYZWPR
* JOINTPOS

### user macros

package/project wide pre-processor macros can be defined either from the command line or the package manifest. From the command line macros are invoked the same way they are in GPP (see [GPP documentation][GPP]), with **-D***name=val*, or **/D***name=val*. Macros can be included in the package manifest as shown in [example package.json](#packagejson-file-example).

## Environment variables

```
set PATH=%PATH%;C:\path\to\rossum-0.1.4-distrib\
set ROSSUM_CORE_VERSION=V910-1
set ROSSUM_PKG_PATH \path\to\rossum\dependency\packages
set ROSSUM_SERVER_IP 127.0.0.1
```

`rossum` checks for the existence of two environment variables and uses their
contents to change its behaviour.

### ROSSUM_PKG_PATH

The `ROSSUM_PKG_PATH` should contain (a) path(s) to one or more directories
containing rossum packages. All directories will be searched.

### ROSSUM_CORE_VERSION

The `ROSSUM_CORE_VERSION` variable can be used to specify a 'system wide'
default core version that should be used for all invocations of `ktransw`,
unless the default is overriden using the `--core` option.

Example: to make version 8.30 of the support files the default set
`ROSSUM_CORE_VERSION` to `V8.30-1`.


## Glossary

Terminology used by `rossum`.

### package
A directory containing any number of source and header files, organised into
`src` and `include` sub directories, along with a JSON package manifest. The
manifest declares translationable binary targets and additional meta-data such
as build dependencies (other `rossum` packages), author, version and test
binaries.

### workspace
A directory containing a set of `rossum` compatible packages. Note that while
possible, packages are typically not directly stored in the top-level workspace
directory, but in a *source space* sub directory.

### source space
The sub directory of the *workspace* that contains a set of of `rossum`
compatible packages. Usually named `src`.

### build space
The sub directory of the *workspace* that will store all the build output
(p-code files).

### build file
The ninja build file generated by `rossum` at the end of the configuration
phase.


## Disclaimer

WinOLPC, OlpcPRO and Roboguide are products of Fanuc America Corporation. The
author of `rossum` is not affiliated with Fanuc in any way.



[ninja]: https://ninja-build.org
[ktransw]: https://github.com/kobbled/ktransw_py
[EmPy]: https://pypi.python.org/pypi/EmPy
[releases]: https://github.com/kobbled/rossum/releases
[rossum_example_ws]: https://github.com/kobbled/rossum_example_ws
[Installing Python on Windows]: http://docs.python-guide.org/en/latest/starting/install/win/
[GPP]: https://files.nothingisreal.com/software/gpp/gpp.html