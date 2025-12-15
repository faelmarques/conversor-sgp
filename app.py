import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES ---
try:
    st.set_page_config(page_title="SGPWeb V10 (Dinâmico)", page_icon="🧠", layout="wide")
except:
    pass

SENHA_DO_CLIENTE = "cliente2025" 
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

# --- FUNÇÕES ---

def limpar_linha_duplicada(texto):
    """Remove repetição exata na linha (ex: 'Centro Centro')"""
    if not texto or len(texto) < 3: return texto
    texto = texto.strip()
    # Tenta remover duplicidade perfeita
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
    """Corta a página ao meio para ler só o lado do envio."""
    width = page.width
    height = page.height
    bbox = (0, 0, width / 2 + 20, height)
    
    try:
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
            
            # Limpa "COBRAR DE" residual e duplicidades
            linha_limpa = linha.replace("COBRAR DE", "").strip()
            linha_final = limpar_linha_duplicada(linha_limpa)
            
            if linha_final:
                dados_uteis.append(linha_final)
                
    return dados_uteis

def separar_endereco_inteligente(linhas):
    """
    Lógica de Âncoras (Sanduíche):
    1. Acha o CPF (Topo)
    2. Acha o CEP (Fundo)
    3. O que sobrar no meio é Endereço + Bairro.
       A última linha do meio é o Bairro. O resto é Rua.
    """
    if not linhas: return None

    # --- 1. LOCALIZAR ÂNCORAS ---
    nome = linhas[0] # Nome é sempre a primeira linha
    
    idx_cpf = -1
    cpf = ""
    
    # Procura CPF
    for i, l in enumerate(linhas):
        digitos = re.sub(r'\D', '', l)
        if len(digitos) == 11 or (len(digitos) == 22 and digitos[:11] == digitos[11:]):
            cpf = digitos[:11]
            idx_cpf = i
            break
            
    # Procura CEP (de baixo pra cima)
    idx_cep = -1
    cep = ""
    cidade = ""
    uf = ""
    
    regex_cep = r'\d{5}-?\d{3}'
    for i in range(len(linhas)-1, -1, -1):
        l = linhas[i]
        match = re.search(regex_cep, l)
        if match:
            idx_cep = i
            cep = match.group(0).replace('-', '')
            # Extrai Cidade/UF
            resto = l.split(match.group(0))[0].strip().strip(',').strip()
            if len(resto) > 2:
                uf = resto[-2:]
                cidade = resto[:-2].strip().strip('-')
            else:
                cidade = resto
            break

    # Se não achou âncoras, aborta
    if idx_cpf == -1 or idx_cep == -1:
        return None

    # --- 2. PROCESSAR O "RECHEIO" (ENDEREÇO E BAIRRO) ---
    # Pegamos tudo que está entre o CPF e o CEP
    linhas_recheio = linhas[idx_cpf+1 : idx_cep]
    
    logradouro = ""
    numero = ""
    complemento = ""
    bairro = ""
    
    if linhas_recheio:
        # Se tiver mais de uma linha no recheio, a última é o BAIRRO (como você disse)
        if len(linhas_recheio) > 1:
            bairro = linhas_recheio[-1] # A última linha é o Bairro
            
            # As linhas anteriores são o Endereço (Rua, Num, Comp)
            # Juntamos elas caso a rua tenha quebrado de linha
            texto_rua = " ".join(linhas_recheio[:-1]) 
        else:
            # Se só tiver uma linha, o Bairro deve estar separado por vírgula no final
            # Ou o endereço é curto e o bairro é a linha inteira?
            # Vamos assumir que se só tem 1 linha, tentamos separar por vírgula
            texto_rua = linhas_recheio[0]
            # Se essa única linha for curta e não tiver numero, pode ser que o endereço ficou colado no CPF
            # Mas vamos processar como rua normal
            
        # Agora separamos Rua, Número e Complemento pelas vírgulas
        partes = [p.strip() for p in texto_rua.split(',') if p.strip()]
        
        if len(partes) > 0:
            logradouro = partes[0]
            
            if len(partes) > 1:
                segunda = partes[1]
                # Verifica se é número
                if any(c.isdigit() for c in segunda) or "S/N" in segunda.upper():
                    numero = segunda
                    if len(partes) > 2:
                        complemento = " ".join(partes[2:])
                else:
                    # Se não for número, o endereço está confuso, joga no complemento
                    # ou talvez o bairro estava na mesma linha?
                    # Se o bairro ainda estiver vazio, tenta pegar daqui
                    if not bairro:
                        bairro = segunda
                    else:
                        complemento = " ".join(partes[1:])
            else:
                # Só tem 1 parte (ex: "Rua das Flores 123") sem virgula
                # Tenta achar o número com regex no final da string
                match_num = re.search(r'(\d+)$', logradouro)
                if match_num:
                    numero = match_num.group(1)
                    logradouro = logradouro.replace(numero, "").strip()

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
def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1,1,1])
        with col2:
            st.title("🔒 Login SGPWeb")
            senha = st.text_input("Senha:", type="password")
            if st.button("Entrar"):
                if senha == SENHA_DO_CLIENTE:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
        return

    st.title("🧠 Extrator SGPWeb (V10 Inteligente)")
    st.info("Sistema Dinâmico: Detecta Rua longa e separa Bairro automaticamente.")

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
            
            st.success(f"✅ {len(df)} Pedidos extraídos!")
            st.dataframe(df.head())
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV", csv, "importacao_sgpweb_v10.csv", "text/csv")
        else:
            st.warning("Nenhum pedido encontrado.")

if __name__ == "__main__":
    main()