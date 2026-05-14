#!/bin/bash

echo "--- PREPARANDO AMBIENTE LINUX ---"
echo "Fechando instâncias existentes do Chrome..."
pkill -f chrome > /dev/null 2>&1
sleep 2

echo ""
echo "Iniciando Google Chrome em modo de depuração (Porta 9222)..."
USER_DATA_DIR="$HOME/selenium_chrome_profile"
google-chrome --remote-debugging-port=9222 --user-data-dir="$USER_DATA_DIR" > /dev/null 2>&1 &

echo ""
echo "========================================================"
echo "Chrome iniciado no Linux!"
echo "1. Faça o login no PJe na nova janela do Chrome."
echo "2. Após o login, volte ao terminal e rode: python3 main.py"
echo "========================================================"
