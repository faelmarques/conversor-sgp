import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="SGPWeb Extrator V3", page_icon="📦", layout="wide")
SENHA_DO_CLIENTE = "cliente2025" 

# --- LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_login():
    if st.session_state.authenticated: return True
    
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🔒 Acesso Restrito")
        senha = st.text_input("Senha de Acesso:", type="password")
        if st.button("Entrar"):
            if senha == SENHA_DO_CLIENTE:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False

# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO ---
def limpar_string(s):
    if not s: return ""
    return str(s).replace('\n', ' ').strip()

def extrair_de_tabela(page):
    """Estratégia 1: Tenta achar tabelas estruturadas (comum em páginas com colunas)"""
    tabelas = page.extract_tables()
    dados_encontrados = []
    
    for tabela in tabelas:
        for row in tabela:
            # Achata a linha para buscar palavras-chave
            texto_linha = " ".join([str(x) for x in row if x]).upper()
            
            # Se acharmos o cabeçalho na linha, pegamos a linha SEGUINTE
            if "ENVIAR PARA" in texto_linha:
                idx_linha = tabela.index(row)
                if idx_linha + 1 < len(tabela):
                    celula_dados = tabela[idx_linha + 1][0] # Assume coluna 0
                    if celula_dados:
                        linhas_texto = celula_dados.split('\n')
                        # Filtra linhas vazias
                        linhas_texto = [l.strip() for l in linhas_texto if l.strip()]
                        if len(linhas_texto) >= 2:
                             # Na tabela, geralmente linha 0 = Nome, Linha 1 = CPF/Endereço
                            dados_encontrados.append(linhas_texto)
    return dados_encontrados

def extrair_de_texto(page):
    """Estratégia 2: Regex flexível no texto bruto"""
    texto = page.extract_text()
    if not texto: return None, "Página Vazia (Imagem?)"

    # Regex que procura 'ENVIAR PARA' mesmo com quebra de linha (ENVIAR\nPARA)
    # e captura tudo até 'COBRAR DE' ou um telefone
    padrao = r'ENVIAR\s*PARA\s*(.*?)\s*(?:COBRAR\s*DE|\+55\d{10,11}|Brasil\s*\+55)'
    match = re.search(padrao, texto, re.DOTALL | re.IGNORECASE)
    
    if match:
        bloco = match.group(1)
        linhas = [l.strip() for l in bloco.split('\n') if l.strip()]
        return linhas, texto # Retorna as linhas e o texto bruto para debug
    
    return [], texto

def processar_linhas_para_pedido(linhas):
    """Transforma uma lista de linhas sujas em um objeto de pedido limpo"""
    if not linhas: return None
    
    nome = linhas[0] # Primeira linha é quase sempre o nome
    cpf = ""
    cep = ""
    telefone = ""
    endereco_parts = []
    
    # Remove duplicidade se o nome aparecer de novo no endereço
    linhas_limpas = []
    for l in linhas[1:]:
        if nome.lower() not in l.lower(): # Só adiciona se não for repetição do nome
            linhas_limpas.append(l)

    # Processa o restante
    for linha in linhas_limpas:
        # CPF
        if re.search(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', linha):
            # Extrai apenas os números do CPF
            nums = re.findall(r'\d', linha)
            if len(nums) == 11:
                cpf = "".join(nums)
                continue # Não adiciona CPF ao endereço
        
        # CEP
        match_cep = re.search(r'\d{5}-?\d{3}', linha)
        if match_cep:
            cep = match_cep.group(0)
            endereco_parts.append(linha) # Mantém linha do CEP (cidade/UF)
            continue
            
        # Telefone
        if "+55" in linha or re.search(r'\(\d{2}\)\s?9?\d{4}-\d{4}', linha):
            telefone = linha.replace("Brasil", "").strip()
            continue
            
        # Endereço (o que sobrou)
        if len(linha) > 3 and "Brasil" not in linha:
            endereco_parts.append(linha)

    return {
        "Nome": nome,
        "CPF": cpf,
        "Telefone": telefone,
        "CEP": cep,
        "Endereço": ", ".join(endereco_parts),
        "Email": "cliente@email.com"
    }

# --- APP PRINCIPAL ---
if check_login():
    st.title("📦 Extrator SGPWeb Pro V3.0 (Híbrido)")
    st.markdown("---")
    
    uploaded_file = st.file_uploader("Arraste seu PDF aqui", type="pdf")
    
    if uploaded_file:
        pedidos_finais = []
        debug_info = [] # Para armazenar logs de erro
        
        with pdfplumber.open(uploaded_file) as pdf:
            barra = st.progress(0)
            
            for i, page in enumerate(pdf.pages):
                barra.progress((i + 1) / len(pdf.pages))
                
                # 1. Tenta via Tabela (Prioridade)
                blocos_tabela = extrair_de_tabela(page)
                if blocos_tabela:
                    for linhas in blocos_tabela:
                        p = processar_linhas_para_pedido(linhas)
                        if p: 
                            p['Origem'] = f"Pág {i+1} (Tabela)"
                            pedidos_finais.append(p)
                    continue # Se achou tabela, vai pra próxima página

                # 2. Se não achou tabela, tenta Texto Corrido
                linhas_texto, texto_bruto = extrair_de_texto(page)
                if linhas_texto:
                    p = processar_linhas_para_pedido(linhas_texto)
                    if p:
                        p['Origem'] = f"Pág {i+1} (Texto)"
                        pedidos_finais.append(p)
                else:
                    # Guarda info para debug se falhar
                    debug_info.append(f"Página {i+1}: Não achei padrão 'ENVIAR PARA'.\nTexto inicial: {texto_bruto[:100]}...")

        # --- RESULTADOS ---
        if pedidos_finais:
            df = pd.DataFrame(pedidos_finais)
            st.success(f"✅ Sucesso! {len(df)} pedidos extraídos.")
            
            st.dataframe(df)
            
            csv = df.to_csv(index=False, sep=";").encode('utf-8')
            st.download_button("⬇️ Baixar CSV (Ponto e Vírgula)", csv, "sgpweb_import.csv", "text/csv")
        else:
            st.error("❌ Nenhum pedido encontrado.")
            st.warning("O PDF pode ser uma imagem ou ter um layout desconhecido.")
            
            # --- ÁREA DE DEBUG (Salvadora) ---
            with st.expander("🛠️ CLIQUE AQUI SE DEU ERRO (Modo Debug)"):
                st.write("Envie o texto abaixo para o programador:")
                if debug_info:
                    st.text("\n---\n".join(debug_info))
                else:
                    st.write("O arquivo parece estar vazio ou criptografado.")