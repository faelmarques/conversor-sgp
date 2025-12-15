import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="SGPWeb V12 (Varredura Total)", page_icon="🔥", layout="wide")

SENHA_DO_CLIENTE = "cliente2025" 
PADRAO_PESO = "0.050"
PADRAO_VALOR = "150.00"
PADRAO_SERVICO = "PAC"

# --- FUNÇÕES CORE ---

def limpar_linha_duplicada(texto):
    """Remove repetição exata (Ex: 'Maria Maria' -> 'Maria')"""
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

def extrair_pedidos_varredura(page):
    """
    ESTRATÉGIA V12:
    1. Corta a página ao meio (Esquerda).
    2. Divide o texto inteiro por 'ENVIAR PARA'.
    3. Processa cada bloco independentemente.
    """
    try:
        width = page.width
        height = page.height
        # Corta metade esquerda para evitar duplicidade do 'Cobrar De'
        bbox = (0, 0, width / 2 + 20, height)
        crop = page.crop(bbox)
        text = crop.extract_text()
    except:
        return []

    if not text: return []

    # O PULO DO GATO: Divide o texto em blocos baseados no gatilho
    # O regex split mantém o delimitador se usar parênteses, mas aqui queremos dividir mesmo.
    # Usamos case insensitive flag
    blocos = re.split(r'ENVIAR PARA', text, flags=re.IGNORECASE)
    
    # O primeiro bloco (blocos[0]) geralmente é cabeçalho da página (lixo antes do primeiro pedido)
    # Ignoramos ele. Processamos do 1 em diante.
    pedidos_brutos = []
    
    for bloco in blocos[1:]:
        linhas_bloco = bloco.split('\n')
        linhas_limpas = []
        
        for linha in linhas_bloco:
            linha = linha.strip()
            if not linha: continue
            
            # Critérios de parada DENTRO do bloco (fim do pedido atual)
            # Se encontrar isso, paramos de ler este bloco específico
            termos_fim = ["SPA COSMETICS", "OBSERVAÇÕES", "SPAC OSMETICS", "COBRAR DE", "PEDIDO #"]
            
            # Se a linha for EXATAMENTE um termo de fim, para.
            # Se a linha CONTIVER um termo de fim, limpamos e paramos.
            parar_bloco = False
            for termo in termos_fim:
                if termo in linha.upper():
                    # Às vezes o termo está no final da linha válida. 
                    # Mas na dúvida, vamos considerar que aqui acaba o endereço.
                    parar_bloco = True
                    break
            
            if parar_bloco:
                break
            
            # Limpeza de duplicidade
            l_final = limpar_linha_duplicada(linha)
            if l_final:
                linhas_limpas.append(l_final)
        
        if linhas_limpas:
            pedidos_brutos.append(linhas_limpas)
            
    return pedidos_brutos

def separar_endereco_inteligente(linhas):
    if not linhas: return None

    # 1. Nome (Primeira linha do bloco)
    nome = linhas[0]
    
    # 2. CPF (Procura linha com 11 digitos)
    idx_cpf = -1
    cpf = ""
    for i, l in enumerate(linhas):
        digitos = re.sub(r'\D', '', l)
        # CPF 11 ou duplicado 22
        if len(digitos) == 11 or (len(digitos) == 22 and digitos[:11] == digitos[11:]):
            cpf = digitos[:11]
            idx_cpf = i
            break
            
    # 3. CEP (De baixo pra cima)
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
            # Cidade/UF
            resto = l.split(match.group(0))[0].strip().strip(',').strip()
            if len(resto) > 2:
                uf = resto[-2:]
                cidade = resto[:-2].strip().strip('-')
            else:
                cidade = resto
            break

    # Se não achou âncoras, tenta heurística simples
    if idx_cpf == -1: idx_cpf = 1 # Assume linha 2 é CPF se falhar
    if idx_cep == -1: idx_cep = len(linhas) # Pega tudo até o fim se falhar

    # 4. Endereço (Miolo)
    # Garante índices válidos
    inicio = idx_cpf + 1
    fim = idx_cep
    if inicio >= len(linhas): inicio = 1 # Fallback
    
    linhas_recheio = linhas[inicio : fim]
    
    logradouro = ""
    numero = ""
    complemento = ""
    bairro = ""
    
    if linhas_recheio:
        # Lógica V10: Última linha do recheio é Bairro
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
                # Regex número no fim
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

    st.title("🔥 Extrator SGPWeb V12 (Varredura Total)")
    st.info("Esta versão captura TODOS os pedidos da página, mesmo que sejam vários.")

    uploaded_file = st.file_uploader("Arraste o PDF", type="pdf")

    if uploaded_file:
        pedidos = []
        with pdfplumber.open(uploaded_file) as pdf:
            bar = st.progress(0)
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                bar.progress((i+1)/total)
                
                # Retorna LISTA de LISTAS (vários pedidos por página)
                lista_de_blocos = extrair_pedidos_varredura(page)
                
                for bloco_linhas in lista_de_blocos:
                    p = separar_endereco_inteligente(bloco_linhas)
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
            
            st.success(f"✅ {len(df)} Pedidos extraídos!")
            st.dataframe(df.head())
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV", csv, "importacao_varredura.csv", "text/csv")
        else:
            st.warning("Nenhum pedido encontrado.")

if __name__ == "__main__":
    main()
