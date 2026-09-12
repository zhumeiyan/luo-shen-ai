@echo off
chcp 65001 >nul 2>&1
title 洛神 AI — 本地启动

echo ══════════════════════════════════════
echo        洛神 AI — 本地启动
echo ══════════════════════════════════════
echo.

REM ─── 1. 检查 Python ──────────────────────────────────
echo [1/4] 检查 Python 环境...

where python >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=python
    goto :python_found
)

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=python3
    goto :python_found
)

echo [错误] 未检测到 Python！
echo.
echo 请先安装 Python 3.10 或更高版本：
echo   官网: https://www.python.org/downloads/
echo   安装时一定要勾选 "Add Python to PATH"
echo.
echo 安装完成后，重新双击此文件。
pause
exit /b 1

:python_found
for /f "tokens=*" %%v in ('%PYTHON% --version') do echo   [OK] 检测到: %%v
echo.

REM ─── 2. 安装依赖 ────────────────────────────────────
echo [2/4] 安装依赖...
%PYTHON% -m pip install --quiet requests
if %errorlevel% neq 0 (
    echo [警告] 安装依赖失败，尝试继续...
) else (
    echo   [OK] requests 已就绪
)
echo.

REM ─── 3. 检查 ZHIPU_API_KEY ───────────────────────────
echo [3/4] 检查 API Key...

if exist .env (
    for /f "tokens=1,* delims==" %%a in (.env) do (
        set "%%a=%%b"
    )
)

if "%ZHIPU_API_KEY%"=="" (
    echo   [提示] 未检测到 ZHIPU_API_KEY
    echo.
    echo 请输入你的智谱 API Key：
    echo （获取方式：访问 https://open.bigmodel.cn -^> 注册 -^> API Keys）
    set /p INPUT_KEY="^> "
    if "%INPUT_KEY%"=="" (
        echo [错误] API Key 不能为空！
        pause
        exit /b 1
    )
    echo ZHIPU_API_KEY=%INPUT_KEY%> .env
    set ZHIPU_API_KEY=%INPUT_KEY%
    echo   [OK] 已保存到 .env 文件（下次自动读取）
) else (
    echo   [OK] 已配置 API Key
)
echo.

REM ─── 4. 启动洛神 ──────────────────────────────────────
echo [4/4] 启动洛神...
echo.
echo   洛神正在启动...
echo   浏览器即将自动打开 http://localhost:7860
echo   按 Ctrl+C 停止
echo.

REM 启动后自动打开浏览器
start "" http://localhost:7860

REM 启动服务
%PYTHON% web_chat.py

pause
