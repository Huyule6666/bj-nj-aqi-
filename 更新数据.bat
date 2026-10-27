@echo off
chcp 65001 >nul
cd /d "C:\Users\王垣贺\aqi-monitor"
set PYTHONUTF8=1

echo ================================================
echo   北京·南京空气质量 - 一键更新官方数据
echo ================================================
echo.

echo [1/3] 正在采集官方数据（cnemc 每日 AQI/浓度/实时）...
python collect.py
if errorlevel 1 goto :error

echo.
echo [2/3] 正在提交数据...
git add -A
git diff --cached --quiet
if not errorlevel 1 goto :nochange

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
git commit -m "data: 每日更新 %TODAY%"

echo.
echo [3/3] 正在推送到 GitHub...
netstat -ano | findstr ":65532" >nul 2>&1
if not errorlevel 1 (
    git config http.proxy http://127.0.0.1:65532
    git config https.proxy http://127.0.0.1:65532
    echo 检测到 VPN，走代理推送
) else (
    git config --unset http.proxy 2>nul
    git config --unset https.proxy 2>nul
    echo 未检测到 VPN，直连推送（若失败请开 VPN 后重试）
)
git push
if errorlevel 1 goto :pusherror

echo.
echo ================================================
echo   完成！线上网站已更新，Ctrl+F5 刷新查看
echo ================================================
goto :end

:nochange
echo.
echo 数据无变化，无需推送。
goto :end

:error
echo.
echo 采集出错，请把上方报错截图发给 Claude。
goto :end

:pusherror
echo.
echo 推送失败：请打开 VPN 后再点一次这个脚本。
goto :end

:end
echo.
pause
