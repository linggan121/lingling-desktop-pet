@echo off
chcp 936 >nul
title 灵灵
cd /d "%~dp0"

set "PY="
rem 1) 本目录自带运行时
if exist "%~dp0python\pythonw.exe" set "PY=%~dp0python\pythonw.exe"
rem 2) 灵选宝安装目录
if not defined PY if exist "%LOCALAPPDATA%\灵选宝\python\pythonw.exe" set "PY=%LOCALAPPDATA%\灵选宝\python\pythonw.exe"
if not defined PY if exist "%LOCALAPPDATA%\选品助手\python\pythonw.exe" set "PY=%LOCALAPPDATA%\选品助手\python\pythonw.exe"
rem 3) 系统 python
if not defined PY for /f "delims=" %%i in ('where pythonw 2^>nul') do (set "PY=%%i" & goto :run)

:run
if not defined PY (
  echo 没有找到 Python。请先安装 Python，或把 python 运行目录复制到本目录下的 python\ 里。
  pause
  exit /b 1
)
start "" "%PY%" "%~dp0灵灵.pyw"
exit /b 0