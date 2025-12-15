import streamlit as st
import pdfplumber
import pandas as pd
import re
import sys

# --- CONFIGURAÇÃO INICIAL (Obrigatório ser a primeira linha executável) ---
try:
    st.set_page_config(page_title="SGPWeb Extrator V7", page_icon="📦", layout="wide")
except Exception as e:
    # Se der erro aqui, é porque algo rodou antes. Ignorar.
    pass

# --- SEGURANÇA ---
SENHA_DO_CLIENTE = "cliente2025" 

# --- PADRÕES ---
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

# --- FUNÇÕES DE LÓGICA (CORE) ---

def remover_duplicidade_linha(texto):
    """
    Remove texto espelhado. Ex: 'Maria Silva Maria Silva' -> 'Maria Silva'
    """
    if not texto or len(texto) < 3: return texto
    texto = texto.strip()
    
    # Tentativa 1: Divisão exata por palavras
    palavras = texto.split()
    n = len(palavras)
    
    if n > 1 and n % 2 == 0:
        meio = n // 2
        parte1 = palavras[:meio]
        parte2 = palavras[meio:]
        
        # Compara ignorando maiúsculas/minúsculas
        if [p.lower() for p in parte1] == [p.lower() for p in parte2]:
            return " ".join(palavras[:meio])

    # Tentativa 2: Regex para colagens sem espaço (Ex: NomeNome)
    try:
        match = re.match(r'^(.+?)\s*\1$', texto, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except:
        pass

    return texto

def processar_pagina(page):
    """Lê a página e limpa linha por linha."""
    try:
        text = page.extract_text()
    except Exception:
        return []

    if not text: return []

    linhas = text.split('\n')
    dados_uteis = []
    capturando = False
    
    for linha in linhas:
        linha = linha.strip()
        
        # Gatilho de Início
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue
        
        if capturando:
            # Gatilhos de Fim
            termos_fim = ["PEDIDO #", "SPA COSMETICS", "OBSERVAÇÕES", "SPAC OSMETICS"]
            if any(x in linha.upper() for x in termos_fim):
                break
            
            # Limpeza bruta
            linha_limpa = linha.replace("COBRAR DE", "").strip()
            
            # Limpeza inteligente (Duplicidade)
            linha_deduplicada = remover_duplicidade_linha(linha_limpa)
            
            if linha_deduplicada:
                dados_uteis.append(linha_deduplicada)
            
    return dados_uteis

def separar_endereco(linhas):
    """Separa os campos baseados na estrutura do SGPWeb."""
    if not linhas: return None
    
    try:
        # 1. Nome (Sempre a primeira linha limpa)
        nome = linhas[0]
        
        # 2. CPF (Procura linha com 11 digitos)
        cpf = ""
        idx_cpf = -1
        regex_cpf = r'\d{11}'
        
        for i, l in enumerate(linhas):
            digitos = re.sub(r'\D', '', l)
            # CPF normal ou CPF duplicado (22 digitos)
            if len(digitos) == 11:
                cpf = digitos
                idx_cpf = i
                break
            elif len(digitos) == 22 and digitos[:11] == digitos[11:]:
                cpf = digitos[:11]
                idx_cpf = i
                break
        
        # Fallback se não achar CPF
        if idx_cpf == -1: idx_cpf = 1
        
        # 3. CEP/Cidade/UF (Procura de baixo pra cima)
        cidade = ""
        uf = ""
        cep = ""
        idx_cidade = -1
        
        for i in range(len(linhas)-1, idx_cpf, -1):
            l = linhas[i]
            # Regex de CEP
            match = re.search(r'\d{5}-?\d{3}', l)
            if match:
                cep = match.group(0).replace('-', '')
                idx_cidade = i
                
                # Tenta extrair Cidade e UF que vem antes do CEP
                resto = l.split(match.group(0))[0].strip().strip(',').strip()
                if len(resto) > 2:
                    uf = resto[-2:]
                    cidade = resto[:-2].strip()
                break
        
        # 4. Endereço (O miolo entre CPF e Cidade)
        logradouro = ""
        numero = ""
        complemento = ""
        bairro = ""
        
        if idx_cidade > idx_cpf:
            # Pega as linhas do meio
            linhas_meio = linhas[idx_cpf+1 : idx_cidade]
            texto_full = ", ".join(linhas_meio)
            partes = [p.strip() for p in texto_full.split(',')]
            
            if len(partes) > 0:
                logradouro = partes[0]
                
                if len(partes) > 1:
                    segunda = partes[1]
                    # Se parece número
                    if any(c.isdigit() for c in segunda) or "S/N" in segunda.upper():
                        numero = segunda
                        if len(partes) > 2:
                            complemento = " ".join(partes[2:])
                    else:
                        # Se não parece número, deve ser bairro ou parte da rua
                        bairro = segunda
                        if len(partes) > 2: complemento = partes[2]
            
            # Ajuste fino para Bairro se estiver vazio e tiver muitas partes
            if not bairro and len(partes) >= 3 and not complemento:
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
    except Exception as e:
        print(f"Erro ao processar pedido de {linhas[0] if linhas else '?'}: {e}")
        return None

# --- APP STREAMLIT ---

def main():
    # Login
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

    # Tela Principal
    st.title("📦 Extrator SGPWeb V7 (Verificado)")
    st.markdown("---")

    uploaded_file = st.file_uploader("Arraste o PDF de Pedidos", type="pdf")

    if uploaded_file:
        st.info("Processando arquivo... Aguarde.")
        lista_pedidos = []
        
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                bar = st.progress(0)
                total_paginas = len(pdf.pages)
                
                for i, page in enumerate(pdf.pages):
                    bar.progress((i + 1) / total_paginas)
                    
                    linhas = processar_pagina(page)
                    if linhas:
                        pedido = separar_endereco(linhas)
                        if pedido and pedido["NOME_DESTINATARIO"]:
                            lista_pedidos.append(pedido)
                            
        except Exception as e:
            st.error(f"Erro crítico ao ler o PDF: {e}")
            return

        if lista_pedidos:
            df = pd.DataFrame(lista_pedidos)
            
            # Garantir colunas
            cols = ["NOME_DESTINATARIO", "CPF_CNPJ", "ENDERECO", "NUMERO", 
                    "COMPLEMENTO", "BAIRRO", "CIDADE", "UF", "CEP", 
                    "PESO", "VALOR_DECLARADO", "SERVICO"]
            
            for col in cols:
                if col not in df.columns: df[col] = ""
            
            df = df[cols]
            
            st.success(f"✅ {len(df)} Pedidos extraídos com sucesso!")
            st.dataframe(df.head())
            
            # Botão Download
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button(
                label="⬇️ Baixar CSV para Importação",
                data=csv,
                file_name="importacao_sgpweb.csv",
                mime="text/csv"
            )
        else:
            st.warning("⚠️ Nenhum pedido encontrado. Verifique se o PDF é de texto selecionável.")

if __name__ == "__main__":
    main()