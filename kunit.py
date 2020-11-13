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
import yaml


FILE_MANIFEST = '.man_log'


def main():
  #load file manifest
  with open(FILE_MANIFEST) as man:
    file_list = yaml.load(man, Loader=yaml.FullLoader)
  
  #get ip
  ip = file_list['ip']

  #get test programs if exists
  if 'test' not in file_list.keys():
    print("No test file found in manifest.")
    print("Exiting...")
    return

  test_files = ''
  sub_dict = file_list['test']

  test_files = ''
  for key in sub_dict.keys():
    if test_files:
      test_files = test_files + ','
    test_files = test_files + os.path.splitext(key)[0]
  
  os.system("curl http://" + ip + "/KAREL/KUnit?filenames=" + test_files)


if __name__ == '__main__':
  main()