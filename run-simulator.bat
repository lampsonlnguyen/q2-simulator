@echo off
call "%~dp0emulation\run-simulator.bat" %*
exit /b %errorlevel%
