import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO OBRIGATÓRIA (PRIMEIRA LINHA) ---
st.set_page_config(page_title="SGPWeb V11", page_icon="🚀", layout="wide")

# --- SENHA E PADRÕES ---
SENHA_DO_CLIENTE = "cliente2025" 
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

# --- FUNÇÕES DE LIMPEZA ---
def limpar_linha_duplicada(texto):
    if not texto or len(texto) < 3: return texto
    texto = texto.strip()
    palavras = texto.split()
    n = len(palavras)
    if n > 1 and n % 2 == 0:
        meio = n // 2
        p1 = palavras[:meio]
        p2 = palavras[meio:]
        if [p.lower() for p in p1] == [p.lower() for p in p2]:
            return " ".join(p1)
    return texto

def processar_pagina_esquerda(page):
    """Lê apenas a metade esquerda da página."""
    try:
        width = page.width
        height = page.height
        bbox = (0, 0, width / 2 + 20, height)
        crop = page.crop(bbox)
        text = crop.extract_text()
    except:
        return []

    if not text: return []
    
    linhas = text.split('\n')
    dados_uteis = []
    capturando = False
    
    for linha in linhas:
        linha = linha.strip()
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue
        if capturando:
            if any(x in linha.upper() for x in ["COBRAR DE", "PEDIDO #", "SPA COSMETICS", "OBSERVAÇÕES"]):
                break
            linha_limpa = linha.replace("COBRAR DE", "").strip()
            linha_final = limpar_linha_duplicada(linha_limpa)
            if linha_final:
                dados_uteis.append(linha_final)
    return dados_uteis

def separar_endereco_inteligente(linhas):
    """Separa usando CPF (Topo) e CEP (Fundo) como âncoras."""
    if not linhas: return None

    # 1. Nome
    nome = linhas[0]
    
    # 2. Achar CPF
    idx_cpf = -1
    cpf = ""
    for i, l in enumerate(linhas):
        digitos = re.sub(r'\D', '', l)
        if len(digitos) == 11 or (len(digitos) == 22 and digitos[:11] == digitos[11:]):
            cpf = digitos[:11]
            idx_cpf = i
            break
            
    # 3. Achar CEP (de baixo pra cima)
    idx_cep = -1
    cep = ""
    cidade = ""
    uf = ""
    for i in range(len(linhas)-1, -1, -1):
        l = linhas[i]
        match = re.search(r'\d{5}-?\d{3}', l)
        if match:
            idx_cep = i
            cep = match.group(0).replace('-', '')
            resto = l.split(match.group(0))[0].strip().strip(',').strip()
            if len(resto) > 2:
                uf = resto[-2:]
                cidade = resto[:-2].strip().strip('-')
            else:
                cidade = resto
            break

    if idx_cpf == -1 or idx_cep == -1: return None

    # 4. Recheio (Endereço e Bairro)
    linhas_recheio = linhas[idx_cpf+1 : idx_cep]
    logradouro = ""
    numero = ""
    complemento = ""
    bairro = ""
    
    if linhas_recheio:
        # Última linha do recheio é Bairro
        if len(linhas_recheio) > 1:
            bairro = linhas_recheio[-1]
            texto_rua = " ".join(linhas_recheio[:-1]) 
        else:
            texto_rua = linhas_recheio[0]
            
        partes = [p.strip() for p in texto_rua.split(',') if p.strip()]
        
        if len(partes) > 0:
            logradouro = partes[0]
            if len(partes) > 1:
                segunda = partes[1]
                if any(c.isdigit() for c in segunda) or "S/N" in segunda.upper():
                    numero = segunda
                    if len(partes) > 2: complemento = " ".join(partes[2:])
                else:
                    if not bairro: bairro = segunda
                    else: complemento = " ".join(partes[1:])
            else:
                # Tenta achar numero no fim da string se não tiver virgula
                match_num = re.search(r'(\d+)$', logradouro)
                if match_num:
                    numero = match_num.group(1)
                    logradouro = logradouro.replace(numero, "").strip()

    return {
        "NOME_DESTINATARIO": nome, "CPF_CNPJ": cpf, "ENDERECO": logradouro,
        "NUMERO": numero, "COMPLEMENTO": complemento, "BAIRRO": bairro,
        "CIDADE": cidade, "UF": uf, "CEP": cep,
        "PESO": PADRAO_PESO, "VALOR_DECLARADO": PADRAO_VALOR, "SERVICO": PADRAO_SERVICO
    }

# --- APP PRINCIPAL ---
def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1,1,1])
        with col2:
            st.title("🔒 Login")
            senha = st.text_input("Senha:", type="password")
            if st.button("Entrar"):
                if senha == SENHA_DO_CLIENTE:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
        return

    st.title("📦 Extrator SGPWeb V11")
    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")

    if uploaded_file:
        pedidos = []
        with pdfplumber.open(uploaded_file) as pdf:
            bar = st.progress(0)
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                bar.progress((i+1)/total)
                linhas = processar_pagina_esquerda(page)
                if linhas:
                    p = separar_endereco_inteligente(linhas)
                    if p: pedidos.append(p)
        
        if pedidos:
            df = pd.DataFrame(pedidos)
            cols = ["NOME_DESTINATARIO", "CPF_CNPJ", "ENDERECO", "NUMERO", 
                    "COMPLEMENTO", "BAIRRO", "CIDADE", "UF", "CEP", 
                    "PESO", "VALOR_DECLARADO", "SERVICO"]
            for c in cols: 
                if c not in df.columns: df[c] = ""
            df = df[cols]
            st.success(f"✅ {len(df)} Pedidos!")
            st.dataframe(df.head())
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV", csv, "importacao.csv", "text/csv")

if __name__ == "__main__":
    main()