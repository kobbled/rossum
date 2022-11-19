@echo off
py -3 "%~dp0\kpush.py" %*
ftp -s:ftp.txt