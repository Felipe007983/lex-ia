@echo off
echo --- PREPARANDO AMBIENTE ---
echo Fechando TODAS as instancias do Chrome para liberar a porta...
taskkill /F /IM chrome.exe /T >nul 2>&1
echo Aguardando 2 segundos...
timeout /t 2 >nul

echo.
echo Iniciando Chrome em modo de depuracao (Porta 9222)...
echo Uma nova janela sera aberta.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium_chrome_profile"

echo.
echo ========================================================
echo Chrome iniciado!
echo 1. Faca o login no PJe nesta nova janela.
echo 2. NAO feche esta janela preta.
echo 3. Volte ao terminal do VSCode e rode "python main.py"
echo ========================================================
pause
