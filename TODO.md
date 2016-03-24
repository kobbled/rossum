# TODO


  1. add (unit-)tests
  1. refactor into proper module(s)
  1. use empy for templates (but it's not in the Python Standard Library)
  1. add checks for Makefile dependencies: either on the path, or in the cwd:
    - `make.exe`
    - `busybox.exe`
    - `maketp.exe`
  1. add some sort of deployment target (ftp to controller)
  1. maybe make distinction between 'run depends' and 'build depends'?
    - run deps   : needed on controller at runtime
    - build depds: needed on build machine at compile time (for headers)
     we could include run deps in deploy target, but don't need to build them
  1. relocatable makefiles?
  1. package manifest verification?
  1. source file globbing?
  1. see if yaml makes more sense for package manifests
