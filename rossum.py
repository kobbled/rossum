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
import os
import sys
import json
import fnmatch

import collections

import logging
logger=None


ROSSUM_VERSION='0.1.7'


_OS_EX_USAGE=64
_OS_EX_DATAERR=65

KL_SUFFIX = 'kl'
PCODE_SUFFIX = 'pc'

ENV_PKG_PATH='ROSSUM_PKG_PATH'
ENV_DEFAULT_CORE_VERSION='ROSSUM_CORE_VERSION'
BUILD_FILE_NAME='build.ninja'
BUILD_FILE_TEMPLATE_NAME='build.ninja.em'

FANUC_SEARCH_PATH = [
    'C:/Program Files/Fanuc',
    'C:/Program Files (x86)/Fanuc',
    'D:/Program Files/Fanuc',
    'D:/Program Files (x86)/Fanuc',
]

KTRANS_BIN_NAME='ktrans.exe'
KTRANS_SEARCH_PATH = [
    'C:/Program Files/Fanuc/WinOLPC/bin',
    'C:/Program Files (x86)/Fanuc/WinOLPC/bin',
    'D:/Program Files/Fanuc/WinOLPC/bin',
    'D:/Program Files (x86)/Fanuc/WinOLPC/bin',
]

KTRANSW_BIN_NAME='ktransw.cmd'

MAKETP_NAME='maketp.exe'
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

KtransRobotIniInfo = collections.namedtuple('KtransRobotIniInfo', 'path')

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
    parser.add_argument('--ktrans', type=str, dest='ktrans', metavar='PATH',
        help="Location of ktrans (default: auto-detect)")
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
    parser.add_argument('src_dir', type=str, metavar='SRC',
        help="Main directory with packages to build")
    parser.add_argument('build_dir', type=str, nargs='?', metavar='BUILD',
        help="Directory for out-of-source builds (default: 'cwd')")
    args = parser.parse_args()


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



    ############################################################################
    #
    # Validation
    #

    # build dir is either CWD or user specified it
    build_dir   = os.path.abspath(args.build_dir or os.getcwd())
    source_dir  = os.path.abspath(args.src_dir)
    extra_paths = [os.path.abspath(p) for p in args.extra_paths]


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


    # check we can find a usable robot.ini somewhere.
    # strategy:
    #  - if user provided a location, use that
    #  - if not, try CWD (default value of arg is relative to CWD)
    #  - if that doesn't work, try source space

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


    # try to find base directory for FANUC tools
    try:
        fr_base_dir = find_fr_install_dir(search_locs=FANUC_SEARCH_PATH, is64bit=args.rg64)
        logger.info("Using {} as FANUC software base directory".format(fr_base_dir))
    except Exception as e:
        # not being able to find the Fanuc base dir is only a problem if:
        #  1) no ktrans.exe location provided
        #  2) no support dir location provided
        #
        # exit with a fatal error if we're missing either of those
        if (not args.ktrans or not args.support_dir):
            logger.fatal("Error trying to detect FANUC base-dir: {0}".format(e))
            logger.fatal("Please provide alternative locations for ktrans and support dir using")
            logger.fatal("the '--ktrans' and '--support' options.")
            logger.fatal("Cannot continue, aborting")
            sys.exit(_OS_EX_DATAERR)

        # if both of those have been provided we don't care and can continue
        logger.warning("Error trying to detect FANUC base-dir: {0}".format(e))
        logger.warning("Continuing with provided arguments")


    # TODO: maybe generalise into 'find_tool(..)' or something (for maketp etc)
    # see if we need to find ktrans ourselves
    ktrans_path = KTRANS_BIN_NAME
    if not args.ktrans:
        logger.debug("Trying to auto-detect ktrans location ..")

        try:
            search_locs = [fr_base_dir]
            search_locs.extend(KTRANS_SEARCH_PATH)
            ktrans_path = find_ktrans(kbin_name=KTRANS_BIN_NAME, search_locs=search_locs)
        except MissingKtransException as mke:
            logger.fatal("Aborting: {0}".format(mke))
            sys.exit(_OS_EX_DATAERR)
        except Exception as e:
            logger.fatal("Aborting: {0} (unhandled, please report)".format(e))
            sys.exit(_OS_EX_DATAERR)
    # or if user provided its location
    else:
        logger.debug("User provided ktrans location: {0}".format(args.ktrans))
        ktrans_path = os.path.abspath(args.ktrans)
        logger.debug("Setting ktrans path to: {0}".format(ktrans_path))

        # make sure it exists
        if not os.path.exists(ktrans_path):
            logger.fatal("Specified ktrans location ({0}) does not exist. "
                "Aborting.".format(ktrans_path))
            sys.exit(_OS_EX_DATAERR)

    logger.info("ktrans location: {0}".format(ktrans_path))


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


    # if user didn't supply an alternative, assume it's on the PATH
    ktransw_path = args.ktransw or KTRANSW_BIN_NAME
    logger.info("ktransw location: {0}".format(ktransw_path))


    # template and output file locations
    template_dir  = os.path.dirname(os.path.realpath(__file__))
    template_path = os.path.join(template_dir, BUILD_FILE_TEMPLATE_NAME)
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
        logger.info("Found {0} package(s) in other location(s):".format(len(other_pkgs)))
        for pkg in other_pkgs:
            logger.info("  {0} (v{1})".format(pkg.manifest.name, pkg.manifest.version))


    # process all discovered pkgs
    all_pkgs = []
    all_pkgs.extend(src_space_pkgs)
    all_pkgs.extend(other_pkgs)

    # make sure all their dependencies are present
    try:
        check_pkg_dependencies(all_pkgs)
    except Exception as e:
        logger.fatal("Error occured while checking packages: {}. Cannot "
            "continue".format(e))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # all discovered pkgs get used for dependency and include path resolution,
    resolve_dependencies(all_pkgs)
    resolve_includes(all_pkgs)

    # but only the pkgs in the source space(s) get their objects build
    gen_obj_mappings(src_space_pkgs)


    # notify user of config
    logger.info("Building {} package(s)".format(len(src_space_pkgs)))
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

    # populate dicts & lists needed by template
    ktrans = KtransInfo(path=ktrans_path, support=KtransSupportDirInfo(
        path=fr_support_dir,
        version_string=args.core_version))
    ktransw = KtransWInfo(path=ktransw_path)
    bs_info = RossumSpaceInfo(path=build_dir)
    sp_infos = [RossumSpaceInfo(path=p) for p in src_space_dirs]
    robini_info = KtransRobotIniInfo(path=robot_ini_loc)

    ws = RossumWorkspace(build=bs_info, sources=sp_infos,
        robot_ini=robini_info, pkgs=src_space_pkgs)



    # don't overwrite existing files, unless instructed to do so
    if (not args.overwrite) and os.path.exists(build_file_path):
        logger.fatal("Existing {0} detected and '--overwrite' not specified. "
            "Aborting".format(BUILD_FILE_NAME))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # write out template
    with open(build_file_path, 'w') as ofile:
        # setup the dict for empy
        globls = {
            'ws'             : ws,
            'ktrans'         : ktrans,
            'ktransw'        : ktransw,
            'rossum_version' : ROSSUM_VERSION,
            'tstamp'         : datetime.datetime.now().isoformat(),
        }

        interp = em.Interpreter(
            output=ofile, globals=globls,
            options={em.RAW_OPT : True, em.BUFFERED_OPT : True})

        # load and process the template
        logger.debug("Processing template")
        interp.file(open(template_path))
        logger.debug("Shutting down empy")
        interp.shutdown()


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


def check_pkg_dependencies(pkgs):
    """ make sure all dependencies are present
    """
    known_pkgs = [p.manifest.name for p in pkgs]
    logger.debug("Checking dependencies for: {}".format(', '.join(known_pkgs)))
    for pkg in pkgs:
        logger.debug("  {0} - deps: {1}".format(
            pkg.manifest.name,
            ', '.join(pkg.manifest.depends) if len(pkg.manifest.depends) else 'none'))

        missing = set(pkg.manifest.depends).difference(known_pkgs)
        if len(missing) > 0:
            raise MissingPkgDependency("Package {0} is missing dependencies: {1}"
                .format(pkg.manifest.name, ', '.join(missing)))
        else:
            logger.debug("    satisfied")


def find_in_list(l, pred):
    for i in l:
        if pred(i):
            return i
    return None

def resolve_dependencies(pkgs):
    """ Maps dependency pkg names to RossumPackage instances
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Resolving dependencies for: {}".format(', '.join(pkg_names)))
    for pkg in pkgs:
        logger.debug("  {}".format(pkg.manifest.name))

        for dep_pkg_name in pkg.manifest.depends:
            dep_pkg = find_in_list(pkgs, lambda p: p.manifest.name == dep_pkg_name)

            # this should not be possible, as pkg dependency relationships
            # should have been checked earlier, but you never know.
            if dep_pkg is None:
                raise MissingPkgDependency("Error finding internal pkg instance for '{}', "
                    "can't find it".format(dep_pkg_name))
            logger.debug("    {}: found".format(dep_pkg_name))
            pkg.dependencies.append(dep_pkg)


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
        # TODO: watch out for circular dependencies
        logger.debug("  {}".format(pkg.manifest.name))
        # TODO: is dedup ok here? Doesn't change order of include dirs, but
        #       does change the resulting include path
        inc_dirs = dedup(resolve_includes_for_pkg(pkg))
        pkg.include_dirs.extend(inc_dirs)
        logger.debug("    added {} path(s)".format(len(inc_dirs)))


def resolve_includes_for_pkg(pkg):
    """ Recursively gather include directories for a specific package.
    Makes all include directories absolute as well.
    """
    inc_dirs = []
    # include dirs of current pkg first
    for inc_dir in pkg.manifest.includes:
        abs_inc = os.path.abspath(os.path.join(pkg.location, inc_dir))
        inc_dirs.append(abs_inc)
    # then ask dependencies
    for dep_pkg in pkg.dependencies:
        inc_dirs.extend(resolve_includes_for_pkg(dep_pkg))
    return inc_dirs


def gen_obj_mappings(pkgs):
    """ Updates the 'objects' member variable of each pkg with tuples of the
    form (path\to\a.kl, a.pc).
    """
    pkg_names = [p.manifest.name for p in pkgs]
    logger.debug("Generating src to obj mappings for: {}".format(', '.join(pkg_names)))

    for pkg in pkgs:
        logger.debug("  {}".format(pkg.manifest.name))

        for src in pkg.manifest.source:
            src = src.replace('/', '\\')
            obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], PCODE_SUFFIX)
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj))

        # TODO: refactor this: make test rule generation optional
        for src in pkg.manifest.tests:
            src = src.replace('/', '\\')
            obj = '{}.{}'.format(os.path.splitext(os.path.basename(src))[0], PCODE_SUFFIX)
            logger.debug("    adding: {} -> {}".format(src, obj))
            pkg.objects.append((src, obj))


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


def find_ktrans(kbin_name, search_locs):
    # TODO: check PATH first

    for search_loc in search_locs:
        # see if it is in the default location
        ktrans_loc = os.path.join(search_loc, 'WinOLPC', 'bin')
        ktrans_path = os.path.join(ktrans_loc, kbin_name)

        logger.debug("Looking in {} ..".format(ktrans_loc))
        if os.path.exists(ktrans_path):
            logger.debug("Found {} in {}".format(kbin_name, ktrans_loc))
            return ktrans_path

    logger.warning("Can't find ktrans anywhere")
    raise MissingKtransException("Can't find {} anywhere".format(kbin_name))


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




if __name__ == '__main__':
    main()
