#!/usr/bin/python
#
# Copyright (c) 2016-2019 G.A. vd. Hoorn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#
# rossum - a 'cmake for Fanuc Karel'
#
# Prerequisites:
#  - a recent Python version (2.7.x or 3.4.x)
#  - ninja build system (https://ninja-build.org)
#  - EmPy
#


import em
import re
import datetime
import os, shutil
import sys
import json
import yaml
import configparser
import fnmatch
import time
import shlex
from send2trash import send2trash

import collections

from rossum_cli import CliError, Console, fail_missing_file, install_tracebacks, main_guard, print_box, print_error_panel, run_command, run_command_live, write_text

import logging
logger=None

#Turn on for building executable
BUILD_STANDALONE = False
# -------


ROSSUM_VERSION='0.1.7'


_OS_EX_USAGE=64
_OS_EX_DATAERR=65

KL_SUFFIX = 'kl'
PCODE_SUFFIX = 'pc'
TP_SUFFIX = 'ls'
TPCODE_SUFFIX = 'tp'
TPP_SUFFIX = 'tpp'
TPP_INTERP_SUFFIX = 'ls'
YAML_SUFFIX = 'yml'
XML_SUFFIX = 'xml'
CSV_SUFFIX = 'csv'
FORM_SUFFIX = 'ftx'
DICT_SUFFIX = 'utx'
COMPRESSED_SUFFIX = 'tx'

FILE_MANIFEST = '.man_log'


ENV_PKG_PATH='ROSSUM_PKG_PATH'
ENV_DEFAULT_CORE_VERSION='ROSSUM_CORE_VERSION'
ENV_SERVER_IP='ROSSUM_SERVER_IP'

BUILD_FILE_NAME='build.ninja'
BUILD_FILE_TEMPLATE_NAME='templates\\build.ninja.em'

FANUC_SEARCH_PATH = [
    'C:\\Program Files\\Fanuc',
    'C:\\Program Files (x86)\\Fanuc',
    'D:\\Program Files\\Fanuc',
    'D:\\Program Files (x86)\\Fanuc',
]

KTRANS_BIN_NAME='ktrans.exe'
MAKETP_BIN_NAME='maketp.exe'
TPP_BIN_NAME='tpp.bat'

if BUILD_STANDALONE:
  KTRANSW_BIN_NAME='ktransw.exe'
  XML_BIN_NAME='yamljson2xml.exe'
  KCDICT_BIN_NAME='kcdictw.exe'
else:
  KTRANSW_BIN_NAME='ktransw.cmd'
  XML_BIN_NAME='yamljson2xml.cmd'
  KCDICT_BIN_NAME='kcdictw.cmd'


KTRANS_SEARCH_PATH = [
    'C:\\Program Files\\Fanuc\\WinOLPC\\bin',
    'C:\\Program Files (x86)\\Fanuc\\WinOLPC\\bin',
    'D:\\Program Files\\Fanuc\\WinOLPC\\bin',
    'D:\\Program Files (x86)\\Fanuc\\WinOLPC\\bin',
]

ROBOT_INI_NAME='robot.ini'

MANIFEST_VERSION=1
MANIFEST_NAME='p*.json'

DEFAULT_CORE_VERSION='V7.70-1'

ROSSUM_IGNORE_NAME='ROSSUM_IGNORE'



class MissingKtransException(Exception):
    pass

class InvalidManifestException(Exception):
    pass

class MissingPkgDependency(Exception):
    pass


KtransSupportDirInfo = collections.namedtuple('KtransSupportDirInfo', 'path version_string')

KtransInfo = collections.namedtuple('KtransInfo', 'path support')

KtransWInfo = collections.namedtuple('KtransWInfo', 'path')

KtransRobotIniInfo = collections.namedtuple('KtransRobotIniInfo', 'path ftp env')

# In-memory representation of raw data from a parsed rossum manifest
RossumManifest = collections.namedtuple('RossumManifest',
    'depends '
    'description '
    'includes '
    'name '
    'source '
    'forms '
    'tp '
    'tests '
    'test_depends '
    'test_includes '
    'test_tp '
    'version '
    'interfaces '
    'interfaces_depends '
    'interface_files '
    'macros '
    'tpp_compile_env'
)

# a rossum package contains both raw, uninterpreted data (the manifest), as
# well as derived and processed information (dependencies, include dirs, its
# location and the objects to be build)
RossumPackage = collections.namedtuple('RossumPackage',
    'dependencies ' # list of pkg names that this pkg depends on
    'include_dirs ' # list of (absolute) dirs that contain headers this pkg needs
    'location '     # absolute path to root dir of pkg
    'manifest '     # the rossum manifest of this pkg
    'objects '      # list of (src, obj) tuples
    'tests '         # list of (src, obj) tuples for tests
    'macros' # user defines macros for global package context
)

# a rossum 'space' has:
#  - one path: an absolute path to the location of the space
RossumSpaceInfo = collections.namedtuple('RossumSpaceInfo', 'path')

# a rossum workspace has:
RossumWorkspace = collections.namedtuple('RossumWorkspace',
    'build '     #  - exactly one 'build space'
    'pkgs '      #  - zero or more packages
    'robot_ini ' #  - one robot-ini
    'sources'    #  - one or more 'source space(s)'
)

#container for contents of ini file
robotiniInfo = collections.namedtuple('robotiniInfo',
    'robot '
    'version '
    'base_path ' #base_path designates the base directory where WinOLPC
                 # or roboguide is installed eg. C:\Program Files (x86)\Fanuc\
    'version_path ' #version path is where applications for specified version are stored
                    # eg. C:\Program Files (x86)\Fanuc\WinOLPC\Versions\V910-1\bin
    'support '
    'output '
    'ftp ' # ftp address where the robot server resides
    'env' # environment file location for tp-plus
    )

# container datatype for graph class
packages = collections.namedtuple('packages',
    'name '
    'version '
    'inSource'
)

#TP program routine interfaces
TPInterfaces = collections.namedtuple('TPInterfaces',
    'name '
    'alias '
    'include_file '
    'depends '
    'path '
    'arguments '
    'return_type'
)









def main():
    import argparse

    if len(sys.argv) > 1 and sys.argv[1] in ('doctor', 'timings', 'manifest', 'build'):
        sys.exit(run_modern_command(sys.argv[1:]))
    if len(sys.argv) == 1 and is_rossum_build_dir(os.getcwd()):
        return run_interactive_shell(os.getcwd())

    description=("Version {0}\n\nA cmake-like Makefile generator for Fanuc "
        "Robotics (Karel) projects\nthat supports out-of-source "
        "builds.".format(ROSSUM_VERSION))

    epilog=("Usage example:\n\n"
        "  mkdir C:\\foo\\bar\\build\n"
        "  cd C:\\foo\\bar\\build\n"
        "  rossum C:\\foo\\bar\\src")

    parser = argparse.ArgumentParser(prog='rossum', description=description,
        epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
        help='Be verbose')
    parser.add_argument('-V', '--version', action='version',
        version='%(prog)s {0}'.format(ROSSUM_VERSION))
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet',
        help='Be quiet (only warnings and errors will be shown)')
    parser.add_argument('--no-color', action='store_true', dest='no_color',
        help='Disable colored output')
    parser.add_argument('--shell', action='store_true', dest='shell',
        help='Open the interactive Rossum shell')
    parser.add_argument('--rg64', action='store_true', dest='rg64',
        help='Assume 64-bit Roboguide version.')
    parser.add_argument('-c', '--core', type=str, dest='core_version',
        metavar='ID',
        default=(os.environ.get(ENV_DEFAULT_CORE_VERSION) or DEFAULT_CORE_VERSION),
        help="Version of the core files used when translating "
        "(default: %(default)s). Use the '{0}' environment "
        "variable to configure an alternative default without having to "
        "specify it on each invocation of rossum.".format(ENV_DEFAULT_CORE_VERSION))
    parser.add_argument('--support', type=str, dest='support_dir',
        metavar='PATH', help="Location of KAREL support directory "
            "(default: auto-detect based on selected core version and "
            "FANUC registry keys)")
    parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
        help='Do everything except writing to build file')
    parser.add_argument('--ktransw', type=str, dest='ktransw', metavar='PATH',
        help="Location of ktransw (default: assume it's on the Windows PATH)")
    parser.add_argument('-E', '--preprocess-only', action='store_true', dest='translate_only',
        help="Preprocess only; do not translate")
    parser.add_argument('-n', '--no-env', action='store_true', dest='no_env',
        help='Do not search the {0}, even if it is set'.format(ENV_PKG_PATH))
    parser.add_argument('-nn', '-N', '--ninja', action='store_true', dest='run_ninja',
        help='Run ninja after generating build.ninja')
    parser.add_argument('--ninja-target', action='append', default=[], dest='ninja_targets',
        metavar='TARGET', help='Ninja target to build when --ninja is used; may be repeated')
    parser.add_argument('--ninja-jobs', type=int, dest='ninja_jobs',
        metavar='N', help='Number of Ninja jobs when --ninja is used')
    parser.add_argument('-p', '--pkg-dir', action='append', type=str,
        dest='extra_paths', metavar='PATH', default=[],
        help='Additional paths to search for packages (multiple allowed). '
        'Note: this essentially extends the source space.')
    parser.add_argument('-r', '--robot-ini', type=str, dest='robot_ini',
        metavar='INI', default=ROBOT_INI_NAME,
        help="Location of {0} (default: source dir)".format(ROBOT_INI_NAME))
    parser.add_argument('--ftp', action='store_true', dest='server_ip',
        default= os.environ.get(ENV_SERVER_IP),
        help='send to ip address specified.'
        'This will override env variable, {0}.'.format(ENV_SERVER_IP))
    parser.add_argument('-s', '--buildsource', action='store_true', dest='buildsource',
        help='build source files in package.json.')
    parser.add_argument('-b', '--buildall', action='store_true', dest='buildall',
        help='build all objects source space depends on.')
    parser.add_argument('-g', '--keepgpp', action='store_true', dest='keepgpp',
        help='build all objects source space depends on.')
    parser.add_argument('-D', action='append', type=str, dest='user_macros',
        metavar='PATH', default=[], help='Define user macros from command line')
    parser.add_argument('-tp', '--compiletp', action='store_true', dest='compiletp',
        help='compile .tpp files into .tp files. If false will just interpret to .ls.')
    parser.add_argument('-t', '--include-tests', action='store_true', dest='inc_tests',
        help='include files for testing in build')
    parser.add_argument('-i', '--build-interfaces', action='store_true', dest='build_interface',
        help='build tp interfaces for karel routines specified in package.json.'
        'This is needed to use karel routines within a tp program')
    parser.add_argument('-f', '--build-forms', action='store_true', dest='build_forms',
        help='include forms for building')
    parser.add_argument('-o', '--preserve-build-paths', action='store_true',
        dest='preserve_build_paths',
        help='preserve package-relative paths in the build output directory')
    parser.add_argument('-l', '--build-tp', action='store_true', dest='build_ls',
        help='include ls files for building')
    parser.add_argument('--clean', action='store_true', dest='rossum_clean',
        help='clean all files out of build directory')
    parser.add_argument('--force', action='store_true', dest='force_clean',
        help="allow --clean outside a Rossum directory named 'build'")
    parser.add_argument('--update-manifest', type=str, dest='update_manifest_dir',
        metavar='BUILD', help=argparse.SUPPRESS)
    parser.add_argument('src_dir', type=str, nargs='?', metavar='SRC',
        help="Main directory with packages to build")
    parser.add_argument('build_dir', type=str, nargs='?', metavar='BUILD',
        help="Directory for out-of-source builds (default: 'cwd')")

    # support forward-slash arg notation for include dirs
    for i in range(1, len(sys.argv)):
        if sys.argv[i].startswith('/D'):
            sys.argv[i] = sys.argv[i].replace('/D', '-D', 1)
    if '--run-tpp' in sys.argv:
        sys.exit(run_tpp_from_argv(sys.argv[1:]))
    args = parser.parse_args()

    if args.force_clean and not args.rossum_clean:
        parser.error('--force can only be used with --clean')

    if args.update_manifest_dir:
        manifest_build_dir = os.path.abspath(args.update_manifest_dir)
        update_tp_outputs(manifest_build_dir)
        stamp_path = os.path.join(manifest_build_dir, '.manifest.stamp')
        with open(stamp_path, 'a'):
            os.utime(stamp_path, None)
        sys.exit(0)

    if args.shell:
      shell_build_dir = os.path.abspath(args.build_dir or os.getcwd())
      shell_source_dir = os.path.abspath(args.src_dir) if args.src_dir else infer_source_dir(shell_build_dir)
      return run_interactive_shell(shell_build_dir, source_dir=shell_source_dir, no_color=args.no_color, verbose=args.verbose)



    ############################################################################
    #
    # Validation
    #


    # build dir is either CWD or user specified it
    build_dir   = os.path.abspath(args.build_dir or os.getcwd())
    console = Console(no_color=args.no_color, quiet=args.quiet, verbose=args.verbose)

    #clean out files
    # (ref): https://stackoverflow.com/questions/185936/how-to-delete-the-contents-of-a-folder
    if args.rossum_clean:
      validate_clean_target(build_dir, os.getcwd(), force=args.force_clean)

      files_cleaned = 0
      dirs_cleaned = 0
      failures = []
      for filename in os.listdir(build_dir):
        file_path = os.path.join(build_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                send2trash(file_path)
                files_cleaned += 1
            elif os.path.isdir(file_path):
                send2trash(file_path)
                dirs_cleaned += 1
        except Exception as e:
            failures.append('{}: {}'.format(file_path, e))
      
      if failures:
        raise CliError(
            'Clean completed with errors',
            detail='\n'.join(failures[:20]),
            hints=['Close programs using files in the build directory, then retry.'],
        )

      console.success('Cleaned build directory: {}'.format(build_dir))
      console.table('Removed', ('Type', 'Count'), [
          ('Files', files_cleaned),
          ('Folders', dirs_cleaned),
      ])
      sys.exit(0)

    
    #source directory needs to be specified
    if not args.src_dir:
      parser.error("Source directory must be specified.")
    source_dir  = os.path.abspath(args.src_dir)
    extra_paths = [os.path.abspath(p) for p in args.extra_paths]


    # configure the logger
    log_level = logging.WARNING
    if args.verbose:
        log_level = logging.DEBUG
    if args.quiet:
        log_level = logging.ERROR

    try:
        if args.no_color or os.environ.get('NO_COLOR'):
            raise RuntimeError('plain logging requested')
        output_encoding = (getattr(sys.stderr, 'encoding', '') or getattr(sys.stdout, 'encoding', '') or '').lower()
        if 'utf' not in output_encoding:
            raise RuntimeError('non-utf console')
        from rich.logging import RichHandler
        rich_handler = RichHandler(
            show_time=False,
            show_path=False,
            markup=False,
            rich_tracebacks=True,
        )
        logging.basicConfig(
            level=log_level,
            format='%(message)s',
            handlers=[rich_handler],
        )
    except Exception:
        FMT='%(levelname)-8s | %(message)s'
        logging.basicConfig(format=FMT, level=log_level)

    global logger
    logger = logging.getLogger('rossum')
    logger.setLevel(log_level)

    logger.debug("This is rossum v{0}".format(ROSSUM_VERSION))


    # make sure that source dir exists
    if not os.path.exists(source_dir):
        logger.fatal("Directory '{0}' does not exist. Aborting".format(source_dir))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # refuse to do in-source builds
    if os.path.exists(os.path.join(build_dir, MANIFEST_NAME)):
        logger.fatal("Found a package manifest ({0}) in the build "
            "dir ({1}). Refusing to do in-source builds.".format(
                MANIFEST_NAME, build_dir))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # make sure that build dir exists
    if not os.path.exists(build_dir):
        logger.fatal("Directory '{0}' does not exist (and not creating it), "
            "aborting".format(build_dir))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    #find robot.ini file
    robot_ini_loc = find_robotini(source_dir, args)
    #parse robot.ini file into collection tuple 'robotiniInfo'
    robot_ini_info = parse_robotini(robot_ini_loc)

    # combine env files into one file if multiple are specified
    if robot_ini_info.env:
        if "," in robot_ini_info.env:
            env_file = os.path.join(build_dir, 'env.tpp')
            
            if os.path.exists(env_file):
                open(env_file, 'w').close()
                
            with open(env_file, 'w') as outfile:
                env_list = robot_ini_info.env.split(",")
                for fname in env_list:
                    with open(fname.strip()) as infile:
                        outfile.write(infile.read())
            robot_ini_info = robot_ini_info._replace(env=env_file)
            
    #add base path to fanuc search paths
    search_locs = []
        
    search_locs.append(robot_ini_info.base_path)
    search_locs.extend(FANUC_SEARCH_PATH)

    # try to find base directory for FANUC tools
    try:
        fr_base_dir = find_fr_install_dir(search_locs=FANUC_SEARCH_PATH, is64bit=args.rg64)
        logger.info("Using {} as FANUC software base directory".format(fr_base_dir))
    except Exception as e:
        # not being able to find the Fanuc base dir is a fatal error
        # without a base directory roboguide is most likely not installed
        # on the system, and ktrans, and maketp will not work without a
        # workcell emulation.
            logger.fatal("Error trying to detect FANUC base-dir: {0}".format(e))
            logger.fatal("Please make sure that roboguide, or OlpcPRO are installed.")
            logger.fatal("Cannot continue, aborting")
            sys.exit(_OS_EX_DATAERR)

    #make list of tool names
    tools = [KTRANS_BIN_NAME, KTRANSW_BIN_NAME, MAKETP_BIN_NAME, TPP_BIN_NAME, XML_BIN_NAME, KCDICT_BIN_NAME]
    # preset list of paths to search for paths
    search_locs = []
    search_locs.extend(KTRANS_SEARCH_PATH)
    # add environment path to search
    search_locs.extend([p for p in os.environ['Path'].split(os.pathsep) if len(p) > 0])
    #find build tools
    path_lst = find_tools(search_locs, tools, args)
    # if only precompiling
    if args.translate_only:
        kl_comp_ext = KL_SUFFIX
    else:
        kl_comp_ext = PCODE_SUFFIX
    # put list into dictionary for file type build rule
    tool_paths = {
        'ktrans' : {'from_suffix' : '0', 'to_suffix' : '0', 'path' : path_lst[0], 'type' : 'karel'},
        'ktransw' : {'from_suffix' : KL_SUFFIX, 'interp_suffix' : kl_comp_ext, 'comp_suffix' : kl_comp_ext, 'path' : (args.ktransw or path_lst[1]), 'type' : 'karel'},
        'yaml' : {'from_suffix' : YAML_SUFFIX, 'interp_suffix' : XML_SUFFIX,  'comp_suffix' : XML_SUFFIX, 'path' : path_lst[4], 'type' : 'data'},
        'xml' : {'from_suffix' : XML_SUFFIX, 'interp_suffix' : XML_SUFFIX,  'comp_suffix' : XML_SUFFIX, 'path' : 'C:\\Windows\\SysWOW64\\xcopy.exe', 'type' : 'data'},
        'csv' : {'from_suffix' : CSV_SUFFIX, 'interp_suffix' : CSV_SUFFIX,  'comp_suffix' : CSV_SUFFIX, 'path' : 'C:\\Windows\\SysWOW64\\xcopy.exe', 'type' : 'data'},
        'kcdict' : {'from_suffix' : DICT_SUFFIX, 'interp_suffix' : COMPRESSED_SUFFIX, 'comp_suffix' : COMPRESSED_SUFFIX, 'path' : path_lst[5], 'type' : 'forms'},
        'kcform' : {'from_suffix' : FORM_SUFFIX, 'interp_suffix' : COMPRESSED_SUFFIX, 'comp_suffix' : COMPRESSED_SUFFIX, 'path' : path_lst[5], 'type' : 'forms'}
    }
    #for tpp decide if just interpreting, or compiling to tp
    if args.compiletp:
      tool_paths['maketp'] = {'from_suffix' : TP_SUFFIX, 'interp_suffix' : TPCODE_SUFFIX, 'comp_suffix' : TPCODE_SUFFIX, 'path' : path_lst[2], 'type' : 'tp'}
      tool_paths['tpp'] = {'from_suffix' : TPP_SUFFIX, 'interp_suffix' : TPP_INTERP_SUFFIX, 'comp_suffix' : TPCODE_SUFFIX, 'path' : path_lst[3], 'compile' : path_lst[2], 'type' : 'tp'}
    else:
      tool_paths['maketp'] = {'from_suffix' : TP_SUFFIX, 'interp_suffix' : TP_SUFFIX, 'comp_suffix' : TP_SUFFIX, 'path' : 'C:\\Windows\\SysWOW64\\xcopy.exe', 'type' : 'tp'}
      tool_paths['tpp'] = {'from_suffix' : TPP_SUFFIX, 'interp_suffix' : TPP_INTERP_SUFFIX, 'comp_suffix' : TPP_INTERP_SUFFIX, 'path' : path_lst[3], 'type' : 'tp'}

    # try to find support directory for selected core software version
    logger.info("Setting default system core version to: {}".format(args.core_version))
    # see if we need to find support dir ourselves
    if not args.support_dir:
        try:
            fr_support_dir = find_ktrans_support_dir(fr_base_dir=fr_base_dir,
                version_string=args.core_version)
        except Exception as e:
            logger.fatal("Couldn't determine core software support directory, "
                "aborting".format(e))
            sys.exit(_OS_EX_DATAERR)
    # or if user provided its location
    else:
        fr_support_dir = args.support_dir
        logger.debug("User provided support dir location: {0}".format(fr_support_dir))

        # make sure it exists
        if not os.path.exists(fr_support_dir):
            logger.fatal("Specified support dir ({0}) does not exist. "
                "Aborting.".format(fr_support_dir))
            sys.exit(_OS_EX_DATAERR)

    logger.info("Karel core support dir: {}".format(fr_support_dir))


    # template and output file locations
    template_dir  = os.path.dirname(os.path.realpath(__file__))
    template_path = os.path.join(template_dir, BUILD_FILE_TEMPLATE_NAME) # for ninja file
    build_file_path = os.path.join(build_dir, BUILD_FILE_NAME)

    # check
    if not os.path.isfile(template_path):
        raise RuntimeError("Template file %s not found in template "
            "dir %s" % (template_path, template_dir))

    logger.debug("Using build file template: {0}".format(template_path))



    ############################################################################
    #
    # Package discovery
    #

    # always look in the source space and any extra paths user provided
    src_space_dirs = [source_dir]
    # and any extra paths the user provided
    src_space_dirs.extend(extra_paths)

    logger.info("Source space(s) searched for packages (in order: src, args):")
    for p in src_space_dirs:
        logger.info('  {0}'.format(p))

    # discover packages
    src_space_pkgs = find_pkgs(src_space_dirs, args)
    src_space_pkgs = remove_duplicates(src_space_pkgs)
    logger.info("Found {0} package(s) in source space(s):".format(len(src_space_pkgs)))
    for pkg in src_space_pkgs:
        logger.info("  {0} (v{1})".format(pkg.manifest.name, pkg.manifest.version))


    # discover pkgs in non-source space directories, if those have been configured
    other_pkgs = []
    if (not args.no_env) and (ENV_PKG_PATH in os.environ):
        logger.info("Other location(s) searched for packages ({}):".format(ENV_PKG_PATH))
        other_pkg_dirs = [p for p in os.environ[ENV_PKG_PATH].split(os.pathsep) if len(p) > 0]
        if logger.getEffectiveLevel() == logging.DEBUG:
          for p in other_pkg_dirs:
              logger.debug('  {0}'.format(p))

        other_pkgs.extend(find_pkgs(other_pkg_dirs, args))
        other_pkgs = remove_duplicates(other_pkgs)
        logger.info("Found {0} package(s) in other location(s):".format(len(other_pkgs)))
        if logger.getEffectiveLevel() == logging.DEBUG:
          for pkg in other_pkgs:
              logger.debug("  {0} (v{1})".format(pkg.manifest.name, pkg.manifest.version))


    # process all discovered pkgs
    all_pkgs = []
    all_pkgs.extend(src_space_pkgs)
    all_pkgs.extend(other_pkgs)
    all_pkgs = remove_duplicates(all_pkgs)

    # build out dependency trees
    # for all packages in src_space
    dependency_graph = create_dependency_graph(src_space_pkgs, all_pkgs, args)
    #log dependency trees to logger
    log_dep_tree(dependency_graph)
    #filter out additional packages that are not dependencies
    all_pkgs = filter_packages(all_pkgs, dependency_graph)

    # all discovered pkgs get used for dependency and include path resolution,
    resolve_includes(all_pkgs, args)

    #determine any user defined macros to pass to ktransw
    resolve_macros(all_pkgs, args)

    # select to just build source or all related packages
    if args.buildall:
        build_pkgs = all_pkgs
    else: 
        build_pkgs = src_space_pkgs

    #create tp-interface karel files
    if args.build_interface:
        interfaces = get_interfaces(build_pkgs)
        if interfaces:
            create_interfaces(interfaces)

    # but only the pkgs in the source space(s) get their objects build
    gen_obj_mappings(build_pkgs, tool_paths, args, dependency_graph)


    # notify user of config
    logger.info("Building {} package(s)".format(len(build_pkgs)))
    logger.info("Build configuration:")
    logger.info("  source dir: {0}".format(source_dir))
    logger.info("  build dir : {0}".format(build_dir))
    logger.info("  robot.ini : {0}".format(robot_ini_loc))
    logger.info("Writing generated rules to {0}".format(build_file_path))


    # stop if user wanted a dry-run
    if args.dry_run:
        console.success("Dry run completed. No files were written.")
        print_config_summary(console, args, source_dir, build_dir, robot_ini_loc, build_file_path, build_pkgs)
        sys.exit(0)

    ensure_output_dirs(build_pkgs, build_dir)


    ############################################################################
    #
    # Template processing
    #

    configs = {}
    #support directory
    configs['support'] = fr_support_dir
    # set core version
    configs['version'] = args.core_version
    # set ip address to upload files to
    configs['ftp'] = args.server_ip
    #tpp env file
    configs['env'] = ''

    # get info from robot.ini file
    configs['support'] = robot_ini_info.support
    # set core version
    configs['version'] = robot_ini_info.version
    # set ip address to upload files to
    configs['ftp'] = robot_ini_info.ftp
    #tpp env
    configs['env'] = robot_ini_info.env


    # populate dicts & lists needed by template
    ktrans = KtransInfo(path=tool_paths['ktrans']['path'], support=KtransSupportDirInfo(
        path=configs['support'],
        version_string=configs['version']))
    ktransw = KtransWInfo(path=tool_paths['ktransw']['path'])
    bs_info = RossumSpaceInfo(path=build_dir)
    sp_infos = [RossumSpaceInfo(path=p) for p in src_space_dirs]
    robini_info = KtransRobotIniInfo(path=robot_ini_loc, ftp=configs['ftp'], env=configs['env'])
    make_tpp_env_file = [p.manifest.tpp_compile_env for p in src_space_pkgs]
    if len(make_tpp_env_file) > 0:
      make_tpp_env_file = make_tpp_env_file[0]
    else:
      make_tpp_env_file = None

    ws = RossumWorkspace(build=bs_info, sources=sp_infos,
        robot_ini=robini_info, pkgs=build_pkgs)


    #if --keepgpp is set insert flag into ktrans call in
    # build.ninja.em so that temp builds in %TEMP% are kept
    keep_buildd = ''
    if args.keepgpp:
        keep_buildd = '-k'

    #if --preprocess-only run through GPP and copy resulting
    #file into build folder.
    copy_karel = ''
    if args.translate_only:
        copy_karel = '-E'

    #store globals in container to be passed by empy
    globls = {
        'ws'             : ws,
        'ktrans'         : ktrans,
        'ktransw'        : ktransw,
        'rossum_version' : ROSSUM_VERSION,
        'tstamp'         : datetime.datetime.now().isoformat(),
        'tools'          : tool_paths,
        'keepgpp'        : keep_buildd,
        'preprocess_karel' : copy_karel,
        'compiletp'      : args.compiletp,
        'hastpp'         : args.hastpp,
        'makeenv'        : make_tpp_env_file,
        'rossum_script'  : os.path.join(template_dir, os.path.basename(__file__)),
        'rossum_cmd'     : os.path.join(template_dir, 'rossum.cmd'),
        'ninja_build_outputs' : ninja_build_outputs,
        'ninja_main_output'   : ninja_main_output,
        'ninja_all_outputs'   : ninja_all_outputs,
        'ninja_description'   : ninja_description,
    }
    # write out ninja template
    ninja_fl = open(build_file_path, 'w')
    ninja_interp = em.Interpreter(
            output=ninja_fl, globals=dict(globls),
            options={em.RAW_OPT : True, em.BUFFERED_OPT : True})
    # load and process the template
    logger.debug("Processing template")
    ninja_interp.file(open(template_path))
    # shutdown empy interpreters
    logger.debug("Shutting down empy")
    ninja_interp.shutdown()

    # write build files in manifest
    man_list = manifest_objects(ws.pkgs)
    write_manifest(FILE_MANIFEST, man_list, robini_info.ftp)

    # done
    print_config_summary(console, args, source_dir, build_dir, robot_ini_loc, build_file_path, build_pkgs)
    if args.run_ninja:
        return run_ninja_build(
            console,
            build_dir,
            targets=args.ninja_targets,
            jobs=args.ninja_jobs,
        )
    console.success("Configuration complete. Next: run ninja in the build directory.")





def run_modern_command(argv):
    import argparse

    command = argv[0]
    if command == 'doctor':
        parser = argparse.ArgumentParser(prog='rossum doctor', description='Check Rossum, FANUC tools, robot.ini, and package paths.')
        parser.add_argument('src_dir', nargs='?', default=os.getcwd(), metavar='SRC')
        parser.add_argument('--build-dir', default=os.getcwd(), metavar='PATH')
        parser.add_argument('-r', '--robot-ini', default=ROBOT_INI_NAME, metavar='INI')
        parser.add_argument('--no-color', action='store_true')
        parser.add_argument('-v', '--verbose', action='store_true')
        args = parser.parse_args(argv[1:])
        return rossum_doctor(args)

    if command == 'timings':
        parser = argparse.ArgumentParser(prog='rossum timings', description='Summarize Ninja timing information from .ninja_log.')
        parser.add_argument('build_dir', nargs='?', default=os.getcwd(), metavar='BUILD')
        parser.add_argument('--top', type=int, default=12, metavar='N')
        parser.add_argument('--no-color', action='store_true')
        args = parser.parse_args(argv[1:])
        return rossum_timings(args)

    if command == 'manifest':
        if len(argv) < 2 or argv[1] != 'check':
            raise CliError(
                "Unknown manifest command",
                detail="Expected: rossum manifest check [BUILD]",
                hints=["Run rossum manifest check from a build directory."],
            )
        parser = argparse.ArgumentParser(prog='rossum manifest check', description='Validate .man_log against the build directory.')
        parser.add_argument('build_dir', nargs='?', default=os.getcwd(), metavar='BUILD')
        parser.add_argument('--no-color', action='store_true')
        args = parser.parse_args(argv[2:])
        return rossum_manifest_check(args)

    if command == 'build':
        parser = argparse.ArgumentParser(prog='rossum build', description='Run Ninja with clearer Rossum failure reporting.')
        parser.add_argument('build_dir', nargs='?', default=os.getcwd(), metavar='BUILD')
        parser.add_argument('targets', nargs='*', metavar='TARGET')
        parser.add_argument('-j', '--jobs', type=int, metavar='N')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--no-color', action='store_true')
        parser.add_argument('-v', '--verbose', action='store_true')
        args = parser.parse_args(argv[1:])
        return rossum_build(args)

    raise CliError("Unknown Rossum command", detail=command)


def rossum_doctor(args):
    console = Console(no_color=args.no_color, verbose=args.verbose)
    install_tracebacks(show_locals=args.verbose)
    src_dir = os.path.abspath(args.src_dir)
    build_dir = os.path.abspath(args.build_dir)
    rows = []

    def add(name, ok, detail, warn=False):
        if ok:
            status = 'OK'
        elif warn:
            status = 'WARN'
        else:
            status = 'FAIL'
        rows.append((name, status, detail))

    add('Python', True, sys.version.split()[0])
    add('Ninja', bool(shutil.which('ninja')), shutil.which('ninja') or 'not found on PATH')
    add('ROSSUM_PKG_PATH', ENV_PKG_PATH in os.environ, os.environ.get(ENV_PKG_PATH, 'not set'), warn=True)

    robot_ini = args.robot_ini
    if not os.path.isabs(robot_ini):
        cwd_robot = os.path.abspath(robot_ini)
        src_robot = os.path.join(src_dir, robot_ini)
        robot_ini = cwd_robot if os.path.exists(cwd_robot) else src_robot
    add('robot.ini', os.path.exists(robot_ini), robot_ini)

    if os.path.exists(robot_ini):
        config = configparser.ConfigParser()
        config.read(robot_ini)
        has_section = config.has_section('WinOLPC_Util')
        add('robot.ini section', has_section, 'WinOLPC_Util')
        if has_section:
            for key in ('Robot', 'Path', 'Support'):
                value = config['WinOLPC_Util'].get(key, '')
                add('robot.ini {}'.format(key), bool(value) and os.path.exists(value), value or 'missing', warn=(key == 'Robot'))
            ftp = config['WinOLPC_Util'].get('Ftp', os.environ.get(ENV_SERVER_IP, ''))
            add('Robot IP', bool(ftp), ftp or 'missing')

    search_locs = []
    search_locs.extend(KTRANS_SEARCH_PATH)
    search_locs.extend([p for p in os.environ.get('Path', '').split(os.pathsep) if p])
    for tool in (KTRANS_BIN_NAME, MAKETP_BIN_NAME, TPP_BIN_NAME, KTRANSW_BIN_NAME, XML_BIN_NAME, KCDICT_BIN_NAME):
        found = first_existing_tool(tool, search_locs)
        add(tool, bool(found), found or 'not found')

    add('Build directory', os.path.isdir(build_dir), build_dir)
    add('build.ninja', os.path.exists(os.path.join(build_dir, BUILD_FILE_NAME)), os.path.join(build_dir, BUILD_FILE_NAME), warn=True)
    add('.man_log', os.path.exists(os.path.join(build_dir, FILE_MANIFEST)), os.path.join(build_dir, FILE_MANIFEST), warn=True)

    console.table('Rossum doctor', ('Check', 'Status', 'Detail'), rows)
    failed = [row for row in rows if row[1] == 'FAIL']
    if failed:
        console.warning('{} check(s) failed.'.format(len(failed)))
        return 1
    console.success('All checks passed.')
    return 0


def first_existing_tool(tool, search_locs):
    for search_loc in search_locs:
        path = os.path.join(search_loc, tool)
        if os.path.exists(path):
            return path
    return shutil.which(tool)


def rossum_timings(args):
    console = Console(no_color=args.no_color)
    ninja_log = os.path.join(os.path.abspath(args.build_dir), '.ninja_log')
    if not os.path.exists(ninja_log):
        fail_missing_file(ninja_log, 'Ninja log')

    rows = []
    with open(ninja_log, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.rstrip().split('\t')
            if len(parts) < 4:
                continue
            try:
                start = int(parts[0])
                end = int(parts[1])
            except ValueError:
                continue
            rows.append((end - start, start, end, parts[3]))

    if not rows:
        raise CliError('No timing entries found', detail=ninja_log)

    wall = max(row[2] for row in rows) - min(row[1] for row in rows)
    total = sum(row[0] for row in rows)
    summary = [
        ('Edges', len(rows)),
        ('Wall time', '{} ms'.format(wall)),
        ('Total tool time', '{} ms'.format(total)),
        ('Parallel factor', '{:.2f}x'.format(total / wall) if wall else 'n/a'),
    ]
    console.table('Ninja timing summary', ('Metric', 'Value'), summary)
    top = sorted(rows, reverse=True)[:args.top]
    console.table('Slowest build edges', ('Duration', 'Output'), [
        ('{} ms'.format(duration), os.path.basename(output)) for duration, _, _, output in top
    ])
    return 0


def rossum_manifest_check(args):
    console = Console(no_color=args.no_color)
    build_dir = os.path.abspath(args.build_dir)
    manifest_path = os.path.join(build_dir, FILE_MANIFEST)
    if not os.path.exists(manifest_path):
        fail_missing_file(manifest_path, 'Manifest')

    with open(manifest_path, 'r', encoding='utf-8', errors='replace') as handle:
        manifest = yaml.safe_load(handle) or {}
    if not isinstance(manifest, dict):
        raise CliError('Manifest format is invalid', detail=manifest_path)

    rows = []
    missing = []
    for section, entries in manifest.items():
        if section == 'ip':
            continue
        if not isinstance(entries, dict):
            rows.append((section, 'FAIL', 'section is not a mapping'))
            continue
        section_missing = 0
        total = 0
        for parent, children in entries.items():
            total += 1
            if not os.path.exists(os.path.join(build_dir, parent)):
                missing.append('{}: {}'.format(section, parent))
                section_missing += 1
            for child in children or []:
                total += 1
                if not os.path.exists(os.path.join(build_dir, child)):
                    missing.append('{} child: {}'.format(section, child))
                    section_missing += 1
        rows.append((section, 'OK' if section_missing == 0 else 'FAIL', '{} file(s), {} missing'.format(total, section_missing)))

    console.table('Manifest check', ('Section', 'Status', 'Detail'), rows)
    if missing:
        console.panel('Missing files', '\n'.join(missing[:40]), style='red')
        return 1
    console.success('Manifest matches files in build directory.')
    return 0


def rossum_build(args):
    console = Console(no_color=args.no_color, verbose=args.verbose)
    build_dir = os.path.abspath(args.build_dir)
    build_file = os.path.join(build_dir, BUILD_FILE_NAME)
    if not os.path.exists(build_file):
        fail_missing_file(build_file, 'Ninja build file')

    if args.dry_run:
        command = ['ninja']
        if args.jobs:
            command.extend(['-j', str(args.jobs)])
        command.extend(args.targets)
        console.info('Would run in {}: {}'.format(build_dir, ' '.join(command)))
        return 0

    return run_ninja_build(console, build_dir, targets=args.targets, jobs=args.jobs)


def run_ninja_build(console, build_dir, targets=None, jobs=None):
    command = ['ninja']
    if jobs:
        command.extend(['-j', str(jobs)])
    command.extend(targets or [])

    console.info('Running {}'.format(' '.join(command)))
    result = run_command_live(command, cwd=build_dir, console=console, label='Building with Ninja')
    log_dir = os.path.join(build_dir, '.rossum')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_path = os.path.join(log_dir, 'ninja-last.log')
    write_text(log_path, result.output)

    if result.returncode != 0:
        detail = summarize_ninja_failure(result.output)
        raise CliError(
            'Ninja build failed',
            detail='Return code: {}\nLog: {}\n\n{}'.format(result.returncode, log_path, detail),
            hints=[
                'Open the log only if the summary above is not enough.',
                'Fix the source file shown in the summary, then run rossum -nn again.',
            ],
        )

    if result.output.strip():
        console.panel('Ninja output', result.output[-4000:], style='cyan')
    console.success('Ninja build completed. Log: {}'.format(log_path))
    return 0


def summarize_ninja_failure(output, source_hint=None):
    lines = output.splitlines()
    tpplus_summary = summarize_tpplus_failure(lines, source_hint=source_hint)
    if tpplus_summary:
        return tpplus_summary
    karel_summary = summarize_karel_failure(lines)
    if karel_summary:
        return karel_summary

    interesting = []
    capture = False
    for line in lines:
        if line.startswith('FAILED:') or 'FAILED:' in line:
            capture = True
        if capture:
            interesting.append(line)
        if capture and len(interesting) >= 20:
            break
    return '\n'.join(interesting) if interesting else output[-4000:]


def summarize_karel_failure(lines):
    source = None
    line_no = None
    code_line = None
    code_column_start = 0
    pointer_line = None
    error_text = None
    raw_compiler_line = None

    for index, raw_line in enumerate(lines):
        line = clean_report_line(raw_line)
        match = re.search(r'([A-Za-z]:.+?\.kl)\(([0-9]+)\)', line, re.IGNORECASE)
        if not match:
            continue

        source = match.group(1)
        line_no = int(match.group(2))
        for follow in lines[index + 1:index + 12]:
            clean = clean_report_line(follow)
            code_match = re.match(r'^\s*[0-9]+\s+(.+)$', clean)
            if code_match and code_line is None:
                code_line = code_match.group(1).rstrip()
                code_column_start = code_match.start(1)
                continue
            caret_match = re.search(r'\^\s*ERROR(?:\s*(.*))?$', clean, re.IGNORECASE)
            if caret_match:
                pointer_line = karel_pointer_line(clean, code_column_start)
                error_text = (caret_match.group(1) or '').strip()
                raw_compiler_line = clean.strip()
                break
        break

    if not source or not line_no:
        return None

    symbol = likely_karel_symbol(code_line)
    rows = ['[bold red]KAREL compiler error[/bold red]']
    rows.append('[cyan]Source:[/cyan] {}'.format(display_path(source)))
    rows.append('[cyan]Line:[/cyan] {}'.format(line_no))
    if symbol:
        rows.append('[cyan]Near:[/cyan] {}'.format(symbol))
    if error_text:
        rows.append('[cyan]Message:[/cyan] {}'.format(error_text))
    else:
        rows.append('[cyan]Message:[/cyan] ktrans reported an error at this location.')
    if code_line:
        rows.append('')
        rows.append('[cyan]Exact location:[/cyan]')
        rows.append('{:>5}: {}'.format(line_no, code_line))
        if pointer_line:
            rows.append('       {}'.format(pointer_line))
    source_detail = karel_source_context(source, line_no, code_line=code_line)
    if source_detail:
        rows.append('')
        rows.append(source_detail)
    rows.append('')
    rows.append('[yellow]Hint:[/yellow] {}'.format(karel_original_hint(raw_compiler_line, error_text)))
    return '\n'.join(rows)


def karel_pointer_line(caret_line, code_match_start=None):
    caret_index = caret_line.find('^')
    if caret_index < 0:
        return None
    base = code_match_start or 0
    return '{}^ ERROR'.format(' ' * max(0, caret_index - base))


def karel_source_context(source_path, line_no, radius=3, code_line=None):
    if not source_path or not os.path.exists(source_path):
        return None
    try:
        with open(source_path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
    except OSError:
        return None
    if line_no < 1 or line_no > len(lines):
        matches = find_matching_source_lines(lines, code_line)
        out = ['[cyan]Source context:[/cyan]']
        out.append('  Compiler reported line {}, but the current source has {} line(s).'.format(line_no, len(lines)))
        if matches:
            out.append('  Matching statement found at source line(s): {}'.format(', '.join(str(item) for item in matches[:8])))
            if len(matches) == 1:
                out.append('')
                out.append(karel_context_at_line(lines, matches[0], radius))
            else:
                out.append('  Multiple matches exist; use the compiler line and matching statement to choose the right one.')
        else:
            out.append('  No exact matching statement was found. The error may be from a generated/preprocessed KAREL file.')
        return '\n'.join(out)

    return '[cyan]Source context:[/cyan]\n' + karel_context_at_line(lines, line_no, radius)


def karel_context_at_line(lines, line_no, radius=3):
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    out = []
    routine = nearest_karel_routine(lines, line_no)
    if routine:
        out.append('  Routine: {}'.format(routine))
    for idx in range(start, end + 1):
        marker = '>' if idx == line_no else ' '
        out.append('{} {:4d}: {}'.format(marker, idx, lines[idx - 1].rstrip()))
    return '\n'.join(out)


def find_matching_source_lines(lines, code_line):
    if not code_line:
        return []
    target = normalize_karel_statement(code_line)
    matches = []
    for idx, line in enumerate(lines, start=1):
        if normalize_karel_statement(line) == target:
            matches.append(idx)
    return matches


def normalize_karel_statement(line):
    return re.sub(r'\s+', ' ', str(line).strip()).lower()


def nearest_karel_routine(lines, line_no):
    for idx in range(min(line_no, len(lines)), 0, -1):
        match = re.match(r'\s*ROUTINE\s+([A-Za-z_][A-Za-z0-9_]*)', lines[idx - 1], re.IGNORECASE)
        if match:
            return match.group(1)
    return None


KAREL_KEYWORDS = {
    'abort', 'and', 'array', 'begin', 'boolean', 'by', 'case', 'const',
    'continue', 'do', 'else', 'endif', 'endfor', 'endroutine', 'endselect',
    'endwhile', 'false', 'for', 'from', 'if', 'in', 'integer', 'not',
    'of', 'or', 'program', 'real', 'return', 'routine', 'select', 'string',
    'then', 'to', 'true', 'type', 'until', 'var', 'while', 'xor',
}


def likely_karel_symbol(code_line):
    if not code_line:
        return None
    identifiers = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', code_line)
    identifiers = [item for item in identifiers if item.lower() not in KAREL_KEYWORDS]
    if not identifiers:
        return None
    if '=' in code_line:
        rhs = code_line.split('=', 1)[1]
        rhs_identifiers = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', rhs)
        rhs_identifiers = [item for item in rhs_identifiers if item.lower() not in KAREL_KEYWORDS]
        if rhs_identifiers:
            return rhs_identifiers[0]
    return identifiers[-1]


def karel_original_hint(raw_compiler_line=None, error_text=None):
    if error_text:
        return 'ktrans reported: {}'.format(error_text)
    if raw_compiler_line:
        return 'ktrans reported: `{}`. No more specific compiler message was provided.'.format(raw_compiler_line)
    return 'ktrans did not provide a more specific compiler message. Use the exact location and source context above.'


def summarize_tpplus_failure(lines, source_hint=None):
    parse_line = None
    runtime_line = None
    runtime_message = None
    source = source_hint
    context = []

    source_pattern = re.compile(r'([A-Za-z]:[^\s"]+?\.tpp)|"([^"]+?\.tpp)"')
    for raw_line in lines:
        line = clean_report_line(raw_line)
        if source is None:
            if line.lower().startswith('source:'):
                source_value = line.split(':', 1)[1].strip()
                if source_value:
                    source = source_value
            match = source_pattern.search(line)
            if match:
                source = match.group(1) or match.group(2)
        if 'TPPlus::Parser::ParseError' in line or 'Parse error on line' in line:
            parse_line = line.strip()
            if parse_line.startswith('Message: '):
                parse_line = parse_line[len('Message: '):]
        runtime_match = re.search(r'Runtime error on line\s+([0-9]+)|^Line:\s*([0-9]+)', line)
        if runtime_match and runtime_line is None:
            runtime_line = int(runtime_match.group(1) or runtime_match.group(2))
        message_match = re.search(r'Variable\s+\(([^)]+)\)\s+not defined', line)
        if message_match and runtime_message is None:
            runtime_message = 'Variable "{}" is not defined'.format(message_match.group(1))
        message_match = re.search(r'^Message:\s*(.+)$', line)
        if message_match and runtime_message is None and 'Variable ' in message_match.group(1):
            runtime_message = message_match.group(1).strip()
        if line.startswith('==:') or line.startswith('=>:'):
            if line not in context:
                context.append(line)

    if not parse_line:
        if runtime_line or runtime_message:
            return summarize_tpplus_runtime_failure(source, runtime_line, runtime_message)
        return None

    location = ''
    match = re.search(r'Parse error on line\s+([0-9]+)\s+column\s+([0-9]+)', parse_line)
    if match:
        location = 'line {}, column {}'.format(match.group(1), match.group(2))

    rows = ['[bold red]TP+ parser error[/bold red]']
    if source:
        rows.append('[cyan]Source:[/cyan] {}'.format(display_path(source)))
    if location:
        rows.append('[cyan]Location:[/cyan] {}'.format(location))
    rows.append('[cyan]Message:[/cyan] {}'.format(parse_line))
    if source and match:
        source_detail = source_error_context(source, int(match.group(1)))
        if source_detail:
            rows.append('')
            rows.append(source_detail)
    if context:
        rows.append('')
        rows.append('Parser context:')
        rows.extend(context[-6:])
    rows.append('')
    rows.append('[yellow]Fix:[/yellow] check for a missing end, incomplete block, or unfinished statement near the reported TP+ line.')
    return '\n'.join(rows)


def clean_report_line(line):
    line = str(line).rstrip()
    stripped = line.strip()
    if stripped.startswith('|') and stripped.endswith('|'):
        return stripped[1:-1].strip()
    if stripped.startswith('│') and stripped.endswith('│'):
        return stripped[1:-1].strip()
    border_chars = ('|', '│', 'â', '”', '“', '‚', '„', 'ā')
    while stripped and stripped[0] in border_chars:
        stripped = stripped[1:]
    if stripped.startswith(' '):
        stripped = stripped[1:]
    while stripped and stripped[-1] in border_chars:
        stripped = stripped[:-1]
    if stripped.endswith(' '):
        stripped = stripped[:-1]
    return stripped


def summarize_tpplus_runtime_failure(source, line_no=None, message=None):
    rows = ['[bold red]TP+ runtime error[/bold red]']
    if source:
        rows.append('[cyan]Source:[/cyan] {}'.format(display_path(source)))
    if line_no:
        rows.append('[cyan]Line:[/cyan] {}'.format(line_no))
    if message:
        rows.append('[cyan]Message:[/cyan] {}'.format(message))
    rows.append('')
    if source and line_no:
        source_detail = source_error_context(source, int(line_no), radius=3, include_block_hint=False)
        if source_detail:
            rows.append(source_detail)
            rows.append('')
    rows.append('[yellow]Fix:[/yellow] correct the value/name used at the reported source line, then rebuild.')
    return '\n'.join(rows)


def source_error_context(source_path, line_no, radius=5, include_block_hint=True):
    if not os.path.exists(source_path):
        return None

    try:
        with open(source_path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
    except OSError:
        return None

    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    out = ['[cyan]Source context:[/cyan]']
    for idx in range(start, end + 1):
        marker = '>' if idx == line_no else ' '
        prefix = '[line]>{:4d}:[/line]'.format(idx) if idx == line_no else ' {:4d}:'.format(idx)
        out.append('{} {}'.format(prefix, lines[idx - 1].rstrip()))

    block_hint = analyze_tpp_blocks(lines, line_no) if include_block_hint else None
    if block_hint:
        out.append('')
        out.append(block_hint)
    return '\n'.join(out)


def display_path(path):
    if not path:
        return path
    try:
        rel = os.path.relpath(os.path.abspath(path), os.getcwd())
        if len(rel) < len(path) and not rel.startswith('..\\..'):
            return rel
    except ValueError:
        pass
    return os.path.basename(path) if len(path) > 90 else path


def analyze_tpp_blocks(lines, line_no):
    openers = ('if', 'for', 'while', 'select', 'case', 'def', 'namespace')
    stack = []

    for idx, raw_line in enumerate(lines[:line_no], start=1):
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith('--'):
            continue
        line = line.split('#', 1)[0].strip()

        first = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\b', line)
        if not first:
            continue
        keyword = first.group(1).lower()

        if keyword in openers:
            stack.append((keyword, idx, raw_line.rstrip()))
        elif keyword == 'end':
            if stack:
                stack.pop()
        elif keyword == 'else':
            if not stack or stack[-1][0] != 'if':
                return 'Block hint: line {} has else without a visible matching if.'.format(idx)

    if stack:
        keyword, idx, text = stack[-1]
        return 'Block hint: possible missing end for {} opened at line {}:\n  {}'.format(keyword, idx, text)
    return 'Block hint: no obvious unmatched if/def/namespace before the parser line. Check the last statement before this location.'


def run_tpp_from_argv(argv):
    import argparse

    parser = argparse.ArgumentParser(prog='rossum --run-tpp', add_help=False)
    parser.add_argument('--run-tpp', action='store_true')
    parser.add_argument('--tpp-tool')
    parser.add_argument('--tpp-source')
    parser.add_argument('--tpp-output')
    parser.add_argument('--tpp-env')
    parser.add_argument('--tpp-makeenv')
    parser.add_argument('--tpp-keepgpp', action='store_true')
    parser.add_argument('--tpp-rsp')

    pre_args, _ = parser.parse_known_args(argv)
    rsp_args = []
    if pre_args.tpp_rsp:
        rsp_args = read_tpp_response_args(pre_args.tpp_rsp)
    args, extra = parser.parse_known_args(argv + rsp_args)

    if extra and extra[0] == '--':
        extra = extra[1:]

    missing = [name for name, value in (
        ('--tpp-tool', args.tpp_tool),
        ('--tpp-source', args.tpp_source),
        ('--tpp-output', args.tpp_output),
    ) if not value]
    if missing:
        print_error_panel('TP+ failed', '\n'.join([
            'TP+ wrapper configuration is incomplete',
            '',
            'Missing: {}'.format(', '.join(missing)),
            '',
            'Fix: rerun rossum to regenerate build.ninja.',
        ]))
        return 1

    if args.tpp_env and not os.path.exists(args.tpp_env):
        print_error_panel('TP+ failed', '\n'.join([
            'TP+ environment file not found',
            '',
            'Env: {}'.format(args.tpp_env),
            'Source: {}'.format(args.tpp_source),
            '',
            'Fix: check robot.ini Env= and rerun rossum to regenerate build.ninja.',
        ]))
        return 1

    command = [
        args.tpp_tool,
        args.tpp_source,
        '-o',
        args.tpp_output,
    ]
    if args.tpp_env:
        command.extend(['-e', args.tpp_env])
    if args.tpp_makeenv:
        command.extend(['-k', args.tpp_makeenv])
    if args.tpp_keepgpp:
        command.append('-p')
    command.extend(extra)

    result = run_command(command)
    output_has_error = tpp_output_has_error(result.output)
    if result.returncode == 0 and not output_has_error:
        if result.output.strip():
            print(result.output)
        return 0

    summary = summarize_ninja_failure(result.output, source_hint=args.tpp_source)
    print_error_panel('TP+ failed', summary)
    return result.returncode or 1


def read_tpp_response_args(path):
    if not path:
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            content = handle.read()
    except OSError as exc:
        print_error_panel('TP+ failed', '\n'.join([
            'TP+ response file not found',
            '',
            'File: {}'.format(display_path(path)),
            'Error: {}'.format(exc),
        ]))
        sys.exit(1)

    try:
        return shlex.split(content, posix=True)
    except ValueError as exc:
        print_error_panel('TP+ failed', '\n'.join([
            'TP+ response file is invalid',
            '',
            'File: {}'.format(display_path(path)),
            'Error: {}'.format(exc),
        ]))
        sys.exit(1)


def tpp_output_has_error(output):
    lowered = (output or '').lower()
    return any(token in lowered for token in (
        'does not exist',
        'parse error',
        'tpplus::parser::parseerror',
        'runtime error',
        'no such file',
        'error:',
    ))


def print_config_summary(console, args, source_dir, build_dir, robot_ini_loc, build_file_path, build_pkgs):
    outputs = 0
    sections = collections.defaultdict(int)
    for pkg in build_pkgs:
        for obj in pkg.objects:
            count = len(as_list(obj[1]))
            outputs += count
            sections[obj[3]] += count

    requested = []
    if args.buildsource:
        requested.append('source')
    if args.build_ls:
        requested.append('tp')
    if args.inc_tests:
        requested.append('tests')
    if args.build_forms:
        requested.append('forms')
    if args.build_interface:
        requested.append('interfaces')
    if args.compiletp:
        requested.append('compile-tp')
    if args.preserve_build_paths:
        requested.append('preserve-paths')

    rows = [
        ('Source', source_dir),
        ('Build', build_dir),
        ('Packages', str(len(build_pkgs))),
        ('Outputs', str(outputs)),
        ('Mode', ', '.join(requested) if requested else 'configure only'),
        ('Robot ini', robot_ini_loc),
        ('Build file', build_file_path),
        ('Manifest', os.path.join(build_dir, FILE_MANIFEST)),
    ]

    if sections:
        rows.append(('Sections', ', '.join(['{}={}'.format(k, v) for k, v in sorted(sections.items())])))

    console.table('Rossum configuration', ('Item', 'Value'), rows)


def is_rossum_build_dir(path):
    return os.path.isfile(os.path.join(os.path.abspath(path), BUILD_FILE_NAME))


def validate_clean_target(build_dir, current_dir, force=False):
    build_dir = os.path.realpath(os.path.abspath(build_dir))
    current_dir = os.path.realpath(os.path.abspath(current_dir))

    if not os.path.isdir(build_dir):
        raise CliError(
            'Refusing to clean this directory',
            detail='The clean target does not exist or is not a directory:\n  {}'.format(build_dir),
        )

    if force:
        return build_dir

    if os.path.normcase(current_dir) != os.path.normcase(build_dir):
        raise CliError(
            'Refusing to clean from outside the build directory',
            detail='Current directory:\n  {}\nClean target:\n  {}'.format(current_dir, build_dir),
            hints=[
                'Change to the build directory and run rossum --clean.',
                'Use rossum --clean --force only when you have verified the clean target.',
            ],
        )

    if os.path.basename(os.path.normpath(build_dir)).lower() != 'build':
        raise CliError(
            "Refusing to clean a directory not named 'build'",
            detail='Current directory:\n  {}'.format(build_dir),
            hints=[
                "Change to the project's build directory and run rossum --clean.",
                'Use rossum --clean --force only when you have verified the current directory.',
            ],
        )

    if not is_rossum_build_dir(build_dir):
        raise CliError(
            'Refusing to clean this directory',
            detail='No {} was found in:\n  {}'.format(BUILD_FILE_NAME, build_dir),
            hints=[
                'Run rossum --clean from a Rossum build directory.',
                'Use rossum --clean --force only when you have verified the current directory.',
            ],
        )

    return build_dir


def infer_source_dir(build_dir):
    build_dir = os.path.abspath(build_dir)
    parent = os.path.abspath(os.path.join(build_dir, os.pardir))
    if os.path.exists(os.path.join(parent, ROBOT_INI_NAME)) or os.path.exists(os.path.join(parent, 'package.json')):
        return parent

    build_file = os.path.join(build_dir, BUILD_FILE_NAME)
    if os.path.exists(build_file):
        try:
            with open(build_file, 'r', encoding='utf-8', errors='replace') as handle:
                for line in handle:
                    match = re.match(r'^[A-Za-z0-9_.-]+_dir\s*=\s*(.+)$', line.strip())
                    if match:
                        candidate = os.path.abspath(match.group(1).strip())
                        if os.path.exists(candidate):
                            return candidate
        except OSError:
            pass
    return parent


def run_interactive_shell(build_dir, source_dir=None, no_color=False, verbose=False):
    console = Console(no_color=no_color, verbose=verbose)
    build_dir = os.path.abspath(build_dir)
    source_dir = os.path.abspath(source_dir or infer_source_dir(build_dir))
    state = {
        'build_dir': build_dir,
        'source_dir': source_dir,
        'last_error': '',
        'last_result': 'Ready',
    }

    print_shell_intro(console, state)
    shell_status(console, state)
    console.print('')
    console.print('[dim]Type /help for commands. Type /exit to close Rossum.[/dim]')

    while True:
        try:
            if console.rich:
                raw = console.rich.input('\n[bold cyan]rossum[/bold cyan] [dim]>[/dim] ')
            else:
                raw = input('\nrossum> ')
        except EOFError:
            console.print('')
            break
        except KeyboardInterrupt:
            console.print('')
            console.warning('Use /exit to close Rossum.')
            continue

        raw = raw.strip()
        if not raw:
            continue
        if not raw.startswith('/'):
            console.warning('Commands start with /. Try /help.')
            continue

        try:
            should_exit = handle_shell_command(console, state, raw)
            if should_exit:
                break
        except CliError as exc:
            console.print_error(exc)
            state['last_error'] = exc.title
            state['last_result'] = 'Failed'
        except Exception as exc:
            if os.environ.get('ROSSUM_DEBUG'):
                raise
            console.print_error(CliError(
                'Interactive command failed',
                detail=str(exc),
                hints=['Run the command again with ROSSUM_DEBUG=1 for a full traceback.'],
            ))
            state['last_error'] = str(exc)
            state['last_result'] = 'Failed'

    console.success('Rossum closed.')
    return 0


def print_shell_intro(console, state):
    body = '\n'.join([
        '[bold cyan]ROSSUM[/bold cyan] [dim]v{}[/dim]'.format(ROSSUM_VERSION),
        '[dim]Interactive robot build console[/dim]',
    ])
    console.panel('Welcome', body, style='cyan')


def handle_shell_command(console, state, raw):
    try:
        parts = shlex.split(raw[1:])
    except ValueError as exc:
        raise CliError('Command syntax is invalid', detail=str(exc), hints=['Check quotes and try again.'])
    if not parts:
        return False

    command = parts[0].lower()
    args = parts[1:]

    if command in ('exit', 'quit', 'q'):
        return True
    if command == 'help':
        shell_help(console)
    elif command == 'status':
        shell_status(console, state)
    elif command == 'config':
        shell_config(console, state, args)
    elif command == 'build':
        shell_build(console, state, args)
    elif command == 'send':
        shell_send(console, state, args)
    elif command == 'test':
        shell_test(console, state, args)
    elif command == 'clean':
        shell_clean(console, state)
    elif command == 'check':
        shell_check(console, state, args)
    elif command == 'log':
        shell_log(console, state, args)
    else:
        raise CliError('Unknown command', detail='/{0}'.format(command), hints=['Run /help to see available commands.'])
    return False


def shell_help(console):
    rows = [
        ('/status', 'Show source, build, robot, mode, and last result'),
        ('/config [tp|tests|source|all]', 'Generate build.ninja'),
        ('/build [tp|tests|source|all]', 'Run Ninja, optionally configuring first'),
        ('/send [--dry|--only tp|--skip data]', 'Send files to robot using kpush'),
        ('/test [--list|program]', 'Run KUnit tests'),
        ('/clean', 'Clean the build directory after confirmation'),
        ('/check [tools|manifest|robot]', 'Run diagnostics'),
        ('/log [build|send|test]', 'Show recent logs'),
        ('/exit', 'Close Rossum'),
    ]
    console.table('Rossum commands', ('Command', 'Action'), rows)


def shell_status(console, state):
    build_dir = state['build_dir']
    source_dir = state['source_dir']
    manifest = read_manifest_if_present(build_dir)
    mode = detect_shell_mode(manifest)
    robot_ip = manifest.get('ip', 'not set') if isinstance(manifest, dict) else 'not set'
    rows = [
        ('Source', source_dir),
        ('Build', build_dir),
        ('Build file', 'yes' if os.path.exists(os.path.join(build_dir, BUILD_FILE_NAME)) else 'missing'),
        ('Manifest', 'yes' if os.path.exists(os.path.join(build_dir, FILE_MANIFEST)) else 'missing'),
        ('Mode', mode),
        ('Robot', robot_ip or 'not set'),
        ('Last result', state.get('last_result', 'Ready')),
    ]
    if state.get('last_error'):
        rows.append(('Last error', state['last_error']))
    console.table('Rossum status', ('Item', 'Value'), rows)


def shell_config(console, state, args):
    mode = args[0].lower() if args else detect_shell_mode(read_manifest_if_present(state['build_dir']))
    if mode == 'unknown':
        mode = 'tp'
    command = rossum_config_command(state, mode)
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Configuring {}'.format(mode))


def shell_build(console, state, args):
    if args:
        shell_config(console, state, args[:1])
    command = ['ninja']
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Building with Ninja')


def shell_send(console, state, args):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kpush.py')
    mapped = map_shell_flags(args)
    command = [sys.executable, script, '--build-dir', state['build_dir']]
    command.extend(mapped)
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Sending programs to robot')


def shell_test(console, state, args):
    if '--list' in args:
        tests = shell_test_programs(state['build_dir'])
        if not tests:
            console.warning('No KUnit test programs found in .man_log.')
            return
        console.table('KUnit tests', ('Program',), [(item,) for item in tests])
        return

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kunit.py')
    command = [sys.executable, script, '--build-dir', state['build_dir']]
    mapped = map_shell_flags(args)
    value_options = {'--timeout', '--ip', '--manifest'}
    idx = 0
    while idx < len(mapped):
        arg = mapped[idx]
        if arg in value_options:
            if idx + 1 >= len(mapped):
                raise CliError('Missing option value', detail=arg)
            command.extend([arg, mapped[idx + 1]])
            idx += 2
            continue
        if arg.startswith('-'):
            command.append(arg)
        else:
            command.extend(['--program', arg])
        idx += 1
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Running KUnit')


def shell_clean(console, state):
    answer = input('Clean build directory? This moves build outputs to trash. [y/N] ').strip().lower()
    if answer not in ('y', 'yes'):
        console.info('Clean cancelled.')
        return
    command = [sys.executable, os.path.abspath(__file__), '--clean']
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Cleaning build directory')


def shell_check(console, state, args):
    target = args[0].lower() if args else 'tools'
    if target == 'manifest':
        command = [sys.executable, os.path.abspath(__file__), 'manifest', 'check', state['build_dir']]
    elif target in ('tools', 'robot'):
        command = [
            sys.executable,
            os.path.abspath(__file__),
            'doctor',
            state['source_dir'],
            '--build-dir',
            state['build_dir'],
        ]
    else:
        raise CliError('Unknown check target', detail=target, hints=['Use /check tools, /check robot, or /check manifest.'])
    run_shell_process(console, state, command, cwd=state['build_dir'], label='Checking {}'.format(target))


def shell_log(console, state, args):
    target = args[0].lower() if args else 'build'
    build_dir = state['build_dir']
    candidates = {
        'build': [os.path.join(build_dir, '.rossum', 'ninja-last.log'), os.path.join(build_dir, '.ninja_log')],
        'send': [os.path.join(build_dir, 'ftp.log')],
        'test': [os.path.join(build_dir, 'kunit.log')],
    }
    if target not in candidates:
        raise CliError('Unknown log target', detail=target, hints=['Use /log build, /log send, or /log test.'])
    for path in candidates[target]:
        if os.path.exists(path):
            console.panel('{} log'.format(target.title()), tail_text(path, 80), style='cyan')
            return
    raise CliError('Log not found', detail=', '.join(candidates[target]))


def run_shell_process(console, state, command, cwd, label):
    result = run_command_live(command, cwd=cwd, console=console, label=label)
    if result.returncode != 0:
        detail = summarize_ninja_failure(result.output) if command and command[0] == 'ninja' else result.output[-4000:]
        state['last_error'] = detail
        state['last_result'] = 'Failed'
        raise CliError(label + ' failed', detail=detail, exit_code=result.returncode)
    state['last_error'] = ''
    state['last_result'] = label + ' completed'
    console.success(label + ' completed.')


def rossum_config_command(state, mode):
    flags_by_mode = {
        'tp': ['-l'],
        'tests': ['-t'],
        'test': ['-t'],
        'source': ['-s'],
        'all': ['-s', '-l', '-t', '-i', '-f'],
    }
    if mode not in flags_by_mode:
        raise CliError('Unknown config mode', detail=mode, hints=['Use tp, tests, source, or all.'])
    return [sys.executable, os.path.abspath(__file__), state['source_dir'], state['build_dir']] + flags_by_mode[mode]


def map_shell_flags(args):
    mapped = []
    for arg in args:
        mapped.append('--dry-run' if arg == '--dry' else arg)
    return mapped


def read_manifest_if_present(build_dir):
    manifest_path = os.path.join(build_dir, FILE_MANIFEST)
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, 'r', encoding='utf-8', errors='replace') as handle:
            data = yaml.safe_load(handle) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def detect_shell_mode(manifest):
    if not isinstance(manifest, dict) or not manifest:
        return 'unknown'
    sections = {key for key, value in manifest.items() if key != 'ip' and value}
    if any(section.startswith('test') for section in sections):
        return 'tests'
    if 'tp' in sections:
        return 'tp'
    if 'src' in sections or 'karel' in sections:
        return 'source'
    if len(sections) > 1:
        return 'all'
    return 'unknown'


def shell_test_programs(build_dir):
    manifest = read_manifest_if_present(build_dir)
    tests = manifest.get('test')
    if not isinstance(tests, dict):
        return []
    return [os.path.splitext(name)[0] for name in tests.keys()]


def tail_text(path, max_lines):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise CliError('Could not read log', detail='{}: {}'.format(path, exc))
    return ''.join(lines[-max_lines:]) or '(empty log)'


def find_files_recur(top_dir, pattern):
    """
    """
    matches = []
    for root, dirnames, filenames in os.walk(top_dir, topdown=True):
        # if we find an ignore file, don't go down into that subtree
        if ROSSUM_IGNORE_NAME in filenames:
            logger.debug("Ignoring {0} (found {1})".format(root, ROSSUM_IGNORE_NAME))
            # discard any sub dirs os.walk(..) found in 'root'
            dirnames[:] = []
            continue

        for filename in fnmatch.filter(filenames, pattern):
            matches.append(os.path.join(root, filename))

    return matches


def parse_manifest(fpath, args):
    """Convert a package.json file into a RossumManifest struct
    """
    with open(fpath, 'r') as f:
        mfest = json.load(f)

    logger.debug("Loaded {0} from {1}".format(os.path.basename(fpath), os.path.dirname(fpath)))

    # make sure this is not a file that happens to be called 'package.json'
    if not 'manver' in mfest:
        logger.debug("Not a rossum pkg: {0}".format(fpath))
        raise InvalidManifestException("Not a rossum pkg")

    manver = int(mfest['manver'])
    if manver != MANIFEST_VERSION:
        raise InvalidManifestException("Unexpected manifest version: {0} "
            "(expected {1})".format(manver, MANIFEST_VERSION))

    return RossumManifest(
        name=mfest['project'],
        description=mfest['description'],
        version=mfest['version'],
        source=mfest['source'] if 'source' in mfest and args.buildsource else [],
        forms=mfest['forms'] if 'forms' in mfest else [],
        tp=mfest['tp'] if 'tp' in mfest else [],
        tests=mfest['tests'] if 'tests' in mfest else [],
        includes=mfest['includes'] if 'includes' in mfest else [],
        depends=mfest['depends'] if 'depends' in mfest else [],
        test_depends=mfest['tests-depends'] if 'tests-depends' in mfest else [],
        test_includes=mfest['tests-includes'] if 'tests-includes' in mfest else [],
        test_tp=mfest['tests-tp'] if 'tests-tp' in mfest else [],
        interfaces=mfest['tp-interfaces'] if 'tp-interfaces' in mfest else [],
        interfaces_depends=mfest['interface-depends'] if 'interface-depends' in mfest else [],
        interface_files=['tp/{}.kl'.format(i['program_name']) for i in mfest['tp-interfaces']] if 'tp-interfaces' in mfest else [],
        macros=mfest['macros'] if 'macros' in mfest else [],
        tpp_compile_env=mfest['tpp_compile_env'] if 'tpp_compile_env' in mfest else [])


def find_pkgs(dirs, args):
    """find packages in package path directories, and parse package.json files 
    into RossumPackage structs.
    """
    manifest_file_paths = []
    for d in dirs:
        logger.debug("Searching in {0}".format(d))
        manifest_file_paths_ = find_files_recur(d, MANIFEST_NAME)
        manifest_file_paths.extend(manifest_file_paths_)
        logger.debug("  found {0} manifest(s)".format(len(manifest_file_paths_)))
    logger.debug("Found {0} manifest(s) total".format(len(manifest_file_paths)))

    pkgs = []
    for manifest_file_path in manifest_file_paths:
        try:
            manifest = parse_manifest(manifest_file_path, args)
            pkg = RossumPackage(
                    dependencies=[],
                    include_dirs=[],
                    location=os.path.dirname(manifest_file_path),
                    manifest=manifest,
                    objects=[],
                    tests=[],
                    macros=[])
            pkgs.append(pkg)
        except InvalidManifestException as e:
            mfest_loc = os.path.join(os.path.split(
                os.path.dirname(manifest_file_path))[1], os.path.basename(manifest_file_path))
            if str(e) == "Not a rossum pkg":
                logger.debug("Ignoring non-Rossum manifest {0}: {1}.".format(mfest_loc, e))
            else:
                logger.warning("Error parsing manifest {0}: {1}.".format(mfest_loc, e))
        except Exception as e:
            mfest_loc = os.path.join(os.path.split(
                os.path.dirname(manifest_file_path))[1], os.path.basename(manifest_file_path))
            logger.warning("Error parsing manifest {0}: {1}.".format(mfest_loc, e))

    return pkgs

def remove_duplicates(pkgs):
    """create a seperate set with unique package names.
       input list must be the format of the collection
       RossumPackage.
    """
    visited = set()
    set_pkgs = []
    for pkg in pkgs:
        if pkg.manifest.name not in visited:
            visited.add(pkg.manifest.name)
            set_pkgs.append(pkg)
    
    return set_pkgs


def find_in_list(l, pred):
    """lamba function for finding item in a list
    """
    for i in l:
        if pred(i):
            return i
    return None


def create_dependency_graph(source_pkgs, all_pkgs, args):
    """
    Creates dependency graph for build
    Maps dependency pkg names to RossumPackage instances
    """
    # debug: show user source packages to resolve dependencies for
    pkg_names = [p.manifest.name for p in source_pkgs]
    logger.debug("Resolving dependencies for: {}".format(', '.join(pkg_names)))

    #start a dependency graph
    dep_graph = Graph()
    for pkg in source_pkgs:
        # set to track visited packages to avoid circular referencing
        visited = set()
        # add to final_pkgs object
        # set package as a root on dependency tree
        dep_graph.setRoot(pkg.manifest.name, pkg.manifest.version)
        deps = pkg.manifest.depends
        if (args.inc_tests):
          deps.extend(pkg.manifest.test_depends)
        if(args.build_interface):
          deps.extend(pkg.manifest.interfaces_depends)
        # Search through dependencies and add to dep graph and to
        # dependencies in RossumPackage collection
        add_dependency(pkg, visited, args, dep_graph, all_pkgs)
    
    return dep_graph

def add_dependency(src_package, visited, args, graph, pkgs):
    """build out dependency tree, traversing dependencies in the parent node.
    """
    if src_package.manifest.name not in visited:
        logger.debug("  {}:".format(src_package.manifest.name))
        for depend_name in src_package.manifest.depends:
            dep_pkg = find_in_list(pkgs, lambda p: p.manifest.name == depend_name)
            if dep_pkg is None:
                raise MissingPkgDependency("Error finding internal pkg instance for '{}', "
                    "can't find it".format(depend_name))
            # add graph edge and put dependencies into RossumPackage Object
            graph.addEdge(src_package.manifest.name, depend_name, dep_pkg.manifest.version, False)
            logger.debug("    {}: found".format(depend_name))
            src_package.dependencies.append(dep_pkg)
            # after dependency has been added track to visited set to avoid circular dependencies
            visited.add(src_package.manifest.name)
            #if depend package has dependencies search for those as well
            deps = dep_pkg.manifest.depends
            if (args.inc_tests):
              if len(deps) > 0:
                deps.extend(dep_pkg.manifest.test_depends)
              else:
                deps = dep_pkg.manifest.test_depends
            if(args.build_interface):
              if len(deps) > 0:
                deps.extend(dep_pkg.manifest.interfaces_depends)
              else:
                deps = dep_pkg.manifest.interfaces_depends
            if len(deps) > 0:
                add_dependency(dep_pkg, visited, args, graph, pkgs)

def log_dep_tree(graph):
    """write depedency trees from source packages
       to debug logger
    """
    pkg_names = [p.name for p in graph.root]
    for name in pkg_names:
        #print depedency tree for logger
        logger.debug("Printing dependency tree for: {}".format(name))
        depstring = graph.print_dependencies(name)
        if depstring is not None:
            ## split into seperate lines for debug logger
            depstring = depstring.splitlines()
            for line in depstring:
                logger.debug("  {}".format(line))


def filter_packages(pkgs, graph):
    """filter out packages in RossumPackage that
       are not in the dependency tree
    """
    #create new list to store applicable packages
    filtered = []
    #find all root packages in the source
    pkg_names = [p.name for p in graph.root]
    # track visited packages to avoid duplicates
    visited = set()
    for name in pkg_names:
        #retrieve all packages the source package depends on
        deps = graph.depthFirstSearch(name)
        if len(deps) > 0:
            for d in deps:
                if d not in visited:
                    filtered.append(find_in_list(pkgs, lambda p: p.manifest.name == d))
                    visited.add(d)
    # return filtered list of packages
    return filtered


def dedup(seq):
    """ Remove duplicates from a sequence, but:

     1. don't change element order
     2. keep the last occurence of each element instead of the first

    Example:
       a = [1, 2, 1, 3, 4, 1, 2, 6, 2]
       b = dedup(a)

    b is now: [3 4 1 6 2]
    """
    out = []
    for e in reversed(seq):
        if e not in out:
            out.insert(0, e)
    return out

def resolve_includes(pkgs, args):
    """ Gather include directories for all packages in 'pkgs'.
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Resolving includes for: {}".format(', '.join(pkg_names)))
    
    for pkg in pkgs:
        visited = set()
        logger.debug("  {}".format(pkg.manifest.name))
        inc_dirs = dedup(resolve_includes_for_pkg(pkg, visited, args))
        pkg.include_dirs.extend(inc_dirs)
        logger.debug("    added {} path(s)".format(len(inc_dirs)))


def resolve_includes_for_pkg(pkg, visited, args):
    """ Recursively gather include directories for a specific package.
    Makes all include directories absolute as well.
    """
    inc_dirs = []
    if pkg.manifest.name not in visited:
        # include dirs of current pkg first
        for inc_dir in pkg.manifest.includes:
            abs_inc = os.path.abspath(os.path.join(pkg.location, inc_dir))
            inc_dirs.append(abs_inc)
        if (args.inc_tests):
          for inc_dir in pkg.manifest.test_includes:
            abs_inc = os.path.abspath(os.path.join(pkg.location, inc_dir))
            inc_dirs.append(abs_inc)
        visited.add(pkg.manifest.name)
        # then ask dependencies
        for dep_pkg in pkg.dependencies:
            inc_dirs.extend(resolve_includes_for_pkg(dep_pkg, visited, args))
    return inc_dirs

def resolve_macros(pkgs, args):
    '''determine any user defined macros to pass to ktransw
    '''
    # Generate current date stamp in format: YYYY-MM-DD
    date_stamp = datetime.datetime.now().strftime('%Y-%m-%d')
    
    for pkg in pkgs:
      # Add automatic DATE_STAMP macro
      pkg.macros.append('DATE_STAMP="{}"'.format(date_stamp))
      
      if args.user_macros:
        pkg.macros.extend(args.user_macros)
      if len(pkg.manifest.macros):
        pkg.macros.extend(pkg.manifest.macros)


def get_interfaces(pkgs):
    """Get all of the TP interfaces specified in package.json, and store them
    as TPInterfaces collections.
    """
    programs = []
    for pkg in pkgs:
        for include in  pkg.manifest.includes:
            #get all .klh files in include directory
            if not os.path.isabs(include):
              f_name = pkg.location + '\\' + include
            else:
              f_name = include
            inc_files = [f_name + "\\" + fl for fl in os.listdir(f_name) if fl.endswith(".klh")]
            for interface in pkg.manifest.interfaces:
                found_routine = False
                #match routine specified in tp-interfaces
                #interface['name'] will be the full name of the program
                #interface['alias'] will be the 12 character limit program name sent to the controller
                pattern = r"(?:ROUTINE\s*{0})\s*\(?(?:\s*(\w+)\s*\:\s*(\w+)\s*;?)*\)?\s*(?:\:\s*(\w+))?\s*(?:FROM\s*\w+)".format(interface['routine'])
                for fname in inc_files:
                    if found_routine : break #have found the routine and parsed move to next interface
                    #search through each .klh file
                    with open(fname,"r") as f:
                        lines = f.readlines()
                        for ln in lines :
                            m = re.match(pattern, ln)
                            if m:
                                #find all of the arguments and their types
                                # *** This will not work if formated
                                # *** ROUTINE t(v1,v2,v3 : INTEGER)
                                # *** must be formatted
                                # *** ROTUINE t(v1 : INTEGER; v2 : INTEGER; v3 : INTEGER)
                                routine = m.group()
                                var_matches = re.findall(r"(\w+)\s*\:\s*(\w+)\s*(;|\))",routine)
                                arguments = []

                                if 'default_params' in interface:
                                  #convert keys to integers
                                  default_args = {int(k)-1:v for k,v in interface['default_params'].items()}
                                else:
                                  default_args = {}
                                
                                #for var_matches with index
                                for i, v in enumerate(var_matches):
                                  if i in default_args:
                                    arguments.append([v[0], v[1], default_args[i]])
                                  else:
                                    arguments.append([v[0], v[1], None])

                                #store return type
                                if m.group(3):
                                  ret_type = m.group(3)
                                else:
                                  ret_type = ''

                                programs.append(TPInterfaces(
                                    name= interface['routine'],
                                    alias= interface['program_name'],
                                    include_file= os.path.basename(fname),
                                    path= '{}\\tp\\{}.kl'.format(pkg.location, interface['program_name']),
                                    depends= pkgs[0].manifest.interfaces_depends,
                                    arguments= arguments,
                                    return_type= ret_type
                                ))
                                # outer loop break control
                                found_routine = True
                                break

    return programs

def create_interfaces(interfaces):
    """Generates Karel program for the specified interface in package.json.
    example:
    PROGRAM mth_abs
      %NOBUSYLAMP
      %NOLOCKGROUP

      VAR
        out_reg : INTEGER
        val : REAL
      %include tpe.klh
      %from registers.klh %import set_real
      %from math.builtins.klh %import abs

      BEGIN
        val = tpe__get_real_arg(1)
        out_reg = tpe__get_int_arg(2)
        registers__set_real(out_reg, math__abs(val))
      END mth_abs
    """
    for interface in interfaces:
        program = "PROGRAM {0}\n" \
                  "%NOBUSYLAMP\n" \
                  "%COMMENT = 'DATE_STAMP'\n" \
                  "%NOLOCKGROUP\n" \
                  "\n".format(interface.alias)

        pose_types = ('position', 'xyzwpr', 'jointpos', 'vector')
        
        if interface.return_type or interface.arguments:
          program += 'VAR\n'

        #if return type first tpe argument should be return register
        if interface.return_type:
            program += '\tout_reg : INTEGER\n'
            if interface.return_type.lower() in pose_types:
              program += '\tout_grp : INTEGER\n'

        # make arguments
        i = 1
        pr_dict = {}
        for args in interface.arguments:
            if args[1].lower() in pose_types:
              program += '\tpr_num{0} : INTEGER\n'.format(i)
              # key = pr_variable : val = group_num
              # if no group num is specified mark value as 'None'
              pr_dict['pr_num{0}'.format(i)] = {'index' : i, 'group' : 'None', 'type' : args[1].lower(), 'map_var' : args[0] }

            # var definition of strings must specify a size. 
            var_typ = args[1]
            if var_typ == 'STRING':
              var_typ = 'STRING[32]'
            program += '\t{0} : {1}\n'.format(args[0], var_typ)
            i += 1
        
        #flag if groups are specified
        is_groups = False
        #do second pass through pr_dict to replace any groups with specified arguement
        if any(args[1].lower() in pose_types for args in interface.arguments):
          i = 1
          for args in interface.arguments:
            if args[0].lower() in 'grp_no':
              is_groups = True
              pr_dict['pr_num{0}'.format(i)]['group'] = args[0].lower()
              i += 1
        
        # load applicable tpe interfaces
        if interface.return_type or interface.arguments:
          program += "%include tpe.vars.klh\n"
        
        #use set to remove duplicates
        load_funcs = set()
        for args in interface.arguments:
          t_arg = 'int' if args[1].lower() == 'integer' else args[1].lower()
          load_funcs.add("get_{0}_arg".format(t_arg))
        if interface.return_type:
          load_funcs.add("get_int_arg")
        
        #load write to register function
        if interface.return_type:
          t_return = 'int' if interface.return_type.lower() == 'integer' else interface.return_type.lower()
          program += "%from registers.klh %import set_{0}\n".format(t_return)

        #include function for handling position types
        #if 'pose' in interface.depends:
        program += "%from pose.klh %import get_posreg_xyz, get_posreg_joint, set_posreg_xyz, set_posreg_joint, set_vector_to_posreg\n"


        #include header files
        func_name = interface.name.split('__')[-1] # assuming formating is 'namespace__function'
        program += "%from {0} %import {1}\n\n".format(interface.include_file, func_name)
        program += "BEGIN\n"
        # tpe arguments
        arg_list = []
        i = 1
        for args in interface.arguments:
            t_arg = 'int' if args[1].lower() == 'integer' else args[1].lower()

            #check for default values
            has_default = False
            if args[2]:
              program += 'IF NOT tpe__parameter_exists({0}) THEN\n'.format(i)
              has_default = True
              program += '\t{0} = {1}\n'.format(args[0], args[2])
              program += 'ELSE\n'

            if args[1].lower() in pose_types:
              if args[1].lower() in ['xyzwpr','position']: t_arg = 'xyz'
              if args[1].lower() in 'jointpos': t_arg = 'joint'
              
              program += '\tpr_num{0} = tpe__get_int_arg({0})\n'.format(i)
            else:
              program += '\t{0} = tpe__get_{1}_arg({2})\n'.format(args[0], t_arg, i)

            if has_default:
              program += 'ENDIF\n'

            arg_list.append(args[0])
            i += 1
        
        # add calls to retrieve position register
        for key, value in pr_dict.items():
          if value['type'] in ['xyzwpr','position']: value['type'] = 'xyz'
          if value['type'] in 'jointpos': value['type'] = 'joint'
          if value['type'] == 'vector':
            program += '\t{0} = tpe__get_vector_arg({1})\n'.format(value['map_var'], key)
          else:
            if value['group'] == 'None':
              program += '\t{0} = pose__get_posreg_{1}({2}, 1)\n'.format(value['map_var'], value['type'], key)
            else:
              program += '\t{0} = pose__get_posreg_{1}({2}, {3})\n'.format(value['map_var'], value['type'], key, value['group'])

        
        #set return register
        if interface.return_type:
          program += '\tout_reg = tpe__get_int_arg({})\n'.format(i)
          i += 1
        
        #set arguement for group number if return type is a position
        if interface.return_type.lower() in pose_types and is_groups:
          program += 'IF NOT tpe__parameter_exists({0}) THEN\n'.format(i)
          program += '\tout_grp = 1\n'
          program += 'ELSE\n'
          program += '\tout_grp = tpe__get_int_arg({})\n'.format(i)
          program += 'ENDIF\n'
          i += 1
        
        #set return and karel routine
        if interface.return_type:
            t_return = 'int' if interface.return_type.lower() == 'integer' else interface.return_type.lower()
            if interface.return_type.lower() in ['xyzwpr', 'position']: t_return = 'xyz'
            if interface.return_type.lower() in 'jointpos': t_return = 'joint'

            if interface.arguments:
              arg_str = ",".join(arg_list)
              if interface.return_type.lower() in pose_types:
                if t_return == 'vector':
                  program += '\tpose__set_vector_to_posreg({0}({1}), out_reg)\n'.format(interface.name, arg_str)
                else:
                  if is_groups:
                    program += '\tpose__set_posreg_{0}({1}({2}), out_reg, out_grp)\n'.format(t_return, interface.name, arg_str)
                  else:
                    program += '\tpose__set_posreg_{0}({1}({2}), out_reg, 1)\n'.format(t_return, interface.name, arg_str)
              else:
                program += '\tregisters__set_{0}(out_reg, {1}({2}))\n'.format(t_return, interface.name, arg_str)
            else:
              program += '\tregisters__set_{0}(out_reg, {1})\n'.format(t_return, interface.name)
        else:
            #if not return type just run function
            if interface.arguments:
              arg_str = ",".join(arg_list)
              program += '\t{0}({1})\n'.format(interface.name, arg_str)
            else:
              program += '\t{0}\n'.format(interface.name)

        program += 'END {}'.format(interface.alias)

        #save program to path
        if not os.path.exists(os.path.dirname(interface.path)):
            os.makedirs(os.path.dirname(interface.path))
        with open(interface.path, 'w+') as fl:
            fl.write(program)


def build_output_name(src, suffix, preserve_build_paths):
    """Return a build-dir-relative output path for a package source file."""
    src = os.path.normpath(src)
    base = os.path.splitext(os.path.basename(src))[0]

    if not preserve_build_paths:
        return '{}.{}'.format(base, suffix)

    stem = os.path.splitext(src)[0]
    drive, tail = os.path.splitdrive(stem)
    parts = []

    if drive:
        parts.extend(['_absolute', drive.replace(':', '')])

    for part in tail.replace('/', '\\').split('\\'):
        if part in ('', '.'):
            continue
        if part == '..':
            parts.append('_external')
        else:
            parts.append(part)

    if not parts:
        parts.append(base)

    return '{}.{}'.format(os.path.join(*parts), suffix)


def as_list(value):
    if isinstance(value, list):
        return value
    return [value]


def build_output_names(src, suffix, preserve_build_paths, child_bases=None):
    parent_output = build_output_name(src, suffix, preserve_build_paths)
    if not child_bases:
        return parent_output, parent_output

    parent_dir = os.path.dirname(parent_output)
    child_outputs = []
    for child_base in child_bases:
        child_name = '{}.{}'.format(child_base, suffix)
        child_outputs.append(os.path.join(parent_dir, child_name) if parent_dir else child_name)

    return child_outputs, parent_output


def ninja_build_outputs(outputs):
    return ' '.join(['$build_dir\\{}'.format(output) for output in as_list(outputs)])


def ninja_main_output(output):
    return '$build_dir\\{}'.format(output)


def ninja_all_outputs(pkgs):
    outputs = []
    for pkg in pkgs:
        for obj in pkg.objects:
            outputs.extend(['$build_dir\\{}'.format(output) for output in as_list(obj[1])])
    return ' '.join(outputs)


def ninja_description(src, pkg_name, compiletp):
    lower = src.lower()
    if lower.endswith('.tpp'):
        action = 'TP+ -> TP' if compiletp else 'TP+ -> LS'
    elif lower.endswith('.kl'):
        action = 'KAREL -> PC'
    elif lower.endswith('.ls'):
        action = 'LS -> TP' if compiletp else 'LS copy'
    elif lower.endswith(('.yml', '.yaml', '.json')):
        action = 'DATA -> XML'
    elif lower.endswith('.xml'):
        action = 'XML copy'
    elif lower.endswith('.csv'):
        action = 'CSV copy'
    elif lower.endswith(('.utx', '.ftx')):
        action = 'FORM -> TX'
    else:
        action = 'BUILD'
    return '{} | {} :: {}'.format(action, pkg_name.replace(' ', '_'), src)


def manifest_objects(pkgs):
    objects = []
    for pkg in pkgs:
        for obj in pkg.objects:
            for output in as_list(obj[2]):
                objects.append((output, obj[3]))
    return objects


def ensure_output_dirs(pkgs, build_dir):
    """Create build output directories used by generated Ninja rules."""
    for pkg in pkgs:
        for obj in pkg.objects:
            outputs = []
            outputs.extend(as_list(obj[1]))
            outputs.extend(as_list(obj[2]))
            if len(obj) > 4:
                outputs.append(obj[4])

            for output in outputs:
                output_dir = os.path.dirname(os.path.join(build_dir, output))
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)


def gen_obj_mappings(pkgs, mappings, args, dep_graph):
    """ Updates the 'objects' member variable of each pkg with tuples of the
    form (path\to\a.kl, a.pc).
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Generating src to obj mappings for: {}".format(', '.join(pkg_names)))

    # start with assumption no tpp files are in package
    args.hastpp = False

    for pkg in pkgs:
        logger.debug("  {}".format(pkg.manifest.name))
        cell_no = cell_no_from_macros(pkg.macros)

        # include forms in source
        if args.build_forms:
          pkg.manifest.source.extend(pkg.manifest.forms)

        # include LS files in source
        if args.build_ls:
          pkg.manifest.source.extend(pkg.manifest.tp)

          if args.inc_tests and hasattr(pkg.manifest, 'test_tp'):
            pkg.manifest.source.extend(pkg.manifest.test_tp)

        for src in pkg.manifest.source:
            src = src.replace('/', '\\')
            for (k, v) in mappings.items():
                if '.' + v['from_suffix'] in src:
                    child_bases = tpp_child_outputs(pkg.location, src, cell_no) if k == 'tpp' and not args.compiletp else []
                    obj, main_out = build_output_names(src, v['interp_suffix'], args.preserve_build_paths, child_bases)
                    build, _ = build_output_names(src, v['comp_suffix'], args.preserve_build_paths, child_bases)
                    if v['type'] == 'karel':
                      typ = 'src'
                    else:
                      typ = v['type']
                    # check if tpp file is in package
                    if k == 'tpp':
                      args.hastpp = True
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj, build, typ, main_out))

        # add interfaces to mappings
        if (args.build_interface):
          if args.buildall or any(pkg.manifest.name in x.name for x in dep_graph.root):
            for src in pkg.manifest.interface_files:
              src = src.replace('/', '\\')
              for (k, v) in mappings.items():
                  if '.' + v['from_suffix'] in src:
                      obj, main_out = build_output_names(src, v['interp_suffix'], args.preserve_build_paths)
                      build, _ = build_output_names(src, v['comp_suffix'], args.preserve_build_paths)
                      typ = 'interface'
              logger.debug("    adding: {} -> {}".format(src, obj))
              pkg.objects.append((src, obj, build, typ, main_out))

        # add tests to mappings
        if (args.inc_tests) and any(pkg.manifest.name in x.name for x in dep_graph.root):
          for src in pkg.manifest.tests:
              src = src.replace('/', '\\')
              for (k, v) in mappings.items():
                  if '.' + v['from_suffix'] in src:
                      child_bases = tpp_child_outputs(pkg.location, src, cell_no) if k == 'tpp' and not args.compiletp else []
                      obj, main_out = build_output_names(src, v['interp_suffix'], args.preserve_build_paths, child_bases)
                      build, _ = build_output_names(src, v['comp_suffix'], args.preserve_build_paths, child_bases)
                      if v['type'] == 'karel':
                        typ = 'test'
                      else:
                        typ = 'test_' + v['type']
                      # check if tpp file is in package
                      if k == 'tpp':
                        args.hastpp = True
              logger.debug("    adding: {} -> {}".format(src, obj))
              pkg.objects.append((src, obj, build, typ, main_out))


def cell_no_from_macros(macros):
    for macro in macros:
        match = re.match(r'CELL_NO=([0-9]+)', macro)
        if match:
            return match.group(1)
    return None


def tpp_child_outputs(pkg_location, src, cell_no):
    source_path = os.path.normpath(os.path.join(pkg_location, src))
    if not os.path.exists(source_path):
        return []
    if not tpp_is_function_only(source_path):
        return []
    return parse_tpp_child_bases(source_path, cell_no)


def tpp_is_function_only(source_path):
    block_depth = 0
    saw_function = False

    with open(source_path, 'r') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or line.startswith('.'):
                continue

            if re.match(r'namespace\b', line):
                block_depth += 1
                continue

            if re.match(r'(inline\s+)?def\s+', line):
                block_depth += 1
                saw_function = True
                continue

            if line == 'end':
                block_depth = max(0, block_depth - 1)
                continue

            if block_depth == 0:
                return False

    return saw_function


def find_fr_install_dir(search_locs, is64bit=False):
    """Find install directory of roboguide looking through registry keys
    """
    try:
        import winreg as wreg

        # always use 32-bit registry view, unless requested not to. Roboguide
        # is a 32-bit application, so its keys are stored in the 32-bit view.
        sam_flags = wreg.KEY_READ
        if not is64bit:
            sam_flags |= wreg.KEY_WOW64_32KEY

        # find roboguide install dir
        with wreg.OpenKey(wreg.HKEY_LOCAL_MACHINE, r'Software\FANUC', 0, sam_flags) as fr_key:
            fr_install_dir = wreg.QueryValueEx(fr_key, "InstallDir")[0]

        # get roboguide version
        # TODO: this will fail if roboguide isn't installed
        with wreg.OpenKey(wreg.HKEY_LOCAL_MACHINE, r'Software\FANUC\ROBOGUIDE', 0, sam_flags) as rg_key:
            rg_ver = wreg.QueryValueEx(rg_key, "Version")[0]

        logger.info("Found Roboguide version: {0}".format(rg_ver))
        if os.path.exists(os.path.join(fr_install_dir, 'Shared')):
            logger.debug("Most likely FANUC base-dir: {}".format(fr_install_dir))
            return fr_install_dir

    except WindowsError as we:
        logger.debug("Couldn't find FANUC registry key(s), trying other methods")
    except ImportError as ime:
        logger.debug("Couldn't import 'winreg' module, can't access Windows registry, trying other methods")

    # no windows registry, try looking in the file system
    logger.warning("Can't find FANUC base-dir using registry, switching to file-system search")

    for search_loc in search_locs:
        logger.debug("Looking in '{0}'".format(search_loc))
        candidate_path = os.path.join(search_loc, 'Shared')
        if os.path.exists(candidate_path):
            logger.debug("Found FANUC base-dir: {}".format(search_loc))
            return search_loc

    logger.warning("Exhausted all methods to find FANUC base-dir")
    raise Exception("Can't find FANUC base-dir anywhere")

def find_program(tool, search_locs):
    """Helper function for `find_tools` to help find tool programs.
    """
    for search_loc in search_locs:
        path = os.path.join(search_loc, tool)
        if os.path.exists(path):
            return path
    
    logger.warning("Can't find {} anywhere".format(tool))
    raise MissingKtransException("Can't find {} anywhere".format(tool))

def find_ktrans_support_dir(fr_base_dir, version_string):
    """Find support files directory of specified core version 
    """
    logger.debug('Trying to find support dir for core version: {}'.format(version_string))
    version_dir = version_string.replace('.', '')
    support_dir = os.path.join(fr_base_dir, 'WinOLPC', 'Versions', version_dir, 'support')

    logger.debug("Looking in {} ..".format(support_dir))
    if os.path.exists(support_dir):
        logger.debug("Found {} support dir: {}".format(version_string, support_dir))
        return support_dir

    raise Exception("Can't determine ktrans support dir for core version {}"
        .format(version_string))

def find_tools(search_locs, tools, args):
    """Find the locations of the tools specified in macros:
    tools = [KTRANS_BIN_NAME, KTRANSW_BIN_NAME, MAKETP_BIN_NAME, TPP_BIN_NAME, XML_BIN_NAME, KCDICT_BIN_NAME]
    """
    tool_paths =[]
    for tool in tools:
        try:
            tool_path = find_program(tool, search_locs)
            logger.info("{} location: {}".format(tool, tool_path))
            tool_paths.append(tool_path)
        except MissingKtransException as mke:
            logger.fatal("Aborting: {0}".format(mke))
            sys.exit(_OS_EX_DATAERR)
        except Exception as e:
            logger.fatal("Aborting: {0} (unhandled, please report)".format(e))
            sys.exit(_OS_EX_DATAERR)

    return tool_paths

#---- Parse robot.ini file ----
#####
def find_robotini(source_dir, args):
    """
      check we can find a usable robot.ini somewhere.
      strategy:
        - if user provided a location, use that
        - if not, try CWD (default value of arg is relative to CWD)
        - if that doesn't work, try source space
    """

    # because 'args.robot_ini' has a default which is simply 'robot.ini', we
    # cover the first two cases in the above list with this single statement
    robot_ini_loc = os.path.abspath(args.robot_ini)

    # check that it actually exists
    logger.debug("Checking: {}".format(robot_ini_loc))
    if not os.path.exists(robot_ini_loc):
        logger.debug("No {} in CWD, trying source space".format(ROBOT_INI_NAME))

        robot_ini_loc = os.path.join(source_dir, ROBOT_INI_NAME)
        logger.debug("Checking: {}".format(robot_ini_loc))
        if os.path.exists(robot_ini_loc):
            logger.debug("Found {} in source space".format(ROBOT_INI_NAME))
        else:
            logger.warning("File does not exist: {}".format(robot_ini_loc))
            logger.fatal("Cannot find a {}, aborting".format(ROBOT_INI_NAME))
            sys.exit(_OS_EX_DATAERR)
        
        # non-"empty" robot.ini files may conflict with rossum and/or ktransw
        # CLAs. Ideally, we'd allow rossum/ktransw CLAs to override paths and
        # other settings from robot.ini files, but for now we'll only just
        # WARN the user if we find a non-empty file.
        with open(robot_ini_loc, 'r') as f:
            robot_ini_txt = f.read()
            if ('Path' in robot_ini_txt) or ('Support' in robot_ini_txt):
                logger.debug("Found {} contains potentially conflicting ktrans "
                    "settings.".format(ROBOT_INI_NAME))
    
    return robot_ini_loc

def parse_robotini(fpath):
    """parse the robot.ini file into a struct, for use by rossum.
    """
    
    config = configparser.ConfigParser()
    config.read(fpath)

    # check that ini file has proper section
    if not 'WinOLPC_Util' in config:
        logger.fatal("Not a robot.ini file. Missing ['WinOLPC_Util'] section.")
        logger.fatal("Re-export robot.ini file from setrobot.exe. Aborting.")
        sys.exit(_OS_EX_DATAERR)

    #get rid of slashes in front and behind of drive letter (i.e. \\C\\ -> C:\\)
    config['WinOLPC_Util']['Robot'] = config['WinOLPC_Util']['Robot'][1] + ':' + config['WinOLPC_Util']['Robot'][2:]

    #try to add a base path to use to find ktrans.exe and roboguide
    # if WinOLPC folder is not found ignore a path for base_path.
    try:
        config['WinOLPC_Util']['Base_Path'] = config['WinOLPC_Util']['Path'].split("\\WinOLPC")[0]
    except:
        config['WinOLPC_Util']['Base_Path'] = ""
        pass

    #check that paths in robot.ini file exist. 
    ## ignore version as its not a path
    ## ignore outfile as does not matter for rossum or ktransw
    for k,v in config['WinOLPC_Util'].items():
        if (k == 'robot' or k == 'path' or k == 'support') and not os.path.exists(v):
            logger.fatal("Directory '{0}' in robot.ini does not exist. Aborting".format(v))
            sys.exit(_OS_EX_DATAERR)

    # handle added 'ftp' key if omitted
    if "Ftp" not in config['WinOLPC_Util']:
        config['WinOLPC_Util']['Ftp'] = os.environ.get(ENV_SERVER_IP)

    # handle tpp env
    if "Env" not in config['WinOLPC_Util']:
        config['WinOLPC_Util']['Env'] = ''

    return robotiniInfo(
        robot=config['WinOLPC_Util']['Robot'],
        version=config['WinOLPC_Util']['Version'],
        base_path=config['WinOLPC_Util']['Base_Path'],
        version_path=config['WinOLPC_Util']['Path'],
        support=config['WinOLPC_Util']['Support'],
        output=config['WinOLPC_Util']['Output'],
        ftp=config['WinOLPC_Util']['Ftp'],
        env=config['WinOLPC_Util']['Env'])

def write_manifest(manifest, files, ipAddress):
    """Write manifest file for kpush. Catagorize out source, test,
      tp+, ls, xml/csv files.
    """

    file_list = {'ip': ipAddress}

    #save file. null list in value is for ktransw objects
    #and templates
    for fl in files:
      if fl[1] not in file_list.keys():
        file_list[fl[1]] = {}
      sub_dict = file_list[fl[1]]
      if fl[0] not in sub_dict.keys():
        file_list[fl[1]][fl[0]] = []

    #save back to yaml file
    with open(manifest, 'w') as man:
      yaml.dump(file_list, man)


def update_tp_outputs(build_dir):
    """Update .man_log with tp-plus files generated from non-inline functions."""
    manifest_path = os.path.join(build_dir, FILE_MANIFEST)
    if not os.path.exists(manifest_path):
        return

    lock_path = manifest_path + '.lock'

    while True:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(lock_fd)
            break
        except FileExistsError:
            time.sleep(0.05)

    try:
        manifest = {}
        attempts = 0
        while attempts < 5:
            try:
                with open(manifest_path, 'r') as f:
                    manifest = yaml.safe_load(f) or {}
                if isinstance(manifest, dict):
                    break
            except yaml.YAMLError:
                pass
            attempts += 1
            time.sleep(0.05)

        if not isinstance(manifest, dict):
            return

        for section in ('tp', 'test_tp'):
            if section not in manifest or not isinstance(manifest[section], dict):
                continue

            for parent_file in list(manifest[section].keys()):
                matches = generated_tp_outputs(build_dir, parent_file)
                if matches:
                    if tp_output_exists(build_dir, parent_file):
                        manifest[section][parent_file] = sorted(set(matches))
                    else:
                        del manifest[section][parent_file]
                        for generated_file in sorted(set(matches)):
                            manifest[section].setdefault(generated_file, [])

        with open(manifest_path, 'w') as f:
            yaml.safe_dump(manifest, f)
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass


def generated_tp_outputs(build_dir, parent_file):
    """Find child .ls/.tp files generated by a parent tp-plus output."""
    parent_path = parent_file.replace('/', os.sep).replace('\\', os.sep)
    parent_dir = os.path.dirname(parent_path)
    parent_base = os.path.splitext(os.path.basename(parent_path))[0]
    search_dir = os.path.join(build_dir, parent_dir)

    if not os.path.isdir(search_dir):
        return []

    expected = [base.lower() for base in expected_tp_child_bases(build_dir).get(os.path.normcase(parent_path), [])]
    if parent_base.lower() in expected:
        return []

    prefix = (parent_base + '_').lower()
    matches = []

    for filename in os.listdir(search_dir):
        name, ext = os.path.splitext(filename)
        if ext.lower() not in ('.ls', '.tp'):
            continue

        if name.lower() in expected or name.lower().startswith(prefix):
            generated_file = os.path.join(parent_dir, filename) if parent_dir else filename
            matches.append(generated_file)

    return matches


def tp_output_exists(build_dir, output_file):
    output_path = output_file.replace('/', os.sep).replace('\\', os.sep)
    return os.path.exists(os.path.join(build_dir, output_path))


def expected_tp_child_bases(build_dir):
    """Map parent outputs to expected child output basenames from source .tpp."""
    ninja_path = os.path.join(build_dir, BUILD_FILE_NAME)
    if not os.path.exists(ninja_path):
        return {}

    with open(ninja_path, 'r') as f:
        lines = f.readlines()

    variables = {}
    for line in lines:
        if line.startswith('build '):
            continue
        match = re.match(r'^([A-Za-z0-9_.-]+)\s*=\s*(.*)$', line.rstrip())
        if match:
            variables[match.group(1)] = match.group(2)

    child_bases = {}
    cell_no = find_cell_no(variables)

    for line in lines:
        if not line.startswith('build ') or ' tpp_' not in line:
            continue

        match = re.match(r'^build\s+(.+?):\s+\S+\s+(.+)$', line.rstrip())
        if not match:
            continue

        parent_outputs = [expand_ninja_vars(output, variables) for output in match.group(1).split()]
        source_path = expand_ninja_vars(match.group(2).split()[0], variables)
        source_path = os.path.normpath(source_path)

        if not os.path.exists(source_path):
            continue

        bases = parse_tpp_child_bases(source_path, cell_no)
        if bases:
            for parent_output in parent_outputs:
                parent_rel = os.path.relpath(os.path.normpath(parent_output), build_dir)
                child_bases[os.path.normcase(parent_rel)] = bases

    return child_bases


def expand_ninja_vars(value, variables):
    """Expand the simple $var and ${var} forms emitted by Rossum."""
    def replace_braced(match):
        return variables.get(match.group(1), match.group(0))

    value = re.sub(r'\$\{([^}]+)\}', replace_braced, value)

    def replace_plain(match):
        return variables.get(match.group(1), match.group(0))

    return re.sub(r'\$([A-Za-z0-9_.-]+)', replace_plain, value)


def find_cell_no(variables):
    for name, value in variables.items():
        if not name.endswith('_macros'):
            continue
        match = re.search(r'/DCELL_NO=([0-9]+)', value)
        if match:
            return match.group(1)
    return None


def parse_tpp_child_bases(source_path, cell_no):
    namespace = ''
    child_bases = []

    with open(source_path, 'r') as f:
        for line in f:
            namespace_match = re.match(r'\s*namespace\s+([A-Za-z_][A-Za-z0-9_]*)\b', line)
            if namespace_match:
                namespace = resolve_tpp_name(namespace_match.group(1), cell_no)
                continue

            function_match = re.match(r'\s*(inline\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', line)
            if not function_match or function_match.group(1):
                continue

            function_name = resolve_tpp_name(function_match.group(2), cell_no)
            if namespace:
                child_bases.append('{}_{}'.format(namespace, function_name))
            else:
                child_bases.append(function_name)

    return child_bases


def resolve_tpp_name(name, cell_no):
    if cell_no:
        if name.startswith('CELL_ID'):
            return 'cell{}{}'.format(cell_no, name[len('CELL_ID'):].lower())
        name = name.replace('CELL_ID', 'cell{}'.format(cell_no))
    return name


#Class to represent a graph 
class Graph:

    def __init__(self, root=None, version=None): 
        self.graph = collections.defaultdict(list) #dictionary containing adjacency List
        self.root = []
        if root is not None and version is not None:
            self.root.append(self.addPackage(root, version, True))

    def __getitem__(self, key):
        for next in self.root:
            if next.name == key:
                return next

    def print_dependencies(self, rootname):
        depList = ''
        
        stack = self.depthFirstSearch(rootname)
        depList += '<{}> {} {x}\n'.format(rootname, self[rootname].version, x='*' if self[rootname].inSource else '')
        stack.remove(rootname)

        for next in self.graph[rootname]:
            depList = self.depPrintRec(next, stack, '|-- ', depList)

        return depList

    def depPrintRec(self, pkg, stack, prepStr, outstr):
        if pkg.name in stack:
            outstr += prepStr + '<{}> {} {x}\n'.format(pkg.name, pkg.version, x='*' if pkg.inSource else '')
            stack.remove(pkg.name)

        for next in self.graph[pkg.name]:
            if next.name in stack:
                outstr = self.depPrintRec(next, stack, '|   ' + prepStr, outstr)

        return outstr

  
    def addPackage(self, Name, Version, Source):
        return packages(
                name= Name,
                version= Version,
                inSource= Source)

    def setRoot(self, name, version):
        self.root.append(self.addPackage(name, version, True))

    # function to add an edge to graph 
    def addEdge(self, pNode, cNode, version, isSource):
        self.graph[pNode].append(self.addPackage(cNode, version, isSource))

    def depthFirstSearch(self, start, visited=None, stack=None):
        if visited is None:
            visited = set()
        if stack is None:
            stack = []
            
        stack.append(start)
        visited.add(start)
        
        pkg_names = set([p.name for p in self.graph[start]])

        difference = pkg_names - visited
        for next in difference:
            self.depthFirstSearch(next,visited, stack)
        
        return stack


def graph_tests():
    g= Graph()
    g.setRoot("Hash", '1.0.0')
    g.addEdge("Hash", "kUnit", '0.0.1', True)
    g.addEdge("Hash", "Strings", '0.0.2', True)
    g.addEdge("Strings", "errors", '0.0.3', False) 
    g.addEdge("Strings", "kUnit", '0.0.4', True)
    g.addEdge("kUnit", "Strings", '0.0.2', True)
    g.addEdge("errors", "registers", '0.0.1', False)
    g.addEdge("errors", "kUnit", '0.0.4', True)

    g.setRoot("ioFile", '1.0.0')
    g.addEdge("ioFile", "Strings", '0.0.2', True)


    # depth first search hierarchy
    dep = g.depthFirstSearch("Hash")
    print(dep)
    dep = g.depthFirstSearch("ioFile")
    print(dep)
    # Print dependency graph
    print(g.print_dependencies("Hash"))
    print(g.print_dependencies("ioFile"))


if __name__ == '__main__':
    sys.exit(main_guard(main, tool_name='rossum'))
