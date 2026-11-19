@echo off
rem rffilmlab.bat - double-click launcher (Windows).
rem Processes everything in the configured Negative folder once.
rffilmlab run
if errorlevel 1 echo Es gab ein Problem - siehe oben.
pause
