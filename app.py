import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="SGPWeb Pro", page_icon="📦", layout="centered")

# --- SEGURANÇA (TRAVA DE PAGAMENTO) ---
SENHA_DO_CLIENTE = "cliente2025"  # <--- MUDE AQUI A SENHA SE O CLIENTE NÃO PAGAR

def check_login():
    """Garante que apenas quem tem a senha acesse o sistema."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔒 Acesso Restrito")
    st.markdown("Este sistema é privado. Insira sua chave de acesso.")
    
    senha = st.text_input("Senha:", type="password")
    if st.button("Entrar"):
        if senha == SENHA_DO_CLIENTE:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta. Entre em contato com o administrador.")
    return False

# --- MOTOR DE EXTRAÇÃO (INTELIGÊNCIA) ---
def limpar_texto(texto):
    """Remove quebras de linha extras e espaços desnecessários."""
    if not texto: return ""
    return texto.replace('\n', ' ').strip()

def extrair_dados_pdf(pdf_file):
    pedidos = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                # --- TENTATIVA 1: TABELAS (Mais preciso para páginas complexas) ---
                tabelas = page.extract_tables()
                tabela_encontrada = False
                
                for tabela in tabelas:
                    # Procura tabela que tenha "ENVIAR PARA" no cabeçalho ou primeira linha
                    if tabela and len(tabela) > 0:
                        # Achata a tabela para string para buscar a palavra chave
                        texto_tabela = str(tabela).upper()
                        if "ENVIAR PARA" in texto_tabela:
                            # Geralmente a coluna 0 é o Enviar Para
                            # Vamos pegar o conteúdo da célula abaixo do cabeçalho
                            try:
                                celula_dados = tabela[1][0] # Linha 2, Coluna 1
                            except:
                                continue # Estrutura estranha, pula
                                
                            if celula_dados:
                                linhas = celula_dados.split('\n')
                                dados_pedido = processar_linhas(linhas)
                                if dados_pedido['Nome']: # Só adiciona se achou nome
                                    tabela_encontrada = True
                                    dados_pedido['Pagina'] = i + 1
                                    pedidos.append(dados_pedido)

                # --- TENTATIVA 2: TEXTO CORRIDO (Se não achou tabela) ---
                if not tabela_encontrada:
                    texto = page.extract_text()
                    if texto:
                        # Regex captura tudo entre "ENVIAR PARA" e "COBRAR DE" (ou +55, ou Brasil)
                        # Adaptado para o layout do seu PDF
                        match = re.search(r'ENVIAR PARA\s+(.*?)\s+(?:COBRAR DE|\+55\d{10,11})', texto, re.DOTALL)
                        if match:
                            bloco = match.group(1).strip()
                            linhas = bloco.split('\n')
                            dados_pedido = processar_linhas(linhas)
                            
                            # Tenta achar telefone fora do bloco se não veio junto
                            if not dados_pedido['Telefone']:
                                match_tel = re.search(r'\+55\d{10,11}', texto)
                                if match_tel:
                                    dados_pedido['Telefone'] = match_tel.group(0)
                            
                            dados_pedido['Pagina'] = i + 1
                            pedidos.append(dados_pedido)

            except Exception as e:
                # Se der erro em uma página, não para tudo, apenas segue
                print(f"Erro na página {i+1}: {e}")
                continue

    return pd.DataFrame(pedidos)

def processar_linhas(linhas_brutas):
    """Lógica comum para limpar e identificar Nome, CPF e Endereço das linhas."""
    nome = ""
    cpf = ""
    cep = ""
    endereco_parts = []
    telefone = ""
    
    regex_cpf = r'\d{11}'
    regex_cep = r'\d{5}-\d{3}'
    
    for linha in linhas_brutas:
        linha = linha.strip()
        if not linha or linha == "Brasil": continue
        
        # Identifica CPF
        if re.match(regex_cpf, linha.replace('.', '').replace('-', '')):
            cpf = linha
            continue
            
        # Identifica CEP
        match_cep = re.search(regex_cep, linha)
        if match_cep:
            cep = match_cep.group(0)
            endereco_parts.append(linha) # Mantém a linha do CEP no endereço (tem cidade/UF)
            continue
            
        # Identifica Telefone no meio das linhas
        if "+55" in linha:
            telefone = linha
            continue
            
        # O que sobra: Primeira linha é Nome, resto é Endereço
        if not nome:
            nome = linha
        else:
            endereco_parts.append(linha)
            
    return {
        "Nome": nome,
        "CPF": cpf,
        "Telefone": telefone,
        "CEP": cep,
        "Endereço Completo": ", ".join(endereco_parts),
        "Email": "cliente@email.com" # Placeholder padrão
    }

# --- INTERFACE DO USUÁRIO ---
if check_login():
    st.title("📦 Conversor PDF -> SGPWeb")
    st.markdown("### Automatize sua importação de pedidos")
    st.info("💡 Arraste o PDF de vendas aqui. O sistema extrairá Nome, Endereço e CPF automaticamente.")
    
    uploaded_file = st.file_uploader("Upload do PDF", type="pdf")
    
    if uploaded_file:
        with st.spinner("Lendo arquivo... Isso pode levar alguns segundos."):
            df_resultado = extrair_dados_pdf(uploaded_file)
            
            if not df_resultado.empty:
                st.success(f"✅ Sucesso! {len(df_resultado)} pedidos encontrados.")
                
                # Mostra prévia
                st.dataframe(df_resultado.head())
                
                # Botão de Download
                csv_buffer = df_resultado.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Baixar CSV para SGPWeb",
                    data=csv_buffer,
                    file_name="importacao_sgpweb.csv",
                    mime="text/csv"
                )
            else:
                st.warning("⚠️ Não conseguimos identificar pedidos neste PDF. Verifique se é o arquivo correto.")

    st.markdown("---")
    st.caption("Sistema v1.0 | Protegido por Senha")