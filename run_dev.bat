@echo off
cd /d %~dp0
call .venv\Scripts\activate

for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback' -and $_.IPAddress -notmatch '^169\.' } | Select-Object -First 1 -ExpandProperty IPAddress)"') do set LAPTOP_IP=%%i

echo.
echo Asset Tracking dev server
echo   Laptop:  http://127.0.0.1:8000
if defined LAPTOP_IP (
  echo   Phone test: http://%LAPTOP_IP%:8000/ping/
  echo   Phone login: http://%LAPTOP_IP%:8000/login/
  echo   Phone scan:  http://%LAPTOP_IP%:8000/scan/
) else (
  echo   Could not detect Wi-Fi IP. Run: ipconfig
)
echo.
echo Use http:// NOT https://
echo Phone must be on the SAME Wi-Fi as this laptop.
echo.

python manage.py runserver 0.0.0.0:8000
