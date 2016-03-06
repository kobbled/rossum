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

import collections

import logging
logger=None


ROSSUM_VERSION='0.0.5'


_OS_EX_USAGE=64
_OS_EX_DATAERR=65


ENV_PKG_PATH='KPKG_PATH'
MAKEFILE_NAME='Makefile'

KTRANS_NAME='ktrans.exe'
KTRANS_SEARCH_LOCS = [
    'C:/Program Files/Fanuc/WinOLPC/bin',
    'C:/Program Files (x86)/Fanuc/WinOLPC/bin'
]

MAKETP_NAME='maketp.exe'
ROBOT_INI_NAME='robot.ini'

MANIFEST_VERSION=1
MANIFEST_NAME='package.json'





class MissingKtransException(Exception):
    pass

class InvalidManifestException(Exception):
    pass




Manifest = collections.namedtuple('Manifest', 'name description version source includes depends')

class Pkg(object):
    def __init__(self, location, manifest):
        self.location = location
        self.manifest = manifest
        self.include_dirs = []









def main():
    import argparse

    # parse command line opts
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
        help='Be verbose')
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet',
        help='Be quiet (only warnings and errors will be shown)')
    #parser.add_argument('-b', '--create-build', action='store_true',
    #    dest='create_build', help="Create build dir if it doesn't exist")
    parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
        help='Do everything except writing to Makefile')
    parser.add_argument('--ktrans', type=str, dest='ktrans', metavar='PATH',
        help="Location of ktrans (default: auto-detect)")
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


    # always look in the source space
    pkg_dirs = [source_dir]
    # and any extra paths the user provided
    pkg_dirs.extend(extra_paths)
    # and finally look at the PKG_PATH if configured to do so
    if not args.no_env and ENV_PKG_PATH in os.environ:
        pkg_dirs.extend(os.environ[ENV_PKG_PATH].split(';'))


    # TODO: maybe generalise into 'find_tool(..)' or something (for maketp etc)

    # see if we need to find ktrans ourselves
    if not args.ktrans:
        logger.debug("Trying to auto-detect ktrans ..")

        ktrans_path = ''
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


    # notify user of config
    logger.info("ktrans: {0}".format(ktrans_path))
    logger.info("Build configuration:")
    logger.info("  source dir: {0}".format(source_dir))
    logger.info("  build dir : {0}".format(build_dir))
    logger.info("  robot.ini : {0}".format(robot_ini_loc))
    logger.info("Package search path (in order: src, args, env):")
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


    ############################################################################
    #
    # Generation
    #

    # finally: generate a Makefile for all discovered pkgs and the
    #          various bits of configuration data we collected
    mk_src = gen_makefile(pkg_dirs, pkgs, source_dir, build_dir, ktrans_path, robot_ini_loc)


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


CP:=busybox cp
MKDIR:=busybox mkdir
RM:=busybox rm
MV:=busybox mv

# set at rossum configuration time
SOURCE_DIR:={source_dir}
BUILD_DIR:={build_dir}
#INSTALL_DIR:=

CC:={ktrans_path}
SUPPORT_VER?=V7.70-1
ROBOT_INI:={robot_ini_loc}
CFLAGS:=/ver $(SUPPORT_VER) /config $(ROBOT_INI)
"""



def gen_mk_prefix(source_dir, build_dir, ktrans_path, robot_ini_loc):
    return mk_prefix.format(
        source_dir=source_dir,
        build_dir=build_dir,
        ktrans_path=ktrans_path,
        robot_ini_loc=robot_ini_loc)




mk_global_tgts="""
## top-level targets ###########################################################

.PHONY: all clean {phony_targets}

.SUFFIXES:
.SUFFIXES: .kl .pc

all: {proj_pcode_tgts}

clean: {proj_clean_tgts}
"""


def gen_mk_global_tgts(pkgs):
    phony_tgts = []
    pcode_tgts = []
    clean_tgts = []
    for pkg in pkgs:
        phony_tgts.extend([dep + '_INCLUDE_DIRS_check' for dep in pkg.manifest.depends])
        phony_tgts.append(pkg.manifest.name + '_INCLUDE_DIRS_check')
        pcode_tgts.append(pkg.manifest.name + '_pcode')
        clean_tgts.append(pkg.manifest.name + '_clean')

    phony_tgts.extend(pcode_tgts)
    phony_tgts.extend(clean_tgts)

    phony_tgts = list(set(phony_tgts))

    return mk_global_tgts.format(
        phony_targets=' '.join(phony_tgts),
        proj_pcode_tgts=' '.join(pcode_tgts),
        proj_clean_tgts=' '.join(clean_tgts))













### project specific variables

tmpl_vars = """{project}_DIR:={proj_loc}
{project}_OBJS:={proj_objs}
{project}_OBJS:=$(addprefix $(BUILD_DIR)/,$({project}_OBJS))
"""


def gen_mk_proj_vars(pkg):
    objs = []

    for src in pkg.manifest.source:
        fname, _ = os.path.splitext(os.path.basename(src))
        objs.append(fname + '.pc')

    return tmpl_vars.format(
        project=pkg.manifest.name,
        proj_loc=pkg.location,
        proj_objs=' '.join(objs))





### per source file target

tmpl_src_recipe = """$(BUILD_DIR)/{fname}.pc: $({project}_DIR)/src/{fname}.kl
\t$(SC)cmd /c 'cd $(BUILD_DIR) && $(CC) $({project}_DIR)\src\{fname}.kl $(CFLAGS) && echo.'
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




### include dir checks and copying

tmpl_inc_dir_chk = """{project}_INCLUDE_DIRS_check: {proj_inc_dirs} {dep_inc_dir_chk_tgts}
{inc_dir_cp_rcps}
"""

tmpl_inc_dir_copy = """$(BUILD_DIR)/{inc_dir}:
\t$(SC)$(CP) -R $({project}_DIR)/include/{inc_dir} $(BUILD_DIR)
"""


def gen_mk_proj_inc_dir_chk(pkg):
    # first gather own include dirs (may be multiple)
    proj_inc_dirs = ' '.join(['$(BUILD_DIR)/' + inc for inc in pkg.include_dirs])

    # instantiate one 'copy recipe' per exported include dir
    inc_dir_cp_rcps = ""
    for inc in pkg.include_dirs:
        inc_dir_cp_rcps += tmpl_inc_dir_copy.format(
            inc_dir=inc,
            project=pkg.manifest.name)

    # now those from its direct dependencies (make will solve the recursive deps)
    deps_inc_chk_tgts = ' '.join([dep + '_INCLUDE_DIRS_check' for dep in pkg.manifest.depends])

    # combine and return
    return tmpl_inc_dir_chk.format(
        project=pkg.manifest.name,
        proj_inc_dirs=proj_inc_dirs,
        dep_inc_dir_chk_tgts=deps_inc_chk_tgts,
        inc_dir_cp_rcps=inc_dir_cp_rcps)




### project specific targets

tmpl_proj_tgts = """{project}_clean:
\t$(SC)$(RM) -f $({project}_OBJS)
{tmpl_proj_clean_dirs}

{project}_pcode: {project}_INCLUDE_DIRS_check $({project}_OBJS) {dep_pcode_tgts}
"""

tmpl_proj_clean_dirs = "\t$(SC)$(RM) -rf $(BUILD_DIR)/{project}"



def gen_mk_proj_tgts(pkg):
    dep_pcode_tgts_str = ' '.join([dep + '_pcode' for dep in pkg.manifest.depends])
    tmpl_proj_clean_dirs_str = '\n'.join([tmpl_proj_clean_dirs.format(project=inc) for inc in pkg.include_dirs])

    return tmpl_proj_tgts.format(
        project=pkg.manifest.name,
        tmpl_proj_clean_dirs=tmpl_proj_clean_dirs_str,
        dep_pcode_tgts=dep_pcode_tgts_str)




def gen_makefile_section(pkg):
    mk_sec  = gen_mk_proj_vars(pkg) + '\n'
    mk_sec += gen_mk_proj_inc_dir_chk(pkg)
    mk_sec += gen_mk_proj_bin_tgts(pkg)
    mk_sec += gen_mk_proj_tgts(pkg)

    return mk_sec


def gen_makefile(pkg_dirs, pkgs, source_dir, build_dir, ktrans_path, robot_ini):

    res  = gen_mk_header(pkg_dirs) + '\n\n'
    res += gen_mk_prefix(source_dir, build_dir, ktrans_path, robot_ini)
    res += "\n\n"
    res += gen_mk_global_tgts(pkgs)
    res += "\n\n"

    for pkg in pkgs:
        res += "## {project} ###################\n\n".format(project=pkg.manifest.name)
        res += gen_makefile_section(pkg)
        res += "\n\n"
    return res




def find_files_recur(top_dir, pattern):
    import fnmatch
    matches = []
    for root, dirnames, filenames in os.walk(top_dir):
        for filename in fnmatch.filter(filenames, pattern):
            matches.append(os.path.join(root, filename))
    return matches


def is_rossum_pkg(mfest):
    return 'manver' in mfest


def parse_manifest(fpath):
    import json
    with open(fpath, 'r') as f:
        mfest = json.load(f)

    logger.debug("Loaded {0} in {1}".format(os.path.basename(fpath), os.path.dirname(fpath)))

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

    # find real include dirs
    for pkg in pkgs:
        logger.debug("Processing includes for {0}".format(pkg.manifest.name))

        for inc in pkg.manifest.includes:
            # see what's there
            loc = os.path.join(pkg.location, inc)
            logger.debug("Enumerating dirs in: {0}".format(loc))

            # only keep directories
            dirs = [d for d in os.listdir(loc) if os.path.isdir(os.path.join(loc, d))]
            pkg.include_dirs.extend(dirs)

            logger.debug("Added {0} include dir(s) for {1}".format(len(dirs), pkg.manifest.name))

    return pkgs




def find_ktrans():
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
        ktrans_path = os.path.join(ktrans_loc, KTRANS_NAME)
        if os.path.exists(ktrans_path):
            logger.debug("Found {0} in {1} via Windows registry".format(KTRANS_NAME, ktrans_loc))
            return ktrans_path

    except ImportError, ime:
        logger.debug("Couldn't access Windows registry, trying other methods")

    # no windows registry, try looking in the file system
    logger.warn("Can't find {0} using registry, switching to FS search".format(KTRANS_NAME))
    for ktrans_loc in KTRANS_SEARCH_LOCS:
        logger.debug("Looking in '{0}'".format(ktrans_loc))
        ktrans_path = os.path.join(ktrans_loc, KTRANS_NAME)
        if os.path.exists(ktrans_path):
            logger.debug("Found {0} in '{1}' in the FS".format(KTRANS_NAME, ktrans_loc))
            return ktrans_path

    logger.warn("Exhausted all methods to find {0}".format(KTRANS_NAME))

    # couldn't find it
    raise MissingKtransException("Can't find {0} anywhere".format(KTRANS_NAME))







if __name__ == '__main__':
    main()
