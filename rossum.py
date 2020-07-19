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
import datetime
import os, shutil
import sys
import json
import configparser
import fnmatch
from send2trash import send2trash

import collections

import logging
logger=None


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

ENV_PKG_PATH='ROSSUM_PKG_PATH'
ENV_DEFAULT_CORE_VERSION='ROSSUM_CORE_VERSION'
ENV_SERVER_IP='ROSSUM_SERVER_IP'

BUILD_FILE_NAME='build.ninja'
BUILD_FILE_TEMPLATE_NAME='build.ninja.em'

FTP_FILE_NAME='ftp.txt'
FTP_FILE_TEMPLATE_NAME='ftp.txt.em'

FANUC_SEARCH_PATH = [
    'C:\\Program Files\\Fanuc',
    'C:\\Program Files (x86)\\Fanuc',
    'D:\\Program Files\\Fanuc',
    'D:\\Program Files (x86)\\Fanuc',
]

KTRANS_BIN_NAME='ktrans.exe'
KTRANSW_BIN_NAME='ktransw.cmd'
MAKETP_BIN_NAME='maketp.exe'
TPP_BIN_NAME='tpp.bat'
XML_BIN_NAME='yamljson2xml.cmd'

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
    'tests '
    'version'
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
    'tests'         # list of (src, obj) tuples for tests
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
    parser.add_argument('-tp', '--compiletp', action='store_true', dest='compiletp',
        help='compile .tpp files into .tp files. If false will just interpret to .ls.')
    parser.add_argument('-t', '--include-tests', action='store_true', dest='inc_tests',
        help='include files for testing in build')
    parser.add_argument('--clean', action='store_true', dest='rossum_clean',
        help='clean all files out of build directory')
    parser.add_argument('src_dir', type=str, nargs='?', metavar='SRC',
        help="Main directory with packages to build")
    parser.add_argument('build_dir', type=str, nargs='?', metavar='BUILD',
        help="Directory for out-of-source builds (default: 'cwd')")
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
    tools = [KTRANS_BIN_NAME, KTRANSW_BIN_NAME, MAKETP_BIN_NAME, TPP_BIN_NAME, XML_BIN_NAME]
    # preset list of paths to search for paths
    search_locs = []
    search_locs.extend(KTRANS_SEARCH_PATH)
    # add environment path to search
    search_locs.extend([p for p in os.environ['Path'].split(os.pathsep) if len(p) > 0])
    #find build tools
    path_lst = find_tools(search_locs, tools, args)
    # put list into dictionary for file type build rule
    tool_paths = {
        'ktrans' : {'from_suffix' : '0', 'to_suffix' : '0', 'path' : path_lst[0]},
        'ktransw' : {'from_suffix' : KL_SUFFIX, 'interp_suffix' : PCODE_SUFFIX, 'comp_suffix' : PCODE_SUFFIX, 'path' : (args.ktransw or path_lst[1])},
        'yaml' : {'from_suffix' : YAML_SUFFIX, 'interp_suffix' : XML_SUFFIX,  'comp_suffix' : XML_SUFFIX, 'path' : path_lst[4]},
        'csv' : {'from_suffix' : CSV_SUFFIX, 'interp_suffix' : CSV_SUFFIX,  'comp_suffix' : CSV_SUFFIX, 'path' : 'C:\\Windows\\SysWOW64\\xcopy.exe'}
    }
    #for tpp decide if just interpreting, or compiling to tp
    if args.compiletp:
      tool_paths['maketp'] = {'from_suffix' : TP_SUFFIX, 'interp_suffix' : TPCODE_SUFFIX, 'comp_suffix' : TPCODE_SUFFIX, 'path' : path_lst[2]}
      tool_paths['tpp'] = {'from_suffix' : TPP_SUFFIX, 'interp_suffix' : TPP_INTERP_SUFFIX, 'comp_suffix' : TPCODE_SUFFIX, 'path' : path_lst[3], 'compile' : path_lst[2]}
    else:
      tool_paths['maketp'] = {'from_suffix' : TP_SUFFIX, 'interp_suffix' : TP_SUFFIX, 'comp_suffix' : TP_SUFFIX, 'path' : 'C:\\Windows\\SysWOW64\\xcopy.exe'}
      tool_paths['tpp'] = {'from_suffix' : TPP_SUFFIX, 'interp_suffix' : TPP_INTERP_SUFFIX, 'comp_suffix' : TPP_INTERP_SUFFIX, 'path' : path_lst[3]}

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
    template_ftp_path = os.path.join(template_dir, FTP_FILE_TEMPLATE_NAME) # for ftp
    ftp_file_path = os.path.join(build_dir, FTP_FILE_NAME)

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
        for p in other_pkg_dirs:
            logger.info('  {0}'.format(p))

        other_pkgs.extend(find_pkgs(other_pkg_dirs))
        other_pkgs = remove_duplicates(other_pkgs)
        logger.info("Found {0} package(s) in other location(s):".format(len(other_pkgs)))
        for pkg in other_pkgs:
            logger.info("  {0} (v{1})".format(pkg.manifest.name, pkg.manifest.version))


    # process all discovered pkgs
    all_pkgs = []
    all_pkgs.extend(src_space_pkgs)
    all_pkgs.extend(other_pkgs)
    all_pkgs = remove_duplicates(all_pkgs)

    # build out dependency trees
    # for all packages in src_space
    dependency_graph = create_dependency_graph(src_space_pkgs, all_pkgs)
    #log dependency trees to logger
    log_dep_tree(dependency_graph)
    #filter out additional packages that are not dependencies
    all_pkgs = filter_packages(all_pkgs, dependency_graph)

    # all discovered pkgs get used for dependency and include path resolution,
    resolve_includes(all_pkgs)

    # select to just build source or all related packages
    if args.buildall:
        build_pkgs = all_pkgs
    else: 
        build_pkgs = src_space_pkgs

    # but only the pkgs in the source space(s) get their objects build
    gen_obj_mappings(build_pkgs, tool_paths, args)


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

    ws = RossumWorkspace(build=bs_info, sources=sp_infos,
        robot_ini=robini_info, pkgs=build_pkgs)


    #if --keepgpp is set insert flag into ktrans call in
    # build.ninja.em so that temp builds in %TEMP% are kept
    keep_buildd = ''
    if args.keepgpp:
        keep_buildd = '-k'

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
        'compiletp'      : args.compiletp
    }
    # write out ninja template
    ninja_fl = open(build_file_path, 'w')
    ninja_interp = em.Interpreter(
            output=ninja_fl, globals=dict(globls),
            options={em.RAW_OPT : True, em.BUFFERED_OPT : True})
    # write out ftp push template
    ftp_fl = open(ftp_file_path, 'w')
    ftp_interp = em.Interpreter(
            output=ftp_fl, globals=dict(globls),
            options={em.RAW_OPT : True, em.BUFFERED_OPT : True})
    # load and process the template
    logger.debug("Processing template")
    ninja_interp.file(open(template_path))
    ftp_interp.file(open(template_ftp_path))
    # shutdown empy interpreters
    logger.debug("Shutting down empy")
    ninja_interp.shutdown()
    ftp_interp.shutdown()


    # done
    logger.info("Configuration successful, you may now run 'ninja' in the "
        "build directory.")





def find_files_recur(top_dir, pattern):
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


def is_rossum_pkg(mfest):
    return 'manver' in mfest


def parse_manifest(fpath):
    with open(fpath, 'r') as f:
        mfest = json.load(f)

    logger.debug("Loaded {0} from {1}".format(os.path.basename(fpath), os.path.dirname(fpath)))

    # make sure this is not a file that happens to be called 'package.json'
    if not is_rossum_pkg(mfest):
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
        tests=mfest['tests'] if 'tests' in mfest else [],
        includes=mfest['includes'] if 'includes' in mfest else [],
        depends=mfest['depends'] if 'depends' in mfest else [])


def find_pkgs(dirs):
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
                    tests=[])
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
    for i in l:
        if pred(i):
            return i
    return None


def create_dependency_graph(source_pkgs, all_pkgs):
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
        # Search through dependencies and add to dep graph and to
        # dependencies in RossumPackage collection
        add_dependency(pkg, visited, dep_graph, all_pkgs)
    
    return dep_graph

def add_dependency(src_package, visited, graph, pkgs):
    """
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
            if len(dep_pkg.manifest.depends) > 0:
                add_dependency(dep_pkg, visited, graph, pkgs)

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

def resolve_includes(pkgs):
    """ Gather include directories for all packages in 'pkgs'.
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Resolving includes for: {}".format(', '.join(pkg_names)))
    
    for pkg in pkgs:
        visited = set()
        logger.debug("  {}".format(pkg.manifest.name))
        inc_dirs = dedup(resolve_includes_for_pkg(pkg, visited))
        pkg.include_dirs.extend(inc_dirs)
        logger.debug("    added {} path(s)".format(len(inc_dirs)))


def resolve_includes_for_pkg(pkg, visited):
    """ Recursively gather include directories for a specific package.
    Makes all include directories absolute as well.
    """
    inc_dirs = []
    if pkg.manifest.name not in visited:
        # include dirs of current pkg first
        for inc_dir in pkg.manifest.includes:
            abs_inc = os.path.abspath(os.path.join(pkg.location, inc_dir))
            inc_dirs.append(abs_inc)
        visited.add(pkg.manifest.name)
        # then ask dependencies
        for dep_pkg in pkg.dependencies:
            inc_dirs.extend(resolve_includes_for_pkg(dep_pkg, visited))
    return inc_dirs


def gen_obj_mappings(pkgs, mappings, args):
    """ Updates the 'objects' member variable of each pkg with tuples of the
    form (path\to\a.kl, a.pc).
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Generating src to obj mappings for: {}".format(', '.join(pkg_names)))

    for pkg in pkgs:
        logger.debug("  {}".format(pkg.manifest.name))

        for src in pkg.manifest.source:
            src = src.replace('/', '\\')
            for (k, v) in mappings.items():
                if '.' + v['from_suffix'] in src:
                    obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['interp_suffix'])
                    build = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['comp_suffix'])
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj, build))

        if args.inc_tests:
          for src in pkg.manifest.tests:
              src = src.replace('/', '\\')
              for (k, v) in mappings.items():
                  if '.' + v['from_suffix'] in src:
                      obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['interp_suffix'])
                      build = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], v['comp_suffix'])
              logger.debug("    adding: {} -> {}".format(src, obj))
              pkg.objects.append((src, obj, build))


def find_fr_install_dir(search_locs, is64bit=False):
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
    for search_loc in search_locs:
        path = os.path.join(search_loc, tool)
        if os.path.exists(path):
            return path
    
    logger.warning("Can't find {} anywhere".format(tool))
    raise MissingKtransException("Can't find {} anywhere".format(tool))

def find_ktrans_support_dir(fr_base_dir, version_string):
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
    if "Tpp-env" not in config['WinOLPC_Util']:
        config['WinOLPC_Util']['Tpp-env'] = ''

    return robotiniInfo(
        robot=config['WinOLPC_Util']['Robot'],
        version=config['WinOLPC_Util']['Version'],
        base_path=config['WinOLPC_Util']['Base_Path'],
        version_path=config['WinOLPC_Util']['Path'],
        support=config['WinOLPC_Util']['Support'],
        output=config['WinOLPC_Util']['Output'],
        ftp=config['WinOLPC_Util']['Ftp'],
        env=config['WinOLPC_Util']['Tpp-env'])


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
