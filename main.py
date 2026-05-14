import os
import time
import re
import glob
import csv
import requests
import platform
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
import pdfplumber
import psycopg2
from dotenv import load_dotenv

import openai
import pyotp
import json
import socket
from google import genai
from pydantic import BaseModel, Field
from typing import Optional

# Carrega variáveis de ambiente do arquivo .env se existir
load_dotenv()

# --- CONFIGURAÇÃO GEMINI ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- CONFIGURAÇÃO OPENAI (CHATGPT) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# ---------------------------

class ContractData(BaseModel):
    Nome: Optional[str] = Field(None, description="Nome completo do devedor/emitente")
    CPF_CNPJ: Optional[str] = Field(None, description="CPF ou CNPJ do devedor/emitente (apenas números)")
    Telefone: Optional[str] = Field(None, description="Telefone de contato do devedor (apenas números)")
    Email: Optional[str] = Field(None, description="Email de contato do devedor")
    Endereco: Optional[str] = Field(None, description="Endereço completo do devedor")
    Numero_Contrato: Optional[str] = Field(None, description="Número da Cédula ou Contrato")
    Data_Contrato: Optional[str] = Field(None, description="Data de emissão ou assinatura (DD/MM/AAAA)")
    Erro: Optional[str] = Field(None, description="Mensagem de erro ou observação")
def setup_driver():
    """Configura e retorna uma instância do WebDriver Chrome conectada a um navegador existente."""
    print("DEBUG: Configurando opções do Chrome...")
    options = webdriver.ChromeOptions()
    
    # Conectar ao Chrome já aberto na porta 9222
    print("DEBUG: Definindo endereço do debugger (127.0.0.1:9222)...")
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    print("DEBUG: Instalando/Verificando ChromeDriver (pode demorar)...")
    try:
        service = ChromeService(ChromeDriverManager().install())
        print("DEBUG: ChromeDriver obtido com sucesso.")
    except Exception as e:
        print(f"DEBUG: Erro ao obter ChromeDriver: {e}")
        raise e

    print("DEBUG: Inicializando WebDriver...")
    try:
        driver = webdriver.Chrome(service=service, options=options)
        print("DEBUG: WebDriver inicializado.")
        
        # OBRIGATÓRIO EM MODO DEBUG: Forçar o caminho de download via CDP
        # As prefs normais são ignoradas quando se conecta a um chrome existente.
        current_dir = os.getcwd()
        download_dir = os.path.join(current_dir, "downloads")
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            
        print(f"DEBUG: Configurando pasta de download via CDP para: {download_dir}")
        params = {
            "behavior": "allow",
            "downloadPath": download_dir
        }
        driver.execute_cdp_cmd("Page.setDownloadBehavior", params)
        
    except Exception as e:
        print(f"DEBUG: Erro ao inicializar WebDriver: {e}")
        raise e
        
    return driver

def handle_cnj_alert(driver):
    """Tenta aceitar o alerta da Resolução CNJ."""
    try:
        # Espera breve para ver se o alerta aparece
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        msg = alert.text
        print(f"ALERTA DETECTADO: {msg}")
        alert.accept()
        print("ALERTA ACEITO (OK).")
        time.sleep(1) # Espera o navegador processar o aceite
        return True
    except TimeoutException:
        # Não é erro, apenas não tinha alerta
        return False
    except Exception as e:
        print(f"Erro ao tentar fechar alerta: {e}")
        return False

def get_latest_pdf():
    """Retorna o caminho do arquivo PDF mais recente na pasta downloads."""
    download_dir = os.path.join(os.getcwd(), "downloads")
    files = glob.glob(os.path.join(download_dir, "*.pdf"))
    
    print(f"DEBUG: Procurando PDFs em: {download_dir}")
    print(f"DEBUG: Arquivos encontrados: {files}")
    
    if not files:
        return None
    return max(files, key=os.path.getctime)

def extract_relevant_segments(text, max_lines=50):
    """
    Filtra o texto para manter apenas linhas contendo palavras-chave relevantes.
    Reduz drasticamente o tamanho do prompt enviado ao LLM.
    """
    keywords = [
        "valor", "parcela", "entrada", "prazo", "multa", "acordo", 
        "nome", "cpf", "cnpj", "endereço", "contrato", "bancário",
        "devedor", "emitente", "cliente", "financiado", "cédula",
        "email", "e-mail", "mail", "telefone","E-mail","Telefones", "tel", "celular", "contato"
    ]
    
    lines = text.split("\n")
    relevant_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        line_lower = line.lower()
        
        if any(k in line_lower for k in keywords):
            # Adiciona a linha encontrada
            relevant_lines.append(line.strip())
            
            # Tenta adicionar as próximas 2 linhas (contexto) se existirem
            # Isso ajuda quando o valor está na linha de baixo (Ex: "Nome:\nFulano")
            for j in range(1, 3):
                if i + j < len(lines):
                    relevant_lines.append(lines[i+j].strip())
            
        i += 1
            
    # Retorna o texto reconstruído, limitando o número de linhas para evitar overflow
    # Aumentei o limite de linhas pois agora pegamos mais contexto
    return "\n".join(list(dict.fromkeys(relevant_lines))[:max_lines*2])

def extract_with_regex_fallback(text):
    """Fallback: Extrai dados usando Regex se a IA falhar ou não estiver configurada."""
    data = {}
    
    # Normaliza texto
    text = text.replace("\n", " ").strip()
    
    # Bloco Emitente
    emitente_block_match = re.search(r"(?:DADOS DO.*EMITENTE|EMITENTE)(.*?)(?:DADOS DO.*CREDOR|CREDORA|III|IV|$)", text, re.IGNORECASE | re.DOTALL)
    text_to_search = emitente_block_match.group(1) if emitente_block_match else text
    
    # Regex Patterns
    nome_match = re.search(r"NOME:\s*([A-Za-z\s]+?)(?:CNPJ|CPF|ENDEREÇO|$)", text_to_search, re.IGNORECASE)
    if nome_match: data["Nome"] = nome_match.group(1).strip()
    
    cpf_match = re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}", text_to_search)
    if cpf_match: 
        # Limpar pontuação
        raw_cpf = cpf_match.group(0)
        data["CPF_CNPJ"] = re.sub(r"\D", "", raw_cpf)
    
    end_match = re.search(r"ENDEREÇO:\s*(.+?)(?:ENDEREÇO ELETRÔNICO|DADOS|$)", text_to_search, re.IGNORECASE)
    if end_match: data["Endereco"] = end_match.group(1).strip()
    
    email_match = re.search(r"ENDEREÇO ELETRÔNICO:\s*(\S+@\S+)", text_to_search, re.IGNORECASE)
    if email_match: data["Email"] = email_match.group(1).strip()

    tel_match = re.search(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}", text_to_search)
    if tel_match: 
        raw_tel = tel_match.group(0)
        data["Telefone"] = re.sub(r"\D", "", raw_tel)
    
    contrato_match = re.search(r"Nº DA CÉDULA:\s*(\d+)", text, re.IGNORECASE)
    if contrato_match: data["Numero_Contrato"] = contrato_match.group(1).strip()

    data_match = re.search(r"\d{2}/\d{2}/\d{4}", text)
    if data_match: data["Data_Contrato"] = data_match.group(0)

    data["Erro"] = "Extraído via Regex (Fallback)"
    
    return data

def extract_with_openai_gpt(text):
    """Extrai dados usando OpenAI GPT-4o-mini (Mais barato e rápido)."""
    if not OPENAI_API_KEY:
        return None

    try:
        print("DEBUG: Iniciando extração com OpenAI (ChatGPT)...")
        client = openai.Client(api_key=OPENAI_API_KEY)
        
        prompt = f"""
        Analise o seguinte texto de um contrato bancário (Cédula de Crédito Bancário).
        Extraia APENAS os dados do EMITENTE (O Cliente/Devedor). Não pegue dados do Banco/Credor.
        
        Retorne APENAS um JSON com estas chaves exatas (sem markdown, sem ```json):
        {{
            "Nome": "Nome completo do emitente",
            "Telefone": "Telefone encontrado (se houver)",
            "Email": "Email encontrado (se houver)",
            "Endereco": "Endereço completo",
            "Contrato_PDF": "Número da Cédula ou Contrato"
        }}
        
        Se não encontrar algum campo, coloque "Não encontrado".
        
        TEXTO DO CONTRATO:
        {text[:30000]} 
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente especializado em extração de dados de contratos bancários."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        print("DEBUG: Sucesso na extração com OpenAI!")
        return data

    except Exception as e:
        print(f"DEBUG: Erro na extração com OpenAI: {e}")
        return None

    except Exception as e:
        print(f"Erro no processo de login: {e}")
        return False

def perform_login(driver, wait):
    """Realiza o login no PJe com as credenciais fornecidas."""
    try:
        print("--- INICIANDO LOGIN ---")
        
        # 1. Aguardar redirecionamento para SSO se necessário
        print("Verificando se estamos na tela de login...")
        time.sleep(5) # Espera o redirecionamento acontecer
        
        # Se já estiver logado (Titulo: Painel ou URL interna)
        if "login" not in driver.current_url and "sso" not in driver.current_url and ("Painel" in driver.title or "Processo" in driver.title):
             print("Parece que já estamos logados! (Título/URL indicam sucesso)")
             return True

        # 2. Tentar preencher credenciais
        print("Tentando localizar campos de CPF e Senha...")
        
        # Tenta lidar com iFrame do PJe legado (se houver)
        try:
            iframe = driver.find_element(By.ID, "ssoFrame")
            driver.switch_to.frame(iframe)
            print("Entrou no iframe de login.")
        except:
            pass # Segue para tentar no corpo principal (PJe Cloud/SSO atual)

        try:
            # Tenta encontrar o campo username (padrão Keycloak/SSO)
            cpf_input = wait.until(EC.visibility_of_element_located((By.ID, "username")))
            cpf_input.click()
            cpf_input.clear()
            # CPF formatado ou limpo? Geralmente limpo. O usuário pediu 101.823...
            # Vamos mandar limpo primeiro.
            cpf_input.send_keys("10182384683") 
            print("CPF preenchido.")
            
            pass_input = driver.find_element(By.ID, "password")
            pass_input.click()
            pass_input.clear()
            pass_input.send_keys("Llbb@0315")
            print("Senha preenchida.")
            
            # Clicar em Entrar
            # O ID pode ser 'btnEntrar' ou 'kc-login' ou similar
            try:
                btn_entrar = driver.find_element(By.ID, "btnEntrar")
                btn_entrar.click()
            except:
                # Tenta pelo type submit ou valor
                btn_entrar = driver.find_element(By.XPATH, "//input[@type='submit'] | //button[@type='submit'] | //input[@value='Entrar']")
                btn_entrar.click()
            
            print("Botão 'Entrar' clicado!")
            
        except TimeoutException:
            print("Não encontrei campos de login! Pode ser que já esteja logado ou a página mudou.")
            return False
            
        driver.switch_to.default_content()

        # 3. Preencher 2FA Automaticamente
        print("Aguardando tela de 2FA (OTP)... o sistema irá preencher o código automaticamente.")
        try:
            # Usa um tempo de espera maior especificamente para a tela de OTP carregar
            wait_otp = WebDriverWait(driver, 30)
            
            # Selector mais abrangente para pegar qualquer campo de OTP no Keycloak do PJe
            xpath_otp = "//input[contains(@id, 'otp') or contains(@name, 'otp') or @autocomplete='one-time-code']"
            
            try:
                otp_input = wait_otp.until(EC.element_to_be_clickable((By.XPATH, xpath_otp)))
            except TimeoutException:
                print("Não encontrou o campo de OTP pela busca padrão. Tentando fallback para qualquer input de texto visível...")
                otp_input = wait_otp.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text' or @type='number' or @type='tel']")))
            
            # Obtém a URI e gera o token
            uri = "otpauth://totp/PDPJ:10182384683?secret=NI3E642WJ5YXKZLQIVIXOMTXIZQW43LM&digits=6&algorithm=SHA1&issuer=PDPJ&period=30"
            totp = pyotp.parse_uri(uri)
            codigo_otp = totp.now()
            
            # Preenche o código
            otp_input.click()
            otp_input.clear()
            for digit in codigo_otp:
                otp_input.send_keys(digit)
                time.sleep(0.05) # Digitar suavemente para disparar eventos JS
            
            print(f"Código OTP ({codigo_otp}) gerado e preenchido com sucesso!")
            
            # Encontra e clica no botão de entrar do OTP
            try:
                btn_entrar_otp = driver.find_element(By.ID, "kc-login")
                btn_entrar_otp.click()
            except:
                try:
                    btn_entrar_otp = driver.find_element(By.XPATH, "//input[@type='submit' or @value='Entrar' or @name='login'] | //button[@type='submit']")
                    btn_entrar_otp.click()
                except:
                    # Se não achar o botão, tenta pressionar a tecla Enter no input
                    otp_input.send_keys(Keys.ENTER)
            
            print("Login com OTP submetido!")
            time.sleep(3)
        except Exception as e:
            print(f"Aviso: Falha ao preencher OTP automaticamente. O seletor pode estar incorreto na página atual. Erro: {e}")
            print("URL atual:", driver.current_url)
            
        # Loop de espera até o login mudar a URL ou título
        max_wait = 180 # 3 minutos
        start_wait = time.time()
        
        while time.time() - start_wait < max_wait:
            if "login" not in driver.current_url and "sso" not in driver.current_url:
                if "Painel" in driver.title or "Processo" in driver.title or "seam" in driver.current_url:
                    print("LOGIN DETECTADO COM SUCESSO! Continuado...")
                    return True
            time.sleep(2)
            
        print("Tempo limite de login excedido (3 minutos).")
        return False

    except Exception as e:
        print(f"Erro geral no login: {e}")
        return False

    except Exception as e:
        print(f"Erro no processo de login: {e}")
        return False


def extract_bv_data_rule_based(text):
    """
    Tenta extrair dados usando padrões específicos dos contratos BV Financeira (A1, A2, etc).
    Retorna um dicionário com dados ou None se não encontrar o padrão.
    """
    print("DEBUG: Tentando extração via regras (Padrão BV)...")
    data = {}
    
    # Padrões Regex Específicos do BV
    # A1 Nome/Razão Social: HELCIO ...
    match_nome = re.search(r"A1\s*Nome/Razão Social:\s*(.+?)(?:\s*A2|$)", text, re.IGNORECASE)
    if match_nome:
        data["Nome"] = match_nome.group(1).strip()
    
    # A2 CPF/CNPJ: 123...
    match_cpf = re.search(r"A2\s*CPF/CNPJ:\s*([\d\.\-/]+)", text, re.IGNORECASE)
    if match_cpf:
        data["CPF_CNPJ"] = re.sub(r"[^\d]", "", match_cpf.group(1))
        
    # A5 E-mail: ...
    match_email = re.search(r"A5\s*E-mail:\s*(.+?)(?:\s*A6|$)", text, re.IGNORECASE)
    if match_email:
        email = match_email.group(1).strip()
        # Validação básica para evitar lixo
        if "@" in email and len(email) < 100:
            data["Email"] = email
            
    # A6 Telefones: ...
    match_tel = re.search(r"A6\s*Telefones:\s*(.+?)(?:\s*A7|$)", text, re.IGNORECASE)
    if match_tel:
        data["Telefone"] = re.sub(r"[^\d]", "", match_tel.group(1))
        
    # Endereço (A4) - Geralmente multilinha, mais chato, mas tentamos
    # Procura 'Endereço:' até 'Bairro:'
    match_end = re.search(r"Endereço:\s*(.+?)\s*Bairro:", text, re.IGNORECASE | re.DOTALL)
    if match_end:
        data["Endereco"] = match_end.group(1).strip().replace("\n", " ")
        
    # Se achou pelo menos Nome e CPF, consideramos sucesso
    if data.get("Nome") and data.get("CPF_CNPJ"):
        print(f"DEBUG: Padrão BV detectado! Dados extraídos via Regras: {data}")
        # Preencher campos faltantes com None para manter consistencia
        required_fields = ["Telefone", "Email", "Endereco", "Numero_Contrato", "Data_Contrato"]
        for f in required_fields:
            if f not in data:
                data[f] = None
        data["Erro"] = None
        return data
        
    print("DEBUG: Padrão BV não detectado ou incompleto.")
    return None

def extract_generic_data_rule_based(text):
    """
    Tenta extrair dados usando padrões Genéricos (Nome:, CPF:, etc) para qualquer banco.
    Funciona como um 'Detetive Universal' antes de tentar a IA.
    """
    print("DEBUG: Tentando extração via regras GENÉRICAS...")
    data = {}
    
    # Normalizar texto para facilitar regex (remover quebras de linha excessivas)
    clean_text = re.sub(r'\s+', ' ', text)
    
    # 1. NOME
    # Busca por: "Nome:", "Devedor:", "Emitente:", "Cliente:", "Mutuário:"
    # Pega tudo até encontrar um CPF, CNPJ, RG, Endereço ou fim de linha
    match_nome = re.search(r"(?:Nome|Razão Social|Devedor|Emitente|Cliente|Mutuário|Financiado)\s*[:\-\s]\s*([A-Z\s\.]+?)(?:\s*CPF|\s*CNPJ|\s*RG|\s*Endereço|\s*Carteira|$)", clean_text, re.IGNORECASE)
    if match_nome:
        candidate_name = match_nome.group(1).strip()
        # Filtro básico: Nome deve ter pelo menos 2 palavras e não ser "do" "da" etc
        if len(candidate_name.split()) >= 2 and len(candidate_name) < 100:
             data["Nome"] = candidate_name

    # 2. CPF / CNPJ
    # Busca estrita de CPF (11 digitos) ou CNPJ (14 digitos)
    match_cpf = re.search(r"(?:CPF|CNPJ|Inscrição).*?(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", clean_text, re.IGNORECASE)
    if match_cpf:
         data["CPF_CNPJ"] = re.sub(r"[^\d]", "", match_cpf.group(1))

    # 3. EMAIL
    # Busca qualquer coisa que pareça um email
    match_email = re.search(r"(?:E-mail|Email|Correio Eletrônico).*?(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)", clean_text, re.IGNORECASE)
    if match_email:
        data["Email"] = match_email.group(1).strip()
        
    # 4. TELEFONE
    # Busca padrões (XX) XXXXX-XXXX ou XX XXXXX-XXXX
    match_tel = re.search(r"(?:Telefone|Celular|Contato|Tel).*?(\(?\d{2}\)?\s*\d{4,5}-?\d{4})", clean_text, re.IGNORECASE)
    if match_tel:
         data["Telefone"] = re.sub(r"[^\d]", "", match_tel.group(1))

    # 5. ENDEREÇO
    # Busca por "Endereço:" ou "Residente em:"
    match_end = re.search(r"(?:Endereço|Residente em|Domiciliado em)\s*[:\-\s]\s*(.+?)(?:\s*CEP|\s*Bairro|\s*Cidade|\s*UF|$)", clean_text, re.IGNORECASE)
    if match_end:
         data["Endereco"] = match_end.group(1).strip()

    # 6. CONTRATO
    match_con = re.search(r"(?:Cédula|Contrato|Proposta)\s*N?[ºo]?\s*[:\-\s]*(\d+)", clean_text, re.IGNORECASE)
    if match_con:
        data["Numero_Contrato"] = match_con.group(1)

    # 7. DATA
    match_data = re.search(r"(?:Data|Emissão).*?(\d{2}/\d{2}/\d{4})", clean_text, re.IGNORECASE)
    if match_data:
        data["Data_Contrato"] = match_data.group(1)

    # CRITÉRIO DE SUCESSO:
    # Se achou NOME e (CPF ou EMAIL ou TELEFONE), consideramos que a regra funcionou bem.
    if data.get("Nome") and (data.get("CPF_CNPJ") or data.get("Email") or data.get("Telefone")):
        print(f"DEBUG: Padrão GENÉRICO detectado! Dados extraídos via Regras: {data}")
        
        # Preencher campos faltantes com None
        required_fields = ["Telefone", "Email", "Endereco", "Numero_Contrato", "Data_Contrato"]
        for f in required_fields:
            if f not in data:
                data[f] = None
                
        data["Erro"] = None
        return data
        
    print("DEBUG: Padrão GENÉRICO insuficiente (faltou Nome ou DOC).")
    return None

def extract_with_gemini(text):
    """Extrai dados usando Google Gemini 2.0 Flash (Estruturado)."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY não configurada."

    try:
        print("DEBUG: Iniciando extração com Google Gemini...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # OTIMIZAÇÃO: Filtrar apenas linhas relevantes antes de enviar
        filtered_text = extract_relevant_segments(text, max_lines=60)
        
        prompt = f"""
        Você é um auditor jurídico extraindo dados de um contrato ou petição.
        Sua missão: Encontrar NOME, CPF_CNPJ, TELEFONE e EMAIL APENAS DO RÉU (Devedor Principal / Cliente).
        
        REGRAS DE EXCLUSÃO:
        1. IGNORE TOTALMENTE dados de advogados, procuradores, juízes ou escritórios (OAB, @adv.br, etc).
        2. PRIORIDADE MÁXIMA: Dados pessoais do DEVEDOR/CLIENTE.
        3. Se não encontrar, retorne null para o campo.

        TEXTO DO CONTRATO:
        {filtered_text}
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": ContractData,
            },
        )

        if response.parsed:
            data = response.parsed.model_dump()
            print("DEBUG: Sucesso na extração com Gemini!")
            return data, None
        else:
            return None, "Falha ao processar resposta estruturada do Gemini."

    except Exception as e:
        msg = f"Erro na extração com Gemini: {e}"
        print(f"DEBUG: {msg}")
        return None, msg

def extract_data_from_pdf(pdf_path):
    """Extrai dados do PDF usando Híbrido: Regras -> Gemini."""
    
    # 1. Extração do Texto Cru
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception as e:
        print(f"Erro ao ler PDF: {e}")
        return {}

    # 2. TENTATIVA VIA REGRAS (Prioridade Máxima)
    rule_data = extract_bv_data_rule_based(text) or extract_generic_data_rule_based(text)
    if rule_data:
        return rule_data

    # 3. Gemini
    gemini_data, error_msg = extract_with_gemini(text)
    
    if gemini_data:
        return gemini_data
    
    print(f"DEBUG: Gemini falhou ({error_msg}). Usando Fallback Regex.")

    # 4. Fallback Regex
    base_data = {
        "Nome": None,
        "CPF_CNPJ": None,
        "Telefone": None,
        "Email": None,
        "Endereco": None,
        "Numero_Contrato": None,
        "Data_Contrato": None,
        "Erro": f"Gemini falhou: {error_msg}. Extraído via Regex (Fallback)"
    }
    regex_data = extract_with_regex_fallback(text)
    base_data.update(regex_data)
    return base_data

def save_to_db(data_dict):
    """Salva os dados extraídos no banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="web_bd",
            user="user",
            password="password"
        )
        cur = conn.cursor()
        
        insert_query = """
        INSERT INTO contratos_extraidos (
            processo, contrato_arvore, nome, cpf_cnpj, telefone, email, endereco, numero_contrato, data_contrato, erro, data_referencia
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cur.execute(insert_query, (
            data_dict.get("Processo"),
            data_dict.get("Contrato_Arvore"),
            data_dict.get("Nome"),
            data_dict.get("CPF_CNPJ"),
            data_dict.get("Telefone"),
            data_dict.get("Email"),
            data_dict.get("Endereco"),
            data_dict.get("Numero_Contrato"),
            data_dict.get("Data_Contrato"),
            data_dict.get("Erro"),
            data_dict.get("Data_Referencia")
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        print("Dados salvos no Banco de Dados com sucesso.")
    except Exception as e:
        print(f"Erro ao salvar no banco de dados: {e}")

def create_table_if_not_exists():
    """Cria a tabela no banco de dados se ela não existir."""
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="web_bd",
            user="user",
            password="password"
        )
        cur = conn.cursor()
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS contratos_extraidos (
            id SERIAL PRIMARY KEY,
            processo VARCHAR(50),
            contrato_arvore VARCHAR(50),
            nome VARCHAR(255),
            cpf_cnpj VARCHAR(20),
            telefone VARCHAR(50),
            email VARCHAR(255),
            endereco TEXT,
            numero_contrato VARCHAR(50),
            data_contrato VARCHAR(20),
            erro TEXT,
            data_extracao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cur.execute(create_table_query)
        conn.commit()
        cur.close()
        conn.close()
        print("Tabela 'contratos_extraidos' verificada/criada com sucesso.")
    except Exception as e:
        print(f"Erro ao criar tabela no banco de dados: {e}")

def cleanup_pdfs():
    """Remove todos os PDFs da pasta downloads."""
    download_dir = os.path.join(os.getcwd(), "downloads")
    if os.path.exists(download_dir):
        files = glob.glob(os.path.join(download_dir, "*.pdf"))
        print(f"Limpando {len(files)} arquivos PDF da pasta {download_dir}...")
        for f in files:
            try:
                os.remove(f)
            except Exception as e:
                print(f"Erro ao remover {f}: {e}")
        print("Limpeza concluída.")

def kill_chrome():
    """Mata os processos do Chrome de forma cross-platform."""
    try:
        if platform.system() == "Windows":
            os.system("taskkill /F /IM chrome.exe /T >nul 2>&1")
        else:
            os.system("pkill -f chrome > /dev/null 2>&1")
        print("Processos do Chrome encerrados.")
    except Exception as e:
        print(f"Erro ao encerrar Chrome: {e}")

def force_start_chrome_debug():
    """Fecha Chromes abertos e inicia um novo em modo Debug."""
    print("\n--- INICIANDO CHROME VIA SCRIPT ---")
    try:
        kill_chrome()
        time.sleep(1)
        
        print("Abrindo Chrome na porta 9222...")
        user_data_dir = os.path.join(os.path.expanduser("~"), "selenium_chrome_profile")
        
        if platform.system() == "Windows":
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            if not os.path.exists(chrome_path):
                chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            
            if os.path.exists(chrome_path):
                cmd = f'start "" "{chrome_path}" --remote-debugging-port=9222 --user-data-dir="{user_data_dir}"'
                os.system(cmd)
            else:
                print(f"ERRO: Chrome não encontrado no Windows.")
                return False
        else:
            # Linux
            cmd = f'google-chrome --remote-debugging-port=9222 --user-data-dir="{user_data_dir}" &'
            os.system(cmd)
            
        print("Chrome iniciado! Aguardando 5 segundos para carregar...")
        time.sleep(5)
        return True
    except Exception as e:
        print(f"Erro ao tentar iniciar Chrome: {e}")
        return False

def download_pdf_via_requests(driver, pdf_url, output_path):
    """Baixa o PDF usando requests e os cookies do Selenium."""
    try:
        print(f"DEBUG: Tentando baixar PDF via requests para: {output_path}")
        session = requests.Session()
        
        # Copiar cookies do Selenium para o requests
        cookies = driver.get_cookies()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'])
            
        # Headers para parecer um navegador
        headers = {
            "User-Agent": driver.execute_script("return navigator.userAgent;")
        }
        
        response = session.get(pdf_url, headers=headers, stream=True, verify=False) # verify=False pois PJe costuma ter certs autoassinados
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("DEBUG: Download via requests concluído com sucesso.")
            return True
        else:
            print(f"DEBUG: Falha no download via requests. Status Code: {response.status_code}")
            return False
    except Exception as e:
        print(f"DEBUG: Erro no download via requests: {e}")
        return False

def process_case(driver, case_number, original_window, reference_date):
    """Processa um caso, iterando por documentos até achar os dados ou esgotar tentativas."""
    try:
        print(f"--- PROCESSANDO CASO: {case_number} ---")
        
        # 1. Garantir que estamos na janela nova
        handle_cnj_alert(driver)
        
        # 2. Aguardar carregamento da árvore
        print("Janela do processo aberta. Aguardando carregamento da árvore de documentos...")
        time.sleep(3) 

        # Lista de Prioridade de Documentos
        # Tenta o primeiro. Se achar Email E Telefone, para. Se não, vai pro próximo.
        document_priorities = [
            ["Contrato", "contrato", "CONTRATO", "Cédula", "Cédula"],
            ["Procuração", "procuração", "PROCURAÇÃO", "Procuracao"],
            ["Petição Inicial", "Petição", "Inicial", "PETIÇÃO"],
            ["Ficha", "Ficha Cadastral", "Cadastro"]
        ]

        # Estrutura para acumular dados
        final_data = {
            "Processo": case_number,
            "Contrato_Arvore": "N/A",
            "Data_Referencia": reference_date,
            "Nome": None,
            "CPF_CNPJ": None,
            "Telefone": None,
            "Email": None,
            "Endereco": None,
            "Numero_Contrato": None,
            "Data_Contrato": None,
            "Erro": None
        }

        data_found_completeness = False # Flag para saber se já temos tudo (Email + Telefone)

        start_time = time.time()
        
        # Loop pelos tipos de documento
        for doc_keywords in document_priorities:
            if data_found_completeness:
                break
                
            print(f"DEBUG: Buscando documento por palavras-chave: {doc_keywords}")
            
            # Tentar encontrar o elemento na árvore
            target_element = None
            
            # XPath dinâmico para as keywords
            # //span[contains(text(), 'Key1') or contains(text(), 'Key2')...]
            xpath_parts = [f"contains(text(), '{k}')" for k in doc_keywords]
            xpath_search = f"//span[{' or '.join(xpath_parts)}] | //div[{' or '.join(xpath_parts)}]"
            
            try:
                elements = driver.find_elements(By.XPATH, xpath_search)
                # Filtra visíveis
                visible_elements = [el for el in elements if el.is_displayed()]
                
                if not visible_elements:
                    print(f"DEBUG: Nenhum documento do tipo {doc_keywords[0]} encontrado.")
                    continue
                
                # Pega o primeiro encontrado desse tipo (geralmente o mais recente/relevante no topo ou base)
                # Na árvore do PJe, o mais recente costuma ficar em cima ou embaixo dependendo da ordenação.
                # Vamos tentar o PRIMEIRO da lista visible_elements
                target_element = visible_elements[0]
                doc_name = target_element.text
                print(f"DEBUG: Documento encontrado: {doc_name}")
                
                 # Extrair numero do contrato se for o tipo Contrato e ainda não tiver
                if "Contrato" in doc_keywords[0] and final_data["Contrato_Arvore"] == "N/A":
                     final_data["Contrato_Arvore"] = doc_name.split("-")[0].strip() if "-" in doc_name else "N/A"

                # Clicar e Baixar
                try:
                    target_element.click()
                    print(f"Clicado em {doc_name}. Aguardando...")
                    time.sleep(4) # Espera iframe
                except Exception as e_click:
                     print(f"Erro ao clicar em {doc_name}: {e_click}")
                     continue

                # Encontrar URL do PDF
                pdf_url = None
                try:
                    frame = driver.find_element(By.TAG_NAME, "iframe")
                    pdf_url = frame.get_attribute("src")
                except:
                    try:
                        obj = driver.find_element(By.TAG_NAME, "object")
                        pdf_url = obj.get_attribute("data")
                    except:
                        print("Não achou iframe/object PDF.")

                if pdf_url:
                    print(f"DEBUG: URL PDF encontrada.")
                    timestamp = int(time.time())
                    # Nome do arquivo inclui o tipo para debug
                    safe_doc_type = doc_keywords[0].replace(" ", "_").lower()
                    pdf_filename = f"{case_number}_{safe_doc_type}_{timestamp}.pdf".replace("/", "-")
                    download_dir = os.path.join(os.getcwd(), "downloads")
                    pdf_path = os.path.join(download_dir, pdf_filename)
                    
                    if download_pdf_via_requests(driver, pdf_url, pdf_path):
                        print(f"DEBUG: PDF {safe_doc_type} baixado. Analisando com AI...")
                        
                        # Extrair dados do PDF atual
                        new_data = extract_data_from_pdf(pdf_path)
                        
                        # Mesclar dados (Prioriza o que não é None)
                        # Só sobrescreve se o final_data[key] for None
                        for key, value in new_data.items():
                            if key in final_data and (final_data[key] is None or final_data[key] == "") and value:
                                final_data[key] = value
                                print(f"DEBUG: Atualizando campo {key} com: {value}")
                        
                        # Checar completude
                        if final_data.get("Email") and final_data.get("Telefone"):
                            print("DEBUG: Email e Telefone encontrados! Parando busca de documentos.")
                            data_found_completeness = True
                            break
                    else:
                        print("Falha download PDF.")
                else:
                    print("URL PDF vazia.")

            except Exception as e_doc:
                print(f"Erro ao processar tipo {doc_keywords}: {e_doc}")
        
        # Salva o resultado final acumulado
        print(f"DEBUG: Dados Finais para Salvar: {final_data}")
        save_to_db(final_data)

        print("DEBUG: Fim do processamento do caso.")
        
    except Exception as e:
        print(f"Erro ao processar caso {case_number}: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("DEBUG: Executando cleanup da janela do caso...")
        try:
            # Fechar qualquer janela que não seja a original
            current_handles = driver.window_handles
            if len(current_handles) > 1:
                for w in current_handles:
                    if w != original_window:
                        driver.switch_to.window(w)
                        driver.close()
            
            # Voltar para original
            driver.switch_to.window(original_window)
        except Exception as e_final:
             print(f"DEBUG: Erro no cleanup de janelas: {e_final}")

# ... (rest of main function remains similar, just ensuring process_case calls match)

# ... (rest of main function remains similar, just ensuring process_case calls match)

def is_debugger_port_open(port=9222):
    """Verifica se há algo ouvindo na porta do debugger."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    driver = None
    try:
        print("--- INICIANDO SCRIPT ---") # REMOVE DUPLICATE IF PRESENT (USER HAD IT TWICE)
        
        # 1. Verificar se a porta 9222 está aberta. Se não, forçar início.
        if not is_debugger_port_open(9222):
            print("Porta 9222 parece fechada/não respondendo.")
            print("Iniciando Chrome automaticamente...")
            if not force_start_chrome_debug():
                print("Falha ao iniciar Chrome. Encerrando.")
                return
        else:
            print("Porta 9222 detectada como ABERTA. Tentando conectar...")

        print("Tentando conectar ao Chrome na porta 9222...")
        
        try:
            driver = setup_driver()
        except Exception as e:
            print(f"Erro na conexão inicial: {e}")
            print("Tentando reiniciar o Chrome e conectar novamente...")
            if force_start_chrome_debug():
                try:
                    driver = setup_driver()
                except Exception as e2:
                    print(f"ERRO FATAL: Falha na segunda tentativa. {e2}")
                    return
            else:
                return

        print("Conexão com Chrome estabelecida com sucesso!")
        print(f"Título da página atual: {driver.title}")
        print(f"URL atual: {driver.current_url}")

        # Garantir que a tabela existe no banco
        create_table_if_not_exists()

        wait = WebDriverWait(driver, 10) # Reduzido para testar mais rápido
        
        target_url = "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam"
        if "ConsultaProcesso/listView.seam" not in driver.current_url:
            print(f"A URL atual não parece ser a de consulta processual.")
            print(f"Navegando para: {target_url}")
            driver.get(target_url)
            time.sleep(3)
        
        # --- LOGIN AUTOMÁTICO ---
        perform_login(driver, wait)
        
        # Garantir que estamos na tela de consulta após o login
        if "ConsultaProcesso/listView.seam" not in driver.current_url:
            print("Redirecionando para a tela de Consulta Processual...")
            driver.get(target_url)
            time.sleep(3)
            
        # 1. Busca
        print("Procurando campo 'Classe judicial'...")
        try:
            # Tenta encontrar o input de várias formas caso o ID mude ou o XPath seja frágil
            # Opção 1: XPath pelo Label (original)
            classe_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Classe judicial')]/following::input[1]")))
            print("Campo encontrado. Digitando filtro...")
            
            classe_input.click()
            classe_input.clear()
            classe_input.send_keys("Busca e apreensão Alienação Fiduciária")
            time.sleep(1)
            classe_input.send_keys(Keys.TAB) # Tenta TAB para validar
            print("Pressionando Enter para pesquisar...")
            # Pressiona Enter no input ou busca botão pesquisar
            classe_input.send_keys(Keys.ENTER)
        except TimeoutException:
            print("ERRO: Não conseguiu encontrar o campo 'Classe judicial'.")
            print("Verifique se você está logado e na tela 'Consulta processos' > 'Lista'.")
            return
        
        print("Aguardando 5 segundos para atualização da tabela...")
        time.sleep(5)
        
        # 2. Iterar com Paginação
        target_date_str = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
        target_date_obj = datetime.strptime(target_date_str, "%d/%m/%Y")
        print(f"Procurando processos com data: {target_date_str}")
        
        original_window = driver.current_window_handle
        processed_count = 0
        page_number = 1
        
        while True:
            print(f"--- Processando Página {page_number} ---")
            
            try:
                # Esperar até que a tabela ou a mensagem de "sem resultados" apareça
                print("Aguardando carregamento da tabela...")
                wait.until(lambda d: 
                    d.find_elements(By.XPATH, "//table[contains(@class, 'rich-table')]//tr[contains(@class, 'rich-table-row')]") or 
                    d.find_elements(By.XPATH, "//div[contains(text(), 'Nenhum registro')]") or
                    d.find_elements(By.XPATH, "//span[contains(text(), 'Nenhum registro')]")
                )
            except TimeoutException:
                print("Tempo limite excedido aguardando resultados.")
                break

            # Verificar se há mensagem de "Nenhum registro"
            if driver.find_elements(By.XPATH, "//div[contains(text(), 'Nenhum registro')]") or \
               driver.find_elements(By.XPATH, "//span[contains(text(), 'Nenhum registro')]"):
                print("Mensagem de 'Nenhum registro encontrado' detectada.")
                break
            
            rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'rich-table')]//tr[contains(@class, 'rich-table-row')]")
            
            if not rows:
                print("Tabela encontrada, mas nenhuma linha de dados (rich-table-row) visível.")
                # Pode tentar um fallback caso a classe mude
                rows = driver.find_elements(By.XPATH, "//table[contains(@id, 'processo')]//tbody//tr")
                if not rows:
                    print("Fallback também não encontrou linhas. Encerrando página.")
                    break

            stop_processing = False
            found_target_date_on_page = False
            
            for i in range(len(rows)):
                # Re-find rows to avoid stale element reference
                rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'rich-table')]//tr[contains(@class, 'rich-table-row')]")
                if i >= len(rows): break
                row = rows[i]
                row_text = row.text
                
                # Verificação de Data para Parada
                match_data = re.search(r"(\d{2}/\d{2}/\d{4})", row_text)
                should_process_row = False
                
                if match_data:
                    try:
                        row_date_str = match_data.group(1)
                        row_date_obj = datetime.strptime(row_date_str, "%d/%m/%Y")
                        
                        # Se data da linha for MENOR que a data alvo (assumindo ordem decrescente), paramos.
                        if row_date_obj < target_date_obj:
                            print(f"Data encontrada ({row_date_str}) é ANTERIOR à data alvo ({target_date_str}). Parando processamento.")
                            stop_processing = True
                            break
                        
                        # Se data for IGUAL, marcamos para processar
                        if row_date_obj == target_date_obj:
                            should_process_row = True
                            found_target_date_on_page = True
                            
                    except Exception as e:
                        print(f"Erro ao comparar datas: {e}")
                
                # Fallback de string se não pegou objeto
                if not should_process_row and target_date_str in row_text:
                    should_process_row = True
                    found_target_date_on_page = True

                if should_process_row:
                    print(f"Linha {i} corresponde à data {target_date_str}")
                    
                    try:
                        links = row.find_elements(By.TAG_NAME, "a")
                        link_processo = None
                        case_number = "Desconhecido"
                        padrao_processo = re.compile(r"\d{7}-\d{2}\.\d{4}\.")
                        
                        for link in links:
                            txt = link.text.strip()
                            if padrao_processo.search(txt):
                                link_processo = link
                                case_number = txt
                                break
                        
                        if not link_processo:
                            print(f"Aviso: Não encontrei link de processo válido na linha {i}. Pulando.")
                            continue
    
                        print(f"Tentando abrir processo: {case_number}")
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", link_processo)
                        time.sleep(1)
                        
                        print("Clicando no NÚMERO do processo...")
                        try:
                            link_processo.click()
                        except Exception as e:
                            print(f"Exceção no clique. Verificando se é alerta...")
                            if handle_cnj_alert(driver):
                                print("Alerta tratado.")
                                try:
                                    link_processo.click()
                                except:
                                    pass
                            else:
                                raise e
    
                        handle_cnj_alert(driver)
                        
                        print("Aguardando nova janela...")
                        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
                        new_window = [w for w in driver.window_handles if w != original_window][0]
                        driver.switch_to.window(new_window)
                        
                        print(f"DEBUG: Chamando process_case para {case_number}...")
                        process_case(driver, case_number, original_window, target_date_str)
                        print(f"DEBUG: process_case retornou para {case_number}.")
                        
                        driver.switch_to.window(original_window)
                        processed_count += 1
                    except Exception as e:
                        print(f"Erro ao processar linha {i}: {e}")
                        import traceback
                        traceback.print_exc()
                        
                        handle_cnj_alert(driver)
                        
                        # Garante volta
                        try:
                            while len(driver.window_handles) > 1:
                                driver.switch_to.window(driver.window_handles[-1])
                                driver.close()
                            driver.switch_to.window(original_window)
                        except:
                            pass

            if stop_processing:
                print("Critério de parada atingido (data anterior encontrada).")
                break
            
            if found_target_date_on_page:
                print(f"Ainda identificamos a data {target_date_str} nesta página. Continuando para a próxima página...")

            # Paginação
            try:
                next_btn = driver.find_element(By.XPATH, "//div[@class='rich-datascr-button'][contains(text(), '>') or contains(text(), 'Próximo')] | //td[contains(@class, 'rich-datascr-button')][contains(text(), '>') or contains(text(), 'Próximo')]")
                if "rich-datascr-inact" not in next_btn.get_attribute("class") and next_btn.is_enabled():
                    print("Indo para a próxima página...")
                    next_btn.click()
                    time.sleep(5)
                    page_number += 1
                else:
                    print("Sem mais páginas (botão desativado ou oculto).")
                    break
            except:
                print("Fim da paginação ou botão não encontrado.")
                break
        
        print(f"Processamento concluído. {processed_count} processos analisados.")
        cleanup_pdfs()
        
    except Exception as e:
        print(f"Erro fatal: {e}")
    finally:
        # Não fechar o navegador pois é a sessão do usuário
        print("Automação finalizada. O navegador permanecerá aberto.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupção do usuário (Ctrl+C).")
    except Exception as e:
        print(f"ERRO CRÍTICO NO SCRIPT: {e}")
        import traceback
        traceback.print_exc()
