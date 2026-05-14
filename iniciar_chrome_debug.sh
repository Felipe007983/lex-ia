#!/bin/bash

echo "--- PREPARANDO AMBIENTE LINUX ---"
echo "Fechando instâncias existentes do Chrome..."
pkill -f chrome > /dev/null 2>&1
sleep 2

echo ""
echo "Iniciando Google Chrome com Monitor Virtual (Xvfb) na Porta 9222..."
USER_DATA_DIR="$HOME/selenium_chrome_profile"

# xvfb-run simula um monitor real para evitar detecção de bot e permitir que o Chrome abra
# -a (auto-servernum) evita conflitos se o Xvfb já estiver rodando
xvfb-run -a --server-args="-screen 0 1920x1080x24" \
google-chrome --no-sandbox \
              --remote-debugging-port=9222 \
              --user-data-dir="$USER_DATA_DIR" \
              --disable-setuid-sandbox \
              --disable-dev-shm-usage \
              --disable-gpu \
              --no-zygote \
              --headless=new \
              --window-size=1920,1080 > /dev/null 2>&1 &

echo ""
echo "========================================================"
echo "Chrome iniciado no Linux!"
echo "1. Faça o login no PJe na nova janela do Chrome."
echo "2. Após o login, volte ao terminal e rode: python3 main.py"
echo "========================================================"
