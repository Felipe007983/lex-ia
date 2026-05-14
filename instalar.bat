@echo off
:: Script de Instalacao Completa - Webscraper e OCR
:: Deve ser executado como Administrador

echo ===================================================
echo Iniciando Instalacao Automatizada da Automacao...
echo Por favor, aguarde. Pode levar alguns minutos.
echo ===================================================

:: Verifica se esta rodando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador!
    echo Clique com o botao direito e selecione "Executar como Administrador".
    pause
    exit /b 1
)

:: Chama o script PowerShell que fara o trabalho pesado
PowerShell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0install.ps1'"

if %errorLevel% neq 0 (
    echo.
    echo [ERRO] Ocorreu um erro durante a instalacao. Verifique os logs acima.
    pause
    exit /b %errorLevel%
)

echo.
echo ===================================================
echo Instalacao concluida com sucesso!
echo ===================================================
pause
exit /b 0
