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

karelext = ['.pc']
tpext = ['.ls', '.tp']
formsext = ['.tx']
dataext = ['.xml', '.csv']

def main():
  #initialize sorted manifest
  ftpManifest = {
    'karel' : [],
    'karelvr' : [],
    'tp' : [],
    'forms' : [],
    'data' : []
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
  for parent, children in file_list.items():
    ext = os.path.splitext(parent)[-1]
    sortfile(parent, ftpManifest)
    if ext in formsext:
      for child in children:
        ftpManifest['forms'].append(child)
    else:
      for child in children:
        sortfile(child, ftpManifest)
  
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


def sortfile(fl, manifest):
  ext = os.path.splitext(fl)[-1]

  if ext in karelext:
    manifest['karel'].append(fl)
    #add variable file
    manifest['karelvr'].append(os.path.splitext(fl)[0] + '.vr')
  if ext in tpext:
    manifest['tp'].append(fl)
  if ext in formsext:
    manifest['forms'].append(fl)
  if ext in dataext:
    manifest['data'].append(fl)


if __name__ == '__main__':
  main()