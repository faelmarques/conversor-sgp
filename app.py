import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="SGPWeb Pro V4 (Corte)", page_icon="✂️", layout="wide")
SENHA_DO_CLIENTE = "cliente2025" 

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

# --- LÓGICA DE CORTE E EXTRAÇÃO ---

def limpar_linha(linha):
    return linha.strip()

def processar_meia_pagina(page):
    """
    Técnica da Lobotomia: Corta a página verticalmente ao meio
    e lê apenas o lado ESQUERDO (Enviar Para).
    """
    width = page.width
    height = page.height
    
    # Define a caixa de corte: (x0, top, x1, bottom)
    # Pegamos de 0 até a metade da largura (width / 2)
    bbox = (0, 0, width / 2 + 10, height) # +10 de margem de segurança
    
    try:
        # Faz o corte
        left_side = page.crop(bbox)
        text = left_side.extract_text()
    except:
        # Se falhar o corte, tenta ler a página inteira
        text = page.extract_text()

    if not text: return None

    linhas = text.split('\n')
    
    # Procura onde começa os dados
    dados_uteis = []
    capturando = False
    
    for linha in linhas:
        linha = linha.strip()
        
        # Gatilho para começar a gravar
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue # Pula a linha do título
        
        # Gatilhos para PARAR de gravar (Rodapés, telefones soltos, outros cabeçalhos)
        if capturando:
            if "COBRAR DE" in linha.upper(): break # Caso o corte tenha falhado
            if "PEDIDO #" in linha.upper(): break
            if "SPA COSMETICS" in linha.upper(): break
            if "OBSERVAÇÕES" in linha.upper(): break
            if not linha: continue
            
            dados_uteis.append(linha)
            
    return dados_uteis

def estruturar_pedido(linhas):
    if not linhas: return None
    
    nome = linhas[0] # A primeira linha DEPOIS do "Enviar Para" é sempre o nome
    cpf = ""
    cep = ""
    telefone = ""
    endereco_parts = []
    
    regex_cpf = r'\d{11}'
    regex_cep = r'\d{5}-?\d{3}'
    
    # Pula a primeira linha (nome) e analisa o resto
    for linha in linhas[1:]:
        # CPF
        if re.match(regex_cpf, linha.replace('.', '').replace('-', '').strip()):
            cpf = linha
            continue
            
        # CEP
        match_cep = re.search(regex_cep, linha)
        if match_cep:
            cep = match_cep.group(0)
            endereco_parts.append(linha) # Mantém linha do CEP (tem cidade)
            continue
            
        # Telefone
        if "+55" in linha or re.search(r'\(\d{2}\)', linha):
            telefone = linha.replace("Brasil", "").strip()
            continue
            
        # Endereço
        if len(linha) > 2 and "Brasil" not in linha:
            endereco_parts.append(linha)

    return {
        "Nome": nome,
        "CPF": cpf,
        "Telefone": telefone,
        "CEP": cep,
        "Endereço": ", ".join(endereco_parts),
        "Email": "cliente@email.com"
    }

# --- APP ---
if check_login():
    st.title("✂️ SGPWeb Extrator V4 (Corte Lateral)")
    st.info("Estratégia: O sistema lê apenas a metade esquerda da página para evitar dados duplicados.")
    
    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")
    
    if uploaded_file:
        pedidos = []
        
        with pdfplumber.open(uploaded_file) as pdf:
            progresso = st.progress(0)
            for i, page in enumerate(pdf.pages):
                progresso.progress((i + 1) / len(pdf.pages))
                
                # 1. Extrai linhas apenas da esquerda
                linhas_brutas = processar_meia_pagina(page)
                
                # 2. Transforma em objeto pedido
                if linhas_brutas:
                    pedido = estruturar_pedido(linhas_brutas)
                    # Validação básica: só adiciona se tiver pelo menos Nome
                    if pedido and pedido['Nome']:
                        pedido['ID_Pagina'] = i + 1
                        pedidos.append(pedido)

        if pedidos:
            df = pd.DataFrame(pedidos)
            st.success(f"✅ {len(df)} Pedidos extraídos com sucesso!")
            st.dataframe(df)
            
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV", csv, "sgpweb_v4.csv", "text/csv")
        else:
            st.error("Nenhum pedido encontrado. Tente novamente.")
