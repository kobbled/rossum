from util.parameters import *
import os

def parse_arguments():
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
  
  return parser.parse_args()


def init_logger(args):
  """Initialize logging tool for runtime and debug info. 
  Set display level with `args` 

  Args:
    args : argparse.ArgumentParser.parse_args
  """
  import logging

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

  return logger