@echo off
rem Drag lecture files (mp4/mp3/m4a/wav) onto this file.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0knuts-transcribe.ps1" %*
