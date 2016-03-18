#!/usr/bin/python
#
# Copyright (c) 2016, G.A. vd. Hoorn
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
#  - Python 2.7.x
#  - GNU Make 3.80+ (http://unxutils.sourceforge.net/)
#     only 'make.exe' from the 'UnxUpdates.zip' archive is needed
#  - busybox-w32 (http://frippery.org/busybox/)
#


#import em
import os
import sys
#import yaml
import json
import fnmatch

import collections

import logging
logger=None


ROSSUM_VERSION='0.0.10'


_OS_EX_USAGE=64
_OS_EX_DATAERR=65


ENV_PKG_PATH='KPKG_PATH'
MAKEFILE_NAME='Makefile'

KTRANS_BIN_NAME='ktrans.exe'
KTRANS_SEARCH_PATH = [
    'C:/Program Files/Fanuc/WinOLPC/bin',
    'C:/Program Files (x86)/Fanuc/WinOLPC/bin'
]

KTRANSW_BIN_NAME='ktransw.cmd'

MAKETP_NAME='maketp.exe'
ROBOT_INI_NAME='robot.ini'

MANIFEST_VERSION=1
MANIFEST_NAME='package.json'

DEFAULT_CORE_VERSION='V7.70-1'




class MissingKtransException(Exception):
    pass

class InvalidManifestException(Exception):
    pass




Manifest = collections.namedtuple('Manifest', 'name description version source tests includes depends')

class Pkg(object):
    def __init__(self, location, manifest):
        self.location = location
        self.manifest = manifest









def main():
    import argparse

    description=("Version {0}\n\nA cmake-like Makefile generator for Fanuc "
        "Robotics (Karel) projects\nthat supports out-of-source "
        "builds.".format(ROSSUM_VERSION))

    epilog=("Usage example:\n\n"
        "  mkdir  C:\\foo\\bar\\build\n"
        "  rossum C:\\foo\\bar\\src")

    parser = argparse.ArgumentParser(prog='rossum', description=description,
        epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
        help='Be verbose')
    parser.add_argument('-V', '--version', action='version',
        version='%(prog)s {0}'.format(ROSSUM_VERSION))
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet',
        help='Be quiet (only warnings and errors will be shown)')
    #parser.add_argument('-b', '--create-build', action='store_true',
    #    dest='create_build', help="Create build dir if it doesn't exist")
    parser.add_argument('-c', '--core', type=str, dest='core_version',
        metavar='ID', default=DEFAULT_CORE_VERSION, help="Version of "
        "the core files used when translating (default: %(default)s)")
    parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
        help='Do everything except writing to Makefile')
    parser.add_argument('--ktrans', type=str, dest='ktrans', metavar='PATH',
        help="Location of ktrans (default: auto-detect)")
    parser.add_argument('--ktransw', type=str, dest='ktransw', metavar='PATH',
        help="Location of ktransw (default: assume it's on the Windows PATH)")
    parser.add_argument('-n', '--no-env', action='store_true', dest='no_env',
        help='Do not search the {0}, even if it is set'.format(ENV_PKG_PATH))
    parser.add_argument('-p', '--pkg-dir', action='append', type=str,
        dest='extra_paths', metavar='PATH', default=[],
        help='Additional paths to search for packages (multiple allowed)')
    parser.add_argument('-r', '--robot-ini', type=str, dest='robot_ini',
        metavar='INI', default=ROBOT_INI_NAME,
        help="Location of {0} (default: source dir)".format(ROBOT_INI_NAME))
    parser.add_argument('-w', '--overwrite', action='store_true', dest='overwrite',
        help='Overwrite any Makefile that may exist in the build dir')
    parser.add_argument('src_dir', type=str, metavar='SRC',
        help="Main directory with packages to build")
    parser.add_argument('build_dir', type=str, nargs='?', metavar='BUILD',
        help="Directory for out-of-source builds (default: 'cwd')")
    args = parser.parse_args()


    # TODO: remove when / if we support creating build dirs
    args.create_build = False


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
    if os.path.exists(os.path.join(source_dir, MANIFEST_NAME)):
        logger.fatal("Found a package manifest ({0}) in the source "
            "dir ({1}). Cowerdly refusing to do in-source builds.".format(
                MANIFEST_NAME, source_dir))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # make sure that build dir exists
    if not os.path.exists(build_dir) and not args.create_build:
        logger.fatal("Directory '{0}' does not exist (and not creating it), "
            "aborting".format(build_dir))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)


    # for 'robot.ini', handle two cases:
    #  1) relative: look for that name in SOURCE DIR
    #  2) absolute: accept as-is
    if os.path.isabs(args.robot_ini):
        robot_ini_loc = args.robot_ini
        logger.debug("Using absolute path to (replacement) {0}: {1}".format(
            ROBOT_INI_NAME, robot_ini_loc))
    else:
        robot_ini_loc = os.path.join(source_dir, args.robot_ini)
        logger.debug("Expecting (replacement) {0} at: {1}".format(
            ROBOT_INI_NAME, robot_ini_loc))

    # check that it actually exists
    if not os.path.exists(robot_ini_loc):
        logger.fatal("The file '{0}' does not exist, and no alternative "
            "given, aborting.".format(robot_ini_loc))
        sys.exit(_OS_EX_DATAERR)


    # always look in the source space
    pkg_dirs = [source_dir]
    # and any extra paths the user provided
    pkg_dirs.extend(extra_paths)
    # and finally look at the PKG_PATH if configured to do so
    if not args.no_env and ENV_PKG_PATH in os.environ:
        pkg_dirs.extend(os.environ[ENV_PKG_PATH].split(';'))


    # TODO: maybe generalise into 'find_tool(..)' or something (for maketp etc)

    # see if we need to find ktrans ourselves
    ktrans_path = KTRANS_BIN_NAME
    if not args.ktrans:
        logger.debug("Trying to auto-detect ktrans location ..")

        try:
            ktrans_path = find_ktrans()
        except Exception, e:
            logger.fatal(e)
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

    # if user didn't supply an alternative, assume it's on the PATH
    ktransw_path = args.ktransw or KTRANSW_BIN_NAME

    # notify user of config
    logger.info("ktrans location: {0}".format(ktrans_path))
    logger.info("ktransw location: {0}".format(ktransw_path))
    logger.info("Setting default system core version to: {0}".format(args.core_version))
    logger.info("Build configuration:")
    logger.info("  source dir: {0}".format(source_dir))
    logger.info("  build dir : {0}".format(build_dir))
    logger.info("  robot.ini : {0}".format(robot_ini_loc))
    logger.info("Paths searched for packages (in order: src, args, env):")
    for p in pkg_dirs:
        logger.info('  {0}'.format(p))


    ############################################################################
    #
    # Discovery
    #

    # discover packages
    pkgs = find_pkgs(pkg_dirs)
    logger.info("Found {0} package(s):".format(len(pkgs)))
    for pkg in pkgs:
        logger.info("  {0}".format(pkg.manifest.name))


    # make sure all dependencies are present
    logger.debug("Checking dependencies")
    known_pkgs = [p.manifest.name for p in pkgs]
    for pkg in pkgs:
        logger.debug("  {0} - deps: {1}".format(
            pkg.manifest.name,
            ', '.join(pkg.manifest.depends) if len(pkg.manifest.depends) else 'none'))

        missing = set(pkg.manifest.depends).difference(known_pkgs)
        if len(missing) > 0:
            logger.fatal("Package {0} is missing dependencies: {1}. Cannot "
                "continue".format(pkg.manifest.name, ', '.join(missing)))
            # TODO: find appropriate exit code
            sys.exit(_OS_EX_DATAERR)
        else:
            logger.debug("    satisfied")



    ############################################################################
    #
    # Generation
    #

    # finally: generate a Makefile for all discovered pkgs and the
    #          various bits of configuration data we collected
    mk_src = gen_makefile(
        pkg_dirs=pkg_dirs,
        pkgs=pkgs,
        source_dir=source_dir,
        build_dir=build_dir,
        ktrans_path=ktrans_path,
        ktransw_path=ktransw_path,
        core_version=args.core_version,
        robot_ini=robot_ini_loc)

    if args.dry_run:
        logger.info("Requested dry-run, not saving Makefile")
        sys.exit(0)


    ############################################################################
    #
    # Finalisation
    #

    makefile_path = os.path.join(build_dir, MAKEFILE_NAME)
    logger.info("Writing generated rules to {0}".format(makefile_path))

    # don't overwrite existing files, unless instructed to do so
    if (not args.overwrite) and os.path.exists(makefile_path):
        logger.fatal("Existing {0} detected and '--overwrite' not specified. "
            "Aborting".format(MAKEFILE_NAME))
        # TODO: find appropriate exit code
        sys.exit(_OS_EX_DATAERR)

    # put it in the build dir
    with open(makefile_path, 'w') as mk_f:
        mk_f.write(mk_src)

    # done
    logger.info("Configuration successful, you may now run 'make' in the "
        "build directory.")









































mk_header="""################################################################################
#
# This file was auto-generated by rossum v{version} at {stamp}.
#
# Package directories searched at configuration time:
{pkg_dirs}
#
# Do not modify this file. Rather, regenerate it using rossum.
#
################################################################################
"""


def gen_mk_header(pkg_dirs):
    import datetime
    return mk_header.format(
        version=ROSSUM_VERSION,
        stamp=datetime.datetime.now().isoformat(),
        pkg_dirs='\n'.join(['#  - ' + pkg_dir for pkg_dir in pkg_dirs]))



mk_prefix="""
## build related variables and commands ########################################

# invoke as 'make VERBOSE=1' to get make to show recipe commands
ifeq "$(VERBOSE)" ""
\tVERBOSE=0
endif

ifeq "$(VERBOSE)" "0"
\tSC=@
endif

# set at rossum configuration time
SOURCE_DIR:={source_dir}
BUILD_DIR:={build_dir}
#INSTALL_DIR:=

CC:={ktransw_path} --ktrans={ktrans_path}
SUPPORT_VER?={core_version}
ROBOT_INI:={robot_ini_loc}
CFLAGS:=/ver $(SUPPORT_VER) /config $(ROBOT_INI)
"""



def gen_mk_prefix(source_dir, build_dir, ktrans_path, ktransw_path, core_version, robot_ini_loc):
    return mk_prefix.format(
        source_dir=source_dir,
        build_dir=build_dir,
        core_version=core_version,
        ktrans_path=ktrans_path,
        ktransw_path=ktransw_path,
        robot_ini_loc=robot_ini_loc)




mk_global_tgts="""
## top-level targets ###########################################################

.PHONY: all clean {phony_targets}

.SUFFIXES:
.SUFFIXES: .kl .pc

all: {proj_pcode_tgts}

tests: {proj_test_tgts}

clean: {proj_clean_tgts}
"""


def gen_mk_global_tgts(pkgs):
    phony_tgts = []
    pcode_tgts = []
    clean_tgts = []
    test_tgts  = []
    for pkg in pkgs:
        pcode_tgts.append(pkg.manifest.name + '_pcode')
        clean_tgts.append(pkg.manifest.name + '_clean')
        test_tgts.append(pkg.manifest.name + '_tests')

    phony_tgts.extend(pcode_tgts)
    phony_tgts.extend(clean_tgts)
    phony_tgts.extend(test_tgts)

    phony_tgts = list(set(phony_tgts))

    return mk_global_tgts.format(
        phony_targets=' '.join(phony_tgts),
        proj_pcode_tgts=' '.join(pcode_tgts),
        proj_test_tgts=' '.join(test_tgts),
        proj_clean_tgts=' '.join(clean_tgts))













### project specific variables

tmpl_vars = """{project}_DIR:={proj_loc}
{project}_DEPENDENCIES:={proj_dependencies}
{project}_INCLUDE_DIRECTORIES={proj_include_dirs}
{project}_INCLUDE_FLAGS=$(addprefix /I,$({project}_INCLUDE_DIRECTORIES))
{project}_OBJS:={proj_objs}
{project}_OBJS:=$(addprefix $(BUILD_DIR)/,$({project}_OBJS))
{project}_test_OBJS:={proj_test_objs}
{project}_test_OBJS:=$(addprefix $(BUILD_DIR)/,$({project}_test_OBJS))
"""

def gen_obj_names(srcs):
    objs = []
    for src in srcs:
        fname, _ = os.path.splitext(os.path.basename(src))
        objs.append(fname + '.pc')
    return objs


def gen_mk_proj_vars(pkg):
    # include dirs of package itself
    inc_dirs = ['$({0}_DIR)\\{1}'.format(pkg.manifest.name, inc) for inc in pkg.manifest.includes]
    # and it's immediate dependencies
    inc_dirs.extend(['$({0}_INCLUDE_DIRECTORIES)'.format(dep) for dep in pkg.manifest.depends])

    objs = gen_obj_names(pkg.manifest.source)
    tobjs = gen_obj_names(pkg.manifest.tests)

    return tmpl_vars.format(
        project=pkg.manifest.name,
        proj_dependencies=' '.join(pkg.manifest.depends),
        proj_loc=pkg.location,
        proj_include_dirs=' '.join(inc_dirs),
        proj_objs=' '.join(objs),
        proj_test_objs=' '.join(tobjs))





### per source file target

tmpl_src_recipe = """$(BUILD_DIR)/{fname}.pc: $({project}_DIR)/src/{fname}.kl
\t$(SC)echo Building Karel program :: $(notdir $@)
\t$(SC)$(CC) -q $({project}_INCLUDE_FLAGS) $< $@ $(CFLAGS)
"""

def gen_mk_proj_bin_tgts(pkg):
    res = ""
    for src in pkg.manifest.source:
        fname, _ = os.path.splitext(os.path.basename(src))

        res += tmpl_src_recipe.format(
            project=pkg.manifest.name,
            fname=fname)
        res += '\n'
    return res



### per test file target

tmpl_test_recipe = """$(BUILD_DIR)/{fname}.pc: $({project}_DIR)/src/{fname}.kl
\t$(SC)echo Building Karel test    :: $(notdir $@)
\t$(SC)$(CC) -q $({project}_INCLUDE_FLAGS) $< $@ $(CFLAGS)
"""

def gen_mk_proj_test_tgts(pkg):
    res = ""
    for src in pkg.manifest.tests:
        fname, _ = os.path.splitext(os.path.basename(src))

        res += tmpl_test_recipe.format(
            project=pkg.manifest.name,
            fname=fname)
        res += '\n'
    return res







### project specific targets

tmpl_proj_tgts = """{project}_clean:
\t$(SC)del /q /f $(subst /,\,$({project}_OBJS) $({project}_test_OBJS)) 2>nul

{project}_pcode: $(addsuffix _pcode,$({project}_DEPENDENCIES)) {project}_only

{project}_tests: $({project}_test_OBJS)

{project}_only: $({project}_OBJS)
"""


def gen_mk_proj_tgts(pkg):
    dep_pcode_tgts_str = ' '.join([dep + '_pcode' for dep in pkg.manifest.depends])

    return tmpl_proj_tgts.format(
        project=pkg.manifest.name,
        dep_pcode_tgts=dep_pcode_tgts_str)




def gen_makefile_section(pkg):
    mk_sec  = gen_mk_proj_vars(pkg) + '\n'
    mk_sec += gen_mk_proj_bin_tgts(pkg)
    mk_sec += gen_mk_proj_test_tgts(pkg)
    mk_sec += gen_mk_proj_tgts(pkg)

    return mk_sec


def gen_makefile(pkg_dirs, pkgs, source_dir, build_dir, ktrans_path, ktransw_path, core_version, robot_ini):

    res  = gen_mk_header(pkg_dirs) + '\n\n'
    res += gen_mk_prefix(source_dir, build_dir, ktrans_path, ktransw_path, core_version, robot_ini)
    res += "\n\n"
    res += gen_mk_global_tgts(pkgs)
    res += "\n\n"

    for pkg in pkgs:
        res += "## {project} ###################\n\n".format(project=pkg.manifest.name)
        res += gen_makefile_section(pkg)
        res += "\n\n"
    return res




def find_files_recur(top_dir, pattern):
    matches = []
    for root, dirnames, filenames in os.walk(top_dir):
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

    manifest = Manifest(
        name=mfest['project'],
        description=mfest['description'],
        version=mfest['version'],
        source=mfest['source'],
        tests=mfest['tests'] if 'tests' in mfest else [],
        includes=mfest['includes'],
        depends=mfest['depends'])
    return Pkg(location=os.path.dirname(fpath), manifest=manifest)


def find_pkgs(dirs):
    manifests = []
    for d in dirs:
        logger.debug("Searching in {0}".format(d))
        manifests_ = find_files_recur(d, MANIFEST_NAME)
        manifests.extend(manifests_)
        logger.debug("Found {0} manifests in {1}".format(len(manifests_), d))
    logger.debug("Found {0} manifests total".format(len(manifests)))

    pkgs = []
    for mfest in manifests:
        try:
            pkgs.append(parse_manifest(mfest))
        except Exception, e:
            mfest_loc = os.path.join(os.path.split(os.path.dirname(mfest))[1], os.path.basename(mfest))
            logger.warn("Error parsing manifest in {0}: {1}.".format(mfest_loc, e))

    return pkgs




def find_ktrans(kbin_name=KTRANS_BIN_NAME, search_locs=KTRANS_SEARCH_PATH):
    # TODO: check PATH first

    # try the windows registry
    try:
        import _winreg as wreg

        # find roboguide install dir
        fr_key = wreg.OpenKey(wreg.HKEY_LOCAL_MACHINE, r'Software\FANUC', 0, wreg.KEY_READ)
        fr_install_dir = wreg.QueryValueEx(fr_key, "InstallDir")[0]

        # get roboguide version
        rg_key = wreg.OpenKey(wreg.HKEY_LOCAL_MACHINE, r'Software\FANUC\ROBOGUIDE', 0, wreg.KEY_READ)
        rg_ver = wreg.QueryValueEx(rg_key, "Version")[0]

        logger.debug("Found Roboguide version: {0}".format(rg_ver))
        logger.debug("Roboguide installed in: {0}".format(fr_install_dir))

        # see if it is in the default location
        ktrans_loc = os.path.join(fr_install_dir, 'WinOLPC', 'bin')
        ktrans_path = os.path.join(ktrans_loc, kbin_name)
        if os.path.exists(ktrans_path):
            logger.debug("Found {0} in {1} via Windows registry".format(kbin_name, ktrans_loc))
            return ktrans_path

    except ImportError, ime:
        logger.debug("Couldn't access Windows registry, trying other methods")

    # no windows registry, try looking in the file system
    logger.warn("Can't find {0} using registry, switching to FS search".format(kbin_name))
    for ktrans_loc in search_locs:
        logger.debug("Looking in '{0}'".format(ktrans_loc))
        ktrans_path = os.path.join(ktrans_loc, kbin_name)
        if os.path.exists(ktrans_path):
            logger.debug("Found {0} in '{1}' in the FS".format(kbin_name, ktrans_loc))
            return ktrans_path

    logger.warn("Exhausted all methods to find {0}".format(kbin_name))

    # couldn't find it
    raise MissingKtransException("Can't find {0} anywhere".format(kbin_name))







if __name__ == '__main__':
    main()
