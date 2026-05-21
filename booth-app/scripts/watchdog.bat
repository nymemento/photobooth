@echo off
title Memento Booth Watchdog
echo Starting Memento Booth watchdog...

set APP_PATH=%~dp0..\Memento Booth.exe
set RESTART_DELAY=5

:loop
echo [%date% %time%] Starting Memento Booth...
start /wait "" "%APP_PATH%"
echo [%date% %time%] App exited. Restarting in %RESTART_DELAY% seconds...
timeout /t %RESTART_DELAY% /nobreak >nul
goto loop
