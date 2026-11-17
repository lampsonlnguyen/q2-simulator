@echo off
call "%~dp0emulation\run-emulator.bat" %*
exit /b %errorlevel%
