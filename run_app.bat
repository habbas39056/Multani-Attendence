@echo off
title Multani Payroll & Biometric Attendance System
echo =========================================================================
echo       MULTANI PAYROLL & BIOMETRIC ATTENDANCE MANAGEMENT SYSTEM
echo =========================================================================
echo.
echo [1/2] Initializing Database & Seed Data...
python seed_data.py

echo [2/2] Launching Web Application on http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
python server.py
pause
