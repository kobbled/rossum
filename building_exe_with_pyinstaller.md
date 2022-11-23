1. Copy `rossum` repo to a temporary location
2. Change `BUILD_STANDALONE` to `True` in `rossum.py`
```BUILD_STANDALONE = True```
3. Run `pyinstaller rossum.spec`
4. Run `pyinstaller kpush.spec`
5. copy the `rossum`, and `kpush` folder from `dist` into your release folder
6. copy `./exe/rossum.cmd`, and `./exe/kpush.cmd` into your release folder
7. Run `pyinstaller --onefile ./bin/kunit.py`
8. copy `kunit.exe` file from the `./dist` folder into your release folder.