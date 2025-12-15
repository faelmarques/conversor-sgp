import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="SGPWeb Pro - Extrator Limpo", page_icon="📦", layout="centered")

# --- SEGURANÇA ---
SENHA_DO_CLIENTE = "cliente2025" 

def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.title("🔒 Acesso Restrito")
    senha = st.text_input("Senha:", type="password")
    if st.button("Entrar"):
        if senha == SENHA_DO_CLIENTE:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    return False

# --- MOTOR DE EXTRAÇÃO CIRÚRGICA ---
def limpar_linha(linha):
    """Remove caracteres indesejados e espaços extras."""
    return linha.strip()

def processar_bloco_texto(texto_bruto):
    """
    Recebe o texto cru da página e isola APENAS o bloco entre 
    'ENVIAR PARA' e 'COBRAR DE'.
    """
    try:
        # 1. Tenta achar onde começa o envio
        if "ENVIAR PARA" not in texto_bruto:
            return None
        
        # Pega tudo DEPOIS de "ENVIAR PARA"
        parte_1 = texto_bruto.split("ENVIAR PARA")[1]
        
        # 2. Tenta achar onde termina (no "COBRAR DE" ou "+55" ou "Brasil")
        # A prioridade é cortar no "COBRAR DE" para evitar duplicidade
        if "COBRAR DE" in parte_1:
            bloco_limpo = parte_1.split("COBRAR DE")[0]
        else:
            # Caso de fallback se não tiver Cobrar De
            bloco_limpo = parte_1
            
        # Transforma em lista de linhas removendo linhas vazias
        linhas = [limpar_linha(l) for l in bloco_limpo.split('\n') if limpar_linha(l)]
        
        return linhas
    except:
        return None

def extrair_dados_pdf(pdf_file):
    pedidos = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            texto = page.extract_text()
            if not texto: continue
            
            linhas_do_bloco = processar_bloco_texto(texto)
            
            if linhas_do_bloco and len(linhas_do_bloco) > 2:
                # --- LÓGICA DE ATRIBUIÇÃO POSICIONAL ---
                # Sabemos que no seu PDF a ordem é quase sempre:
                # Linha 0: Nome
                # Linha 1: CPF
                # Linhas seguintes: Endereço
                
                nome = linhas_do_bloco[0] # A primeira linha é o nome
                cpf = ""
                cep = ""
                telefone = ""
                endereco_parts = []
                
                # Regex patterns
                regex_cpf = r'\d{11}'
                regex_cep = r'\d{5}-?\d{3}'
                
                # Começamos a varrer da segunda linha em diante (índice 1)
                for linha in linhas_do_bloco[1:]:
                    # Se for CPF
                    if re.match(regex_cpf, linha.replace('.', '').replace('-', '').strip()):
                        cpf = linha.strip() # Pega e não adiciona no endereço
                        continue
                        
                    # Se for CEP (Isso geralmente contém Cidade e UF também)
                    if re.search(regex_cep, linha):
                        match_cep = re.search(regex_cep, linha)
                        if match_cep:
                            cep = match_cep.group(0)
                        # O SGPWeb costuma pedir Cidade/UF separados, mas o endereço completo ajuda
                        # Vamos manter essa linha no endereço para garantir que Cidade/UF vá junto
                        endereco_parts.append(linha) 
                        continue
                    
                    # Se for telefone (começa com +55 ou tem formato de cel)
                    if "+55" in linha or re.search(r'\(\d{2}\)', linha):
                        telefone = linha.replace('Brasil', '').strip()
                        continue
                        
                    # Se não for nada disso, é parte do endereço (Rua, Bairro, etc)
                    if "Brasil" not in linha: # Remove a palavra Brasil solta
                        endereco_parts.append(linha)

                # Busca telefone fora do bloco se não achou dentro (backup)
                if not telefone:
                    match_tel = re.search(r'\+55\d{10,11}', texto)
                    if match_tel:
                        telefone = match_tel.group(0)

                # Monta o objeto final
                pedidos.append({
                    "Nome": nome, # Agora garantido ser a primeira linha
                    "CPF": cpf,   # Agora garantido ser único
                    "Telefone": telefone,
                    "CEP": cep,
                    "Endereço": ", ".join(endereco_parts), # Endereço limpo sem o nome
                    "Email": "cliente@email.com" # Padrão para não dar erro na importação
                })

    return pd.DataFrame(pedidos)

# --- INTERFACE ---
if check_login():
    st.title("📦 Conversor SGPWeb Pro v2.0")
    st.info("Algoritmo ajustado: Remove duplicidades de Nome e CPF.")
    
    uploaded_file = st.file_uploader("Arraste o PDF aqui", type="pdf")
    
    if uploaded_file:
        df = extrair_dados_pdf(uploaded_file)
        
        if not df.empty:
            st.success(f"{len(df)} pedidos processados com sucesso!")
            st.dataframe(df) # Mostra a tabela para conferência visual
            
            csv = df.to_csv(index=False, sep=";").encode('utf-8') # Usei ; que é mais seguro para Excel/SGPWeb BR
            st.download_button("Baixar CSV Corrigido", csv, "importacao_sgpweb_v2.csv", "text/csv")
        else:
            st.warning("Nenhum pedido encontrado. Verifique se o PDF está legível.")