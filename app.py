import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO ---
try:
    st.set_page_config(page_title="SGPWeb Final", page_icon="✅", layout="wide")
except:
    pass

SENHA_DO_CLIENTE = "cliente2025" 
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

def limpar_sujeira(texto):
    """Remove especificamente a sujeira que está aparecendo no nome."""
    if not texto: return ""
    # Remove a frase maldita se ela aparecer colada
    texto = texto.replace("COBRAR DE", "").replace("COBRAR", "").strip()
    return texto

def processar_pagina_geometrica(page):
    """
    Corta a página fisicamente antes de ler o texto.
    Ignora tudo que está depois de 55% da largura da página.
    """
    width = page.width
    height = page.height
    
    # Define a caixa de corte: (x0, top, x1, bottom)
    # Cortamos um pouco mais da metade (width * 0.55) para garantir
    bbox = (0, 0, width * 0.55, height)
    
    try:
        # Força o corte. O lado direito deixa de existir.
        crop = page.crop(bbox)
        text = crop.extract_text()
    except:
        return []

    if not text: return []

    linhas = text.split('\n')
    dados_limpos = []
    capturando = False
    
    for linha in linhas:
        # Limpeza PREVENTIVA linha a linha
        linha = limpar_sujeira(linha)
        if not linha: continue

        # Gatilho de inicio
        if "ENVIAR PARA" in linha.upper():
            capturando = True
            continue # Pula a linha "ENVIAR PARA"
            
        if capturando:
            # Se encontrar cabeçalhos ou rodapés, para.
            if any(x in linha.upper() for x in ["PEDIDO #", "SPA COSMETICS", "OBSERVAÇÕES", "SPAC OSMETICS"]):
                break
            
            # Se a linha não for vazia, guarda
            dados_limpos.append(linha)
            
    return dados_limpos

def estruturar_pedido(linhas):
    # Precisa ter dados mínimos
    if not linhas or len(linhas) < 4: return None
    
    try:
        # --- LINHA 0: NOME (Blindado) ---
        nome = linhas[0]
        # Dupla checagem para garantir que o nome não é "COBRAR DE"
        if "COBRAR" in nome.upper(): 
            return None # Lixo de leitura

        # --- LINHA 1: CPF ---
        cpf_sujo = linhas[1]
        cpf = re.sub(r'\D', '', cpf_sujo)[:11]

        # --- LINHA 2: ENDEREÇO (Rua, Numero, Complemento) ---
        # Ex: Rua tubarão, 801
        # Ex: Rua Genésio Passoni Moreira, 160, Casa
        end_linha = linhas[2]
        partes = [p.strip() for p in end_linha.split(',')]
        
        logradouro = partes[0]
        numero = ""
        complemento = ""
        
        if len(partes) > 1:
            segunda = partes[1]
            # Se a segunda parte tem numero ou é S/N
            if any(c.isdigit() for c in segunda) or "S/N" in segunda.upper():
                numero = segunda
                if len(partes) > 2:
                    complemento = " ".join(partes[2:])
            else:
                # Se não tem numero, o endereço está bagunçado ou o numero está na parte 1
                # Vamos assumir que se não é numero, é complemento/bairro mal posicionado
                if not numero: numero = "S/N"
                complemento = " ".join(partes[1:])
        
        # --- LINHA 3: BAIRRO (Fixo, conforme seu padrão) ---
        bairro = linhas[3]
        
        # --- LINHA 4 (ou 5): CIDADE/UF/CEP ---
        # Procura a linha que tem o CEP
        cidade = ""
        uf = ""
        cep = ""
        
        # Varre as linhas restantes procurando o CEP
        for l in linhas[3:]:
            match_cep = re.search(r'\d{5}-?\d{3}', l)
            if match_cep:
                cep = match_cep.group(0).replace('-', '')
                resto = l.split(match_cep.group(0))[0].strip().strip(',').strip()
                if len(resto) > 2:
                    uf = resto[-2:]
                    cidade = resto[:-2].strip().strip('-')
                else:
                    cidade = resto
                break
                
        # Se não achou cidade na linha do CEP, tenta pegar da linha anterior ao CEP (caso raro)
        if not cidade and len(linhas) > 4:
            # Fallback
            pass

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

    except:
        return None

# --- APP ---
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

    st.title("📦 Extrator SGPWeb (Geometria Fixa)")
    st.warning("Esta versão corta a página ao meio para impedir leitura do lado direito.")

    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")

    if uploaded_file:
        pedidos = []
        with pdfplumber.open(uploaded_file) as pdf:
            bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                bar.progress((i+1)/len(pdf.pages))
                
                # Usa o processador geométrico
                linhas = processar_pagina_geometrica(page)
                
                if linhas:
                    p = estruturar_pedido(linhas)
                    if p and p["NOME_DESTINATARIO"]:
                        pedidos.append(p)
        
        if pedidos:
            df = pd.DataFrame(pedidos)
            cols = ["NOME_DESTINATARIO", "CPF_CNPJ", "ENDERECO", "NUMERO", 
                    "COMPLEMENTO", "BAIRRO", "CIDADE", "UF", "CEP", 
                    "PESO", "VALOR_DECLARADO", "SERVICO"]
            for c in cols: 
                if c not in df.columns: df[c] = ""
            df = df[cols]
            
            st.success(f"✅ {len(df)} Pedidos limpos extraídos!")
            st.dataframe(df.head())
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV", csv, "importacao_final.csv", "text/csv")
        else:
            st.error("Nenhum pedido legível encontrado.")

if __name__ == "__main__":
    main()
