@echo off
echo ============================================
echo  Phone Detect - Task Scheduler Setup
echo ============================================
echo.
echo This will create a scheduled task that runs
echo automatically when Windows connects to WiFi.
echo.
echo Must be run as Administrator!
echo.

schtasks /Create /TN "PhoneDetectAutoStart" ^
  /TR "pythonw.exe C:\Users\User\Desktop\Dev\main.py" ^
  /SC ONEVENT ^
  /EC Microsoft-Windows-NetworkProfile/Operational ^
  /MO "*[System[EventID=10000]]" ^
  /RL HIGHEST ^
  /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Task created successfully!
    echo It will trigger whenever Windows connects to a network.
    echo.
    echo To remove later:  schtasks /Delete /TN "PhoneDetectAutoStart" /F
) else (
    echo.
    echo ERROR: Failed to create task. Make sure you're running as Administrator.
)

echo.
pause
