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
from send2trash import send2trash

import collections

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
MANIFEST_NAME='package.json'

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
    parser.add_argument('-p', '--pkg-dir', action='append', type=str,
        dest='extra_paths', metavar='PATH', default=[],
        help='Additional paths to search for packages (multiple allowed). '
        'Note: this essentially extends the source space.')
    parser.add_argument('-r', '--robot-ini', type=str, dest='robot_ini',
        metavar='INI', default=ROBOT_INI_NAME,
        help="Location of {0} (default: source dir)".format(ROBOT_INI_NAME))
    parser.add_argument('-w', '--overwrite', action='store_true', dest='overwrite',
        help='Overwrite any build file that may exist in the build dir')
    parser.add_argument('--ftp', action='store_true', dest='server_ip',
        default= os.environ.get(ENV_SERVER_IP),
        help='send to ip address specified.'
        'This will override env variable, {0}.'.format(ENV_SERVER_IP))
    parser.add_argument('-o', '--override', action='store_true', dest='override_ini',
        help='override robot.ini file directories with specified paths')
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
    parser.add_argument('-l', '--build-tp', action='store_true', dest='build_ls',
        help='include ls files for building')
    parser.add_argument('--clean', action='store_true', dest='rossum_clean',
        help='clean all files out of build directory')
    parser.add_argument('src_dir', type=str, nargs='?', metavar='SRC',
        help="Main directory with packages to build")
    parser.add_argument('build_dir', type=str, nargs='?', metavar='BUILD',
        help="Directory for out-of-source builds (default: 'cwd')")

    # support forward-slash arg notation for include dirs
    for i in range(1, len(sys.argv)):
        if sys.argv[i].startswith('/D'):
            sys.argv[i] = sys.argv[i].replace('/D', '-D', 1)
    args = parser.parse_args()



    ############################################################################
    #
    # Validation
    #


    # build dir is either CWD or user specified it
    build_dir   = os.path.abspath(args.build_dir or os.getcwd())
    #clean out files
    # (ref): https://stackoverflow.com/questions/185936/how-to-delete-the-contents-of-a-folder
    if args.rossum_clean:
      # make sure folder has build.ninja file or do not delete
      file_list = os.listdir(build_dir)
      if not any('build.ninja' in s for s in file_list):
        print('Refuse deletion of folder contents. Folder must have a build.ninja file')
        sys.exit(1)

      for filename in os.listdir(build_dir):
        file_path = os.path.join(build_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                send2trash(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))
      
      sys.exit(1)

    
    #source directory needs to be specified
    if not args.src_dir:
      raise RuntimeError("Source directory must be specified.")
    source_dir  = os.path.abspath(args.src_dir)
    extra_paths = [os.path.abspath(p) for p in args.extra_paths]


    # configure the logger
    FMT='%(levelname)-8s | %(message)s'
    logging.basicConfig(format=FMT, level=logging.INFO)
    global logger
    logger = logging.getLogger('rossum')
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    if args.quiet:
        logger.setLevel(logging.WARNING)

    logger.info("This is rossum v{0}".format(ROSSUM_VERSION))


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
    src_space_pkgs = find_pkgs(src_space_dirs)
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

        other_pkgs.extend(find_pkgs(other_pkg_dirs))
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
        logger.info("Requested dry-run, not saving build file")
        sys.exit(0)


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

    # update struct if not using robot.ini presets
    if args.override_ini:
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

    # don't overwrite existing files, unless instructed to do so
    if (not args.overwrite) and os.path.exists(build_file_path):
        logger.fatal("Existing {0} detected and '--overwrite' not specified. "
            "Aborting".format(BUILD_FILE_NAME))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

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
    man_list = [(obj[2], obj[3]) for pkg in ws.pkgs for obj in pkg.objects]
    write_manifest(FILE_MANIFEST, man_list, robini_info.ftp)


    # done
    logger.info("Configuration successful, you may now run 'ninja' in the "
        "build directory.")





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


def parse_manifest(fpath):
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
        source=mfest['source'] if 'source' in mfest else [],
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


def find_pkgs(dirs):
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
            manifest = parse_manifest(manifest_file_path)
            pkg = RossumPackage(
                    dependencies=[],
                    include_dirs=[],
                    location=os.path.dirname(manifest_file_path),
                    manifest=manifest,
                    objects=[],
                    tests=[],
                    macros=[])
            pkgs.append(pkg)
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
    for pkg in pkgs:
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
            f_name = pkg.location + '\\' + include
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
          program += "%include tpe.klh\n"
        
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
          program += '\tout_grp = tpe__get_int_arg({})\n'.format(i)
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
                    obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['interp_suffix'])
                    build = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['comp_suffix'])
                    if v['type'] == 'karel':
                      typ = 'src'
                    else:
                      typ = v['type']
                    # check if tpp file is in package
                    if k == 'tpp':
                      args.hastpp = True
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj, build, typ))

        # add interfaces to mappings
        if (args.build_interface) and any(pkg.manifest.name in x.name for x in dep_graph.root):
          for src in pkg.manifest.interface_files:
            src = src.replace('/', '\\')
            for (k, v) in mappings.items():
                if '.' + v['from_suffix'] in src:
                    obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['interp_suffix'])
                    build = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['comp_suffix'])
                    typ = 'interface'
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj, build, typ))

        # add tests to mappings
        if (args.inc_tests) and any(pkg.manifest.name in x.name for x in dep_graph.root):
          for src in pkg.manifest.tests:
              src = src.replace('/', '\\')
              for (k, v) in mappings.items():
                  if '.' + v['from_suffix'] in src:
                      obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['interp_suffix'])
                      build = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['comp_suffix'])
                      if v['type'] == 'karel':
                        typ = 'test'
                      else:
                        typ = 'test_' + v['type']
                      # check if tpp file is in package
                      if k == 'tpp':
                        args.hastpp = True
              logger.debug("    adding: {} -> {}".format(src, obj))
              pkg.objects.append((src, obj, build, typ))


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
        logger.warning("No {} in CWD, and no alternative provided, trying "
            "source space".format(ROBOT_INI_NAME))

        robot_ini_loc = os.path.join(source_dir, ROBOT_INI_NAME)
        logger.debug("Checking: {}".format(robot_ini_loc))
        if os.path.exists(robot_ini_loc):
            logger.info("Found {} in source space".format(ROBOT_INI_NAME))
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
                logger.warning("Found {} contains potentially conflicting ktrans "
                    "settings!".format(ROBOT_INI_NAME))
    
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

    file_list = dict()

    #load in manifest if it exists
    if os.path.exists(manifest):
      with open(manifest) as man:
        file_list = yaml.load(man, Loader=yaml.FullLoader)

    #save ip address
    file_list['ip'] = ipAddress

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
    main()
