#!/usr/bin/python
#
# Copyright (c) 2020, kobbled
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

import os
import em
import yaml
import collections
import fileinput
from ordered_set import OrderedSet

FILE_MANIFEST = '.man_log'

FTP_FILE_NAME='ftp.txt'
FTP_FILE_TEMPLATE_NAME='ftp.txt.em'

DATA_TYPES = ('karel', 'src', 'test', 'tp', 'test_tp', 
              'forms', 'test_forms', 'data', 'test_data', 'interface')

karelext = ['.pc']
tpext = ['.ls', '.tp']
formsext = ['.tx']
dataext = ['.xml', '.csv']

def main():
  import argparse

  description=("FTP wrapper tool for putting and getting files from "
        "the controller.")
  parser = argparse.ArgumentParser(prog='kpush', description=description
                    , formatter_class=argparse.RawDescriptionHelpFormatter)
  
  parser.add_argument('-i', '--exclude-interfaces', action='store_true', dest='exclude_interface',
        help='Be verbose')
  parser.add_argument('-d', '--delete', action='store_true', dest='only_delete',
        help='delete batch off of controller', default=False)
  args = parser.parse_args()

  #initialize sorted manifest
  ftpManifest = {
    'karel' : OrderedSet(),
    'karelvr' : OrderedSet(),
    'tp' : OrderedSet(),
    'forms' : OrderedSet(),
    'data' : OrderedSet(),
    'interface' : OrderedSet(),
  }
  #get build directory
  build_dir   = os.path.abspath(os.getcwd())
  #get ftp template directory
  template_ftp_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), FTP_FILE_TEMPLATE_NAME)
  #get ftp output directory
  ftp_file_path = os.path.join(build_dir, FTP_FILE_NAME)

  #load file manifest
  with open(FILE_MANIFEST) as man:
    file_list = yaml.load(man, Loader=yaml.FullLoader)

  #sort files from build manifest into containers for ftp template
  for key in file_list.keys():
    if (key in DATA_TYPES) and isinstance(file_list[key], dict):
      sub_dict = file_list[key]
      for parent, children in sub_dict.items():
        ext = os.path.splitext(parent)[-1]
        if ext in formsext:
          for child in children:
            ftpManifest['forms'].add(child)
        else:
          for child in children:
            sortchild(child, ftpManifest)
        #sort parent last for dependencies
        sortfile(key, parent, ftpManifest, args)
  
  # write out ftp push template
  with open(ftp_file_path, 'w') as ftp_fl:
    globls = {
        'ip' : file_list['ip'],
        'files'   : ftpManifest,
        'delete_only' : args.only_delete
    }
    ftp_interp = em.Interpreter(
            output=ftp_fl, globals=dict(globls),
            options={em.RAW_OPT : True, em.BUFFERED_OPT : True})
    ftp_interp.file(open(template_ftp_path))
    ftp_interp.shutdown()

  #remove all blank lines
  for line in fileinput.FileInput(ftp_file_path,inplace=1):
    if line.rstrip():
        print(line)


def sortfile(typ, fl, manifest, args):
  if typ in ('karel', 'src', 'test'):
    manifest['karel'].add(fl)
    #add variable file
    manifest['karelvr'].add(os.path.splitext(fl)[0] + '.vr')
  if typ in ('tp', 'test_tp'):
    manifest['tp'].add(fl)
  if typ in ('forms', 'test_forms'):
    manifest['forms'].add(fl)
  if typ in ('data', 'test_data'):
    manifest['data'].add(fl)
  if (not args.exclude_interface) and (typ in ('interface')):
    manifest['interface'].add(fl)

def sortchild(fl, manifest):
  ext = os.path.splitext(fl)[-1]

  if ext in karelext:
    manifest['karel'].add(fl)
    #add variable file
    manifest['karelvr'].add(os.path.splitext(fl)[0] + '.vr')
  if ext in tpext:
    manifest['tp'].add(fl)
  if ext in formsext:
    manifest['forms'].add(fl)
  if ext in dataext:
    manifest['data'].add(fl)

if __name__ == '__main__':
  main()