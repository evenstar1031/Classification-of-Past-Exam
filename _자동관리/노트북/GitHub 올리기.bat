@echo off
rem Uploads transcripts in this folder to GitHub.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0knuts-upload.ps1" %*
