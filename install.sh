#!/bin/bash

# Script de Instalação para Linux (Ubuntu/Debian)
# PROJETO_RENNER - Webscraper e Análise com Gemini

echo "==================================================="
echo "Iniciando Instalação no Linux..."
echo "==================================================="

# 1. Atualizar pacotes
sudo apt update

# 2. Instalar Google Chrome (se não existir)
if ! command -v google-chrome &> /dev/null
then
    echo "Instalando Google Chrome..."
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt install -y ./google-chrome-stable_current_amd64.deb
    rm google-chrome-stable_current_amd64.deb
else
    echo "Google Chrome já instalado."
fi

# 3. Instalar Python e Venv
echo "Instalando Python3 e Venv..."
sudo apt install -y python3 python3-venv python3-pip

# 4. Instalar PostgreSQL
echo "Instalando PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib libpq-dev

# 5. Configurar Banco de Dados
echo "Configurando Banco de Dados (PostgreSQL)..."
sudo -u postgres psql -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'user') THEN CREATE ROLE \"user\" LOGIN PASSWORD 'password'; END IF; END \$\$;"
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname = 'web_bd'" | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE web_bd OWNER \"user\";"

# 6. Configurar Ambiente Virtual Python
echo "Configurando ambiente virtual (venv)..."
python3 -m venv venv
source venv/bin/activate

echo "Instalando dependências Python..."
pip install --upgrade pip
pip install -r requirements.txt

# 7. Criar arquivo .env básico
if [ ! -f .env ]; then
    echo "Criando arquivo .env..."
    echo "GEMINI_API_KEY=sua_chave_aqui" > .env
    echo "OPENAI_API_KEY=" >> .env
fi

echo ""
echo "==================================================="
echo "Instalação concluída com sucesso!"
echo "Instruções:"
echo "1. Configure sua GEMINI_API_KEY no arquivo .env"
echo "2. Rode o script: ./iniciar_chrome_debug.sh"
echo "3. Ative o venv: source venv/bin/activate"
echo "4. Inicie a automação: python3 main.py"
echo "==================================================="
chmod +x iniciar_chrome_debug.sh
