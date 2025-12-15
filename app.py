import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="SGPWeb Extrator V6 (Anti-Duplicidade)", page_icon="🧹", layout="wide")
SENHA_DO_CLIENTE = "cliente2025" 

# --- VALORES PADRÃO ---
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

# --- MOTOR DE LIMPEZA DE DUPLICATAS ---

def remover_duplicidade_linha(texto):
    """
    Detecta se o texto é uma repetição exata dele mesmo (ex: 'Maria Maria')
    e retorna apenas uma ocorrência.
    """
    if not texto or len(texto) < 3: return texto
    texto = texto.strip()
    
    # Estratégia 1: Divisão por palavras (Espelho Perfeito)
    # Ex: "Vivian Fernandes Vivian Fernandes" -> ['Vivian', 'Fernandes', 'Vivian', 'Fernandes']
    palavras = texto.split()
    n = len(palavras)
    
    # Se o número de palavras for par, pode ser uma duplicação
    if n > 1 and n % 2 == 0:
        meio = n // 2
        parte1 = palavras[:meio]
        parte2 = palavras[meio:]
        
        # Compara as listas de palavras (ignorando case)
        if [p.lower() for p in parte1] == [p.lower() for p in parte2]:
            return " ".join(palavras[:meio])

    # Estratégia 2: Regex para repetição colada (caso o PDF coma os espaços)
    # Ex: "Vivian FernandesVivian Fernandes"
    match = re.match(r'^(.+?)\s*\1$', texto, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return texto

def processar_pagina_inteira(page):
    """Lê a página inteira e limpa linha por linha."""
    text = page.extract_text()
    if not text: return []

    linhas = text.split('\n')
    dados_uteis = []
    capturando = False
    
    for linha in linhas:
        linha = linha.strip()
        
        # Lógica de Gatilho
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue
        
        if capturando:
            # Critérios de parada
            if any(x in linha.upper() for x in ["PEDIDO #", "SPA COSMETICS", "OBSERVAÇÕES"]):
                break
            
            # Remove cabeçalho duplicado que as vezes aparece na mesma linha
            linha_limpa = linha.replace("COBRAR DE", "").strip()
            
            # APLICA A LIMPEZA DE DUPLICIDADE AQUI
            linha_deduplicada = remover_duplicidade_linha(linha_limpa)
            
            if linha_deduplicada:
                dados_uteis.append(linha_deduplicada)
            
    return dados_uteis

def separar_endereco(linhas):
    if not linhas: return None
    
    # 1. Nome (Linha 1 limpa)
    nome = linhas[0]
    
    # 2. CPF (Busca e limpa)
    cpf = ""
    idx_cpf = -1
    for i, l in enumerate(linhas):
        # Remove pontos e traços para contar dígitos
        digitos = re.sub(r'\D', '', l)
        
        # Se tiver 11 dígitos (CPF normal) ou 22 dígitos (CPF duplicado que passou pelo filtro)
        if len(digitos) == 11:
            cpf = digitos
            idx_cpf = i
            break
        elif len(digitos) == 22 and digitos[:11] == digitos[11:]:
            cpf = digitos[:11] # Pega só a metade
            idx_cpf = i
            break
            
    if idx_cpf == -1: idx_cpf = 1 # Fallback
    
    # 3. CEP, Cidade, UF
    cidade = ""
    uf = ""
    cep = ""
    idx_cidade = -1
    regex_cep = r'\d{5}-?\d{3}'
    
    for i in range(len(linhas)-1, idx_cpf, -1):
        l = linhas[i]
        match_cep = re.search(regex_cep, l)
        if match_cep:
            cep = match_cep.group(0).replace('-', '')
            idx_cidade = i
            
            resto = l.split(match_cep.group(0))[0].strip().strip(',').strip()
            if len(resto) > 2:
                uf = resto[-2:]
                cidade = resto[:-2].strip()
            break
            
    # 4. Endereço (Rua, Numero, Bairro)
    logradouro = ""
    numero = ""
    complemento = ""
    bairro = ""
    
    if idx_cidade > idx_cpf:
        # Pega as linhas entre o CPF e a Cidade
        linhas_meio = linhas[idx_cpf+1 : idx_cidade]
        
        # Junta tudo numa string só para facilitar a separação por vírgula
        texto_endereco_completo = ", ".join(linhas_meio)
        
        # Separação bruta por vírgula
        partes = [p.strip() for p in texto_endereco_completo.split(',')]
        
        if len(partes) > 0:
            logradouro = partes[0]
            
            # Tenta achar o número
            if len(partes) > 1:
                # O número geralmente é a segunda parte. 
                # Mas às vezes o bairro vem antes ou depois.
                # Vamos assumir: Rua, Numero, Complemento, Bairro (ou Bairro, Cidade...)
                
                segunda_parte = partes[1]
                # Verifica se a segunda parte parece um número (tem digitos) ou "S/N"
                if any(char.isdigit() for char in segunda_parte) or "S/N" in segunda_parte.upper():
                    numero = segunda_parte
                    
                    if len(partes) > 2:
                        # Se tem mais partes, o resto pode ser complemento ou bairro
                        # Se a última parte não for igual a cidade/uf (já extraída), é o bairro
                        resto = " ".join(partes[2:])
                        # Heurística simples: se o resto for curto, é complemento (casa, apto). Se for longo, bairro.
                        if len(resto) < 15 or "CASA" in resto.upper() or "APTO" in resto.upper() or "FUNDOS" in resto.upper():
                            complemento = resto
                        else:
                            bairro = resto
                else:
                    # Se a segunda parte não parece número, talvez seja o bairro ou o numero esteja junto da rua
                    # Ex: Rua X 123, Bairro Y
                    bairro = segunda_parte
                    if len(partes) > 2: complemento = partes[2]
            
            # Fallback se bairro estiver vazio, tenta pegar da última parte se não for complemento
            if not bairro and not complemento and len(partes) > 2:
                bairro = partes[-1]

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
    st.title("📦 SGPWeb V6 (Final)")
    st.info("Algoritmo de espelhamento ativado: Remove textos duplicados na mesma linha.")
    
    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")
    
    if uploaded_file:
        lista_pedidos = []
        with pdfplumber.open(uploaded_file) as pdf:
            bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                bar.progress((i+1)/len(pdf.pages))
                
                linhas_limpas = processar_pagina_inteira(page)
                if linhas_limpas:
                    pedido = separar_endereco(linhas_limpas)
                    if pedido and pedido["NOME_DESTINATARIO"]:
                        lista_pedidos.append(pedido)

        if lista_pedidos:
            df = pd.DataFrame(lista_pedidos)
            cols = ["NOME_DESTINATARIO", "CPF_CNPJ", "ENDERECO", "NUMERO", 
                    "COMPLEMENTO", "BAIRRO", "CIDADE", "UF", "CEP", 
                    "PESO", "VALOR_DECLARADO", "SERVICO"]
            
            # Preenche colunas vazias
            for col in cols:
                if col not in df.columns: df[col] = ""
            
            df = df[cols]
            
            st.success(f"✅ {len(df)} Pedidos processados!")
            st.dataframe(df.head())
            
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV Importação", csv, "sgpweb_v6_final.csv", "text/csv")
        else:
            st.warning("Nenhum dado encontrado.")
