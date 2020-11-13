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

FILE_MANIFEST = '.man_log'

FTP_FILE_NAME='ftp.txt'
FTP_FILE_TEMPLATE_NAME='ftp.txt.em'

DATA_TYPES = ('karel', 'src', 'test', 'tp', 'test_tp', 
              'forms', 'test_forms', 'data', 'test_data')

karelext = ['.pc']
tpext = ['.ls', '.tp']
formsext = ['.tx']
dataext = ['.xml', '.csv']

def main():
  #initialize sorted manifest
  ftpManifest = {
    'karel' : set(),
    'karelvr' : set(),
    'tp' : set(),
    'forms' : set(),
    'data' : set()
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
        sortfile(key, parent, ftpManifest)
        if ext in formsext:
          for child in children:
            ftpManifest['forms'].add(child)
        else:
          for child in children:
            sortchild(child, ftpManifest)
  
  # write out ftp push template
  ftp_fl = open(ftp_file_path, 'w')
  globls = {
      'ip' : file_list['ip'],
      'files'   : ftpManifest
  }
  ftp_interp = em.Interpreter(
          output=ftp_fl, globals=dict(globls),
          options={em.RAW_OPT : True, em.BUFFERED_OPT : True})
  ftp_interp.file(open(template_ftp_path))
  ftp_interp.shutdown()


def sortfile(typ, fl, manifest):
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