import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="SGPWeb Extrator V5 (Separado)", page_icon="📦", layout="wide")
SENHA_DO_CLIENTE = "cliente2025" 

# --- VALORES PADRÃO (Configure conforme sua necessidade) ---
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

# --- LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_login():
    if st.session_state.authenticated: return True
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🔒 Acesso Restrito")
        senha = st.text_input("Senha:", type="password")
        if st.button("Entrar"):
            if senha == SENHA_DO_CLIENTE:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

# --- MOTOR DE EXTRAÇÃO E TRATAMENTO ---

def processar_meia_pagina(page):
    """Corta a página ao meio para ler só o lado esquerdo (ENVIAR PARA)."""
    width = page.width
    height = page.height
    bbox = (0, 0, width / 2 + 20, height) # Margem um pouco maior
    
    try:
        left_side = page.crop(bbox)
        text = left_side.extract_text()
    except:
        text = page.extract_text()

    if not text: return []

    linhas = text.split('\n')
    dados_uteis = []
    capturando = False
    
    for linha in linhas:
        linha = linha.strip()
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue
        
        # Parar de capturar se encontrar estes termos
        if capturando:
            if any(x in linha.upper() for x in ["COBRAR DE", "PEDIDO #", "SPA COSMETICS", "OBSERVAÇÕES"]):
                break
            if linha:
                dados_uteis.append(linha)
            
    return dados_uteis

def separar_endereco(linhas):
    """
    Lógica avançada para separar Rua, Numero, Bairro, Cidade, etc.
    Baseado no padrão:
    Linha 1: Nome
    Linha 2: CPF
    Linha 3: Rua, Numero, Complemento
    Linha 4: Bairro (ou continuação)
    Linha 5: Cidade UF, CEP
    """
    if not linhas: return None
    
    # 1. Identificar Nome e CPF
    nome = linhas[0]
    cpf = ""
    
    # Procura CPF nas linhas seguintes
    regex_cpf = r'\d{11}'
    idx_cpf = -1
    for i, l in enumerate(linhas):
        limpo = l.replace('.', '').replace('-', '').strip()
        if re.match(regex_cpf, limpo):
            cpf = limpo
            idx_cpf = i
            break
    
    # Se não achou CPF, assume que é a segunda linha
    if idx_cpf == -1: idx_cpf = 1
    
    # 2. Identificar Cidade/UF/CEP (Geralmente a linha com CEP)
    cidade = ""
    uf = ""
    cep = ""
    idx_cidade = -1
    regex_cep = r'\d{5}-?\d{3}'
    
    for i in range(len(linhas)-1, idx_cpf, -1): # Procura de baixo pra cima
        l = linhas[i]
        match_cep = re.search(regex_cep, l)
        if match_cep:
            cep = match_cep.group(0).replace('-', '') # Remove traço pro SGPWeb
            idx_cidade = i
            
            # Tenta separar Cidade e UF "Monte Carmelo MG, 38500-000"
            parte_end = l.split(match_cep.group(0))[0].strip().strip(',').strip()
            # Pega os ultimos 2 caracteres como UF
            if len(parte_end) > 2:
                uf = parte_end[-2:]
                cidade = parte_end[:-2].strip()
            break
            
    # 3. O que sobrou no meio é Endereço e Bairro
    # Geralmente: [Rua, Num, Comp] e depois [Bairro]
    logradouro = ""
    numero = ""
    complemento = ""
    bairro = ""
    
    if idx_cidade > idx_cpf:
        linhas_meio = linhas[idx_cpf+1 : idx_cidade]
        
        # A última linha do meio costuma ser o Bairro
        if len(linhas_meio) >= 1:
            bairro = linhas_meio[-1]
            
            # As linhas anteriores são a Rua
            if len(linhas_meio) > 1:
                linha_rua = linhas_meio[0] # Pega a primeira linha de endereço
                
                # Separa por vírgula: "Rua tubarão, 801, Casa"
                partes_rua = linha_rua.split(',')
                
                if len(partes_rua) > 0:
                    logradouro = partes_rua[0].strip()
                if len(partes_rua) > 1:
                    numero = partes_rua[1].strip()
                if len(partes_rua) > 2:
                    complemento = " ".join(partes_rua[2:]).strip()
            else:
                # Se só tem 1 linha no meio, pode ser que o Bairro esteja na mesma linha ou não tenha Bairro
                # Assumimos que é tudo endereço se não tiver vírgula, ou tenta separar
                # Solução de contorno: Se bairro for muito longo e parecer rua, ajusta
                if "," in bairro:
                    # Oops, o bairro na verdade era a rua
                    partes = bairro.split(',')
                    logradouro = partes[0]
                    numero = partes[1] if len(partes) > 1 else ""
                    complemento = partes[2] if len(partes) > 2 else ""
                    bairro = "" # Bairro vazio ou indefinido

    return {
        "NOME_DESTINATARIO": nome,
        "CPF_CNPJ": cpf,
        "ENDERECO": logradouro,
        "NUMERO": numero,
        "COMPLEMENTO": complemento,
        "BAIRRO": bairro,
        "CIDADE": cidade,
        "UF": uf,
        "CEP": cep,
        "PESO": PADRAO_PESO,
        "VALOR_DECLARADO": PADRAO_VALOR,
        "SERVICO": PADRAO_SERVICO
    }

# --- APP ---
if check_login():
    st.title("📦 Extrator SGPWeb (Layout Importação)")
    
    col_dl, col_info = st.columns([2, 1])
    with col_info:
        st.info(f"**Padrões Configurados:**\nPeso: {PADRAO_PESO}\nValor: {PADRAO_VALOR}\nServiço: {PADRAO_SERVICO}")

    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")
    
    if uploaded_file:
        lista_pedidos = []
        
        with pdfplumber.open(uploaded_file) as pdf:
            bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                bar.progress((i+1)/len(pdf.pages))
                
                # 1. Extração bruta
                linhas_brutas = processar_meia_pagina(page)
                
                # 2. Parsing fino
                if linhas_brutas:
                    pedido = separar_endereco(linhas_brutas)
                    if pedido and pedido["NOME_DESTINATARIO"]:
                        lista_pedidos.append(pedido)

        if lista_pedidos:
            df = pd.DataFrame(lista_pedidos)
            
            # Reordenar colunas para garantir a ordem exata
            cols_order = ["NOME_DESTINATARIO", "CPF_CNPJ", "ENDERECO", "NUMERO", 
                          "COMPLEMENTO", "BAIRRO", "CIDADE", "UF", "CEP", 
                          "PESO", "VALOR_DECLARADO", "SERVICO"]
            
            # Garante que todas colunas existam (mesmo se vazias)
            for col in cols_order:
                if col not in df.columns:
                    df[col] = ""
            
            df = df[cols_order]

            st.success(f"✅ {len(df)} Pedidos convertidos!")
            st.dataframe(df.head())
            
            # Exportar com PONTO E VÍRGULA (;) como solicitado
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV Importação", csv, "sgpweb_import.csv", "text/csv")
        else:
            st.warning("Nenhum dado encontrado.")
