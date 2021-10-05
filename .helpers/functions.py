def parse_manifest(fpath):
  """Convert a package.json file into a RossumManifest struct
  """
  return

def find_pkgs(dirs):
  """find packages in package path directories, and parse package.json files 
    into RossumPackage structs.
  """
  return

def remove_duplicates(pkgs):
  """create a seperate set with unique package names.
      input list must be the format of the collection
      RossumPackage.
  """
  return

def find_in_list(l, pred):
  """lamba function for finding item in a list
  """
  return

def create_dependency_graph(source_pkgs, all_pkgs, args):
  """
  Creates dependency graph for build
  Maps dependency pkg names to RossumPackage instances
  """
  return

def add_dependency(src_package, dep_list, visited, args, graph, pkgs):
  """build out dependency tree, traversing dependencies in the parent node.
  """
  return

def log_dep_tree(graph):
  """write depedency trees from source packages
      to debug logger
  """
  return

def filter_packages(pkgs, graph):
  """filter out packages in RossumPackage that
      are not in the dependency tree
  """
  return

def dedup(seq):
  """ Remove duplicates from a sequence, but:

    1. don't change element order
    2. keep the last occurence of each element instead of the first

  Example:
      a = [1, 2, 1, 3, 4, 1, 2, 6, 2]
      b = dedup(a)

  b is now: [3 4 1 6 2]
  """
  return

def resolve_includes(pkgs):
  """ Gather include directories for all packages in 'pkgs'.
  """
  return

def resolve_includes_for_pkg(pkg, visited):
  """ Recursively gather include directories for a specific package.
  Makes all include directories absolute as well.
  """
  return

def resolve_macros(pkgs, args):
  '''determine any user defined macros to pass to ktransw
  '''
  return

def get_interfaces(pkgs):
  """Get all of the TP interfaces specified in package.json, and store them
  as TPInterfaces collections.
  """
  return

def create_interfaces(interfaces):
  """Generates Karel program for the specified interface in package.json.
  example:
  ```
  PROGRAM mth_abs
    %NOBUSYLAMP
    %NOLOCKGROUP

    VAR
      out_reg : INTEGER
      val : REAL
    %from tpe.klh %import get_int_arg,get_real_arg
    %from registers.klh %import set_real
    %from math.builtins.klh %import abs

    BEGIN
      val = tpe__get_real_arg(1)
      out_reg = tpe__get_int_arg(2)
      registers__set_real(out_reg, math__abs(val))
    END mth_abs
  ```
  """
  return

def gen_obj_mappings(pkgs, mappings, args, dep_graph):
    """ Updates the 'objects' member variable of each pkg with tuples of the
    form (path\to\a.kl, a.pc).
    """
    return 

def find_fr_install_dir(search_locs, is64bit=False):
  """Find install directory of roboguide looking through registry keys
  """
  return

def find_program(tool, search_locs):
  """Helper function for `find_tools` to help find tool programs.
  """
  return

def find_ktrans_support_dir(fr_base_dir, version_string):
  """Find support files directory of specified core version 
  """
  return

def find_tools(search_locs, tools, args):
  """Find the locations of the tools specified in macros:
  tools = [KTRANS_BIN_NAME, KTRANSW_BIN_NAME, MAKETP_BIN_NAME, TPP_BIN_NAME, XML_BIN_NAME, KCDICT_BIN_NAME]
  """
  return

def find_robotini(source_dir, args):
  """
    check we can find a usable robot.ini somewhere.
    strategy:
      - if user provided a location, use that
      - if not, try CWD (default value of arg is relative to CWD)
      - if that doesn't work, try source space
  """
  return

def parse_robotini(fpath):
  """parse the robot.ini file into a struct, for use by rossum.
  """
  return

def write_manifest(manifest, files, ipAddress):
  """Write manifest file for kpush. Catagorize out source, test,
     tp+, ls, xml/csv files.
  """
  return
