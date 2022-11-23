@echo off
python "%~dp0\kpush.py" %*
ftp -s:ftp.txt