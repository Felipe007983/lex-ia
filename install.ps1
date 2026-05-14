<#
.SYNOPSIS
Script de instalação completa para o Webscraper.
Instala: Python, Chrome, PostgreSQL, Ollama e configura o Banco de Dados.
#>

$ErrorActionPreference = "Stop"
$WorkingDir = $PSScriptRoot
$LogFile = Join-Path $WorkingDir "install_log.txt"

Function Write-Log {
    Param([string]$Message)
    $TimeStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$TimeStamp] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage
}

Write-Log "Iniciando processo de instalacao..."

# ==========================================
# 1. Instalar Gerenciador de Pacotes Winget (se necessario)
# ==========================================
try {
    $wingetVersion = winget --version
    Write-Log "Winget ja instalado: $wingetVersion"
} catch {
    Write-Log "Aviso: Winget nao encontrado. O Windows 10/11 Server mais recente ja deve possui-lo."
    Write-Log "Se a instalacao falhar, certifique-se de instalar o App Installer da Microsoft Store no servidor."
}

# ==========================================
# 2. Instalar Google Chrome
# ==========================================
Write-Log "Instalando Google Chrome..."
try {
    if (!(Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe") -and !(Test-Path "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")) {
        winget install --id Google.Chrome -e --accept-source-agreements --accept-package-agreements --silent
        Write-Log "Chrome instalado."
    } else {
        Write-Log "Chrome ja esta instalado."
    }
} catch {
    Write-Log "Erro ao tentar instalar o Chrome: $_"
}

# ==========================================
# 3. Instalar Python 3.9+ 
# ==========================================
Write-Log "Instalando Python..."
try {
    $pythonCheck = python --version 2>&1
    if ($pythonCheck -notmatch "Python 3") {
        # O -e garante instalar a versao exata se quisermos, mas o id Python.Python3.9 ja resolve. 
        # Vamos usar a ultima versao 3 disponivel que eh a padrao do winget.
        winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --silent
        Write-Log "Python instalado."
        
        # Recarregar variaveis de ambiente na sessao atual
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    } else {
        Write-Log "Python ja instalado: $pythonCheck"
    }
} catch {
    Write-Log "Erro ao instalar Python: $_"
}

# ==========================================
# 4. Instalar PostgreSQL 15
# ==========================================
Write-Log "Instalando PostgreSQL 15..."
$pgPassword = "password" # DEFINA A SENHA DO BANCO AQUI (deve bater com main.py)
$pgPort = "5432"

try {
    # Verificar se o servico postmaster ja existe
    $pgService = Get-Service -Name "postgresql-*" -ErrorAction Ignore
    if (!$pgService) {
        Write-Log "Baixando instalador do PostgreSQL 15..."
        $pgUrl = "https://get.enterprisedb.com/postgresql/postgresql-15.6-1-windows-x64.exe"
        $pgInstaller = Join-Path $WorkingDir "postgresql_installer.exe"
        Invoke-WebRequest -Uri $pgUrl -OutFile $pgInstaller
        
        Write-Log "Executando instalador silencioso..."
        $process = Start-Process -FilePath $pgInstaller -ArgumentList "--mode unattended --superpassword $pgPassword --serverport $pgPort" -Wait -PassThru
        
        if ($process.ExitCode -eq 0) {
            Write-Log "PostgreSQL instalado com sucesso."
        } else {
            Write-Log "Aviso: Codigo de retorno nao-zero na instalacao do PG: $($process.ExitCode)"
        }
        
        # Limpar instalador
        Remove-Item $pgInstaller -Force
        
        # Adicionar psql ao PATH user
        $pgPath = "C:\Program Files\PostgreSQL\15\bin"
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($currentPath -notmatch [regex]::Escape($pgPath)) {
            [Environment]::SetEnvironmentVariable("Path", $currentPath + ";" + $pgPath, "User")
            $env:Path += ";$pgPath"
        }
        
    } else {
        Write-Log "PostgreSQL ja esta instalado."
    }
} catch {
     Write-Log "Erro ao instalar PostgreSQL: $_"
}

# ==========================================
# 5. Criar Banco de Dados e Tabela (PostgreSQL)
# ==========================================
Write-Log "Configurando Banco de Dados..."
try {
    # Aguardar o servico do banco iniciar (caso recem instalado)
    Start-Sleep -Seconds 10
    
    $psqlPath = "C:\Program Files\PostgreSQL\15\bin\psql.exe"
    
    # Criar user 'user' e db 'web_bd' conforme main.py
    # Usando powershell env:PGPASSWORD para nao pedir senha interativamente
    $env:PGPASSWORD = $pgPassword
    
    # Cria o banco e usuario se nao existirem
    Write-Log "Criando usuario e DB..."
    & $psqlPath -U postgres -c "DO \`$body\`$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'user') THEN CREATE ROLE `"user`" LOGIN PASSWORD 'password'; END IF; END \`$body\`$;"
    & $psqlPath -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'web_bd'" | Select-String -Quiet "1" | Out-Null
    if ($?) {
        Write-Log "DB web_bd ja existe."
    } else {
        & $psqlPath -U postgres -c "CREATE DATABASE web_bd OWNER `"user`";"
        Write-Log "DB web_bd criado."
    }
    
    # Remove a var de ambiente
    Remove-Item Env:\PGPASSWORD
} catch {
    Write-Log "Erro ao configurar banco de dados: $_"
}

# ==========================================
# 6. Finalização e .env
# ==========================================
Write-Log "Configurando arquivo .env..."
if (!(Test-Path (Join-Path $WorkingDir ".env"))) {
    $envContent = "GEMINI_API_KEY=sua_chave_aqui`nOPENAI_API_KEY="
    Set-Content -Path (Join-Path $WorkingDir ".env") -Value $envContent
}

# ==========================================
# 7. Configurar Python Env. e Dependencias
# ==========================================
Write-Log "Configurando script Python..."
try {
    $envDir = Join-Path $WorkingDir "venv"
    if (!(Test-Path $envDir)) {
        Write-Log "Criando ambiente virtual (venv)..."
        python -m venv $envDir
    }
    
    $pipPath = Join-Path $envDir "Scripts\pip.exe"
    
    Write-Log "Atualizando PIP..."
    & $pipPath install --upgrade pip
    
    if (Test-Path (Join-Path $WorkingDir "requirements.txt")) {
        Write-Log "Instalando requirements..."
        & $pipPath install -r (Join-Path $WorkingDir "requirements.txt")
    } else {
        Write-Log "Arquivo requirements.txt nao encontrado! Criando um basico..."
        $reqs = @"
selenium
webdriver-manager
pdfplumber
psycopg2
pyotp
requests
openai
"@
        Set-Content -Path (Join-Path $WorkingDir "requirements.txt") -Value $reqs
        & $pipPath install -r (Join-Path $WorkingDir "requirements.txt")
    }
    Write-Log "Dependencias Python instaladas."
} catch {
    Write-Log "Erro ao configurar Python dev: $_"
}

Write-Log "Configuracao finalizada. Veja install_log.txt para detalhes."
Write-Log "Lembre-se de rodar a automacao ativando o venv: .\venv\Scripts\activate -> python main.py"
