import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="BI Gerencial On-Demand", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("URL da Planilha Google")
drive_folder_id = st.sidebar.text_input("ID da Pasta no Drive (Opcional)")

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_credentials():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    except KeyError:
        st.error("⚠️ Credenciais não encontradas nos Secrets do Streamlit!")
        st.stop()

def get_google_client():
    return gspread.authorize(get_credentials())

def upload_to_drive(file, folder_id):
    try:
        gauth = GoogleAuth()
        gauth.credentials = get_credentials()
        drive = GoogleDrive(gauth)
        file_drive = drive.CreateFile({'title': file.name, 'parents': [{'id': folder_id}]})
        with open(file.name, "wb") as f:
            f.write(file.getbuffer())
        file_drive.SetContentFile(file.name)
        file_drive.Upload()
        os.remove(file.name)
        return file_drive['alternateLink']
    except Exception as e:
        return None

def limpeza_final(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s: return 0.0
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."): s = s.replace(".", "").replace(",", ".")
        else: s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return pd.to_numeric(s, errors='coerce') or 0.0

def formatar_moeda_br(valor):
    try:
        if pd.isna(valor): return "R$ 0,00"
        txt = f"{float(valor):,.2f}"
        txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {txt}"
    except:
        return "R$ 0,00"

# --- APLICATIVO PRINCIPAL ---
st.title("🚀 Construtor de Gráficos Gerenciais")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha Google na barra lateral para iniciar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "🛠️ Construtor de Gráficos (BI)"])

    # ==========================================
    # PROCESSAMENTO DE DADOS (MOTOR DE BI)
    # ==========================================
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
        raw_lanc = sheet.worksheet("Lancamentos").get_all_records()
        raw_budget = sheet.worksheet("Budget").get_all_records()
        
        df_lanc = pd.DataFrame(raw_lanc)
        df_budget = pd.DataFrame(raw_budget)
        
        # --- CRIANDO A TABELA FATO UNIVERSAL ---
        # 1. Preparar df do Budget
        df_b = pd.DataFrame()
        if not df_budget.empty:
            df_b["Competência"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_b["CONTA"] = df_budget.get("CONTA", pd.Series()).astype(str).str.strip()
            df_b["Categoria (Tipo 1)"] = df_budget.get("TIPO 1", pd.Series()).astype(str).str.strip()
            df_b["Orçado"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)
            df_b["Realizado"] = 0.0
            df_b["Fornecedor"] = "N/A (Apenas Budget)"

        # 2. Preparar df de Lançamentos
        df_l = pd.DataFrame()
        if not df_lanc.empty:
            df_l["Competência"] = pd.to_datetime(df_lanc.get("Data de lançamento"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_l["CONTA"] = df_lanc.get("Conta SAP", pd.Series()).astype(str).str.strip()
            df_l["Fornecedor"] = df_lanc.get("Nome do cliente/fornecedor", pd.Series()).astype(str).str.strip()
            df_l["Realizado"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            df_l["Orçado"] = 0.0
            
            # Mapeia a Categoria do Budget para o Lançamento usando a Conta
            if not df_b.empty:
                mapa_cat = df_b.drop_duplicates("CONTA").set_index("CONTA")["Categoria (Tipo 1)"].to_dict()
                df_l["Categoria (Tipo 1)"] = df_l["CONTA"].map(mapa_cat).fillna("Sem Categoria")
            else:
                df_l["Categoria (Tipo 1)"] = "Sem Categoria"

        # 3. Empilhar as bases para permitir qualquer agrupamento
        df_fato = pd.concat([df_b, df_l], ignore_index=True)

    except Exception as e:
        st.error("Erro ao carregar dados do Google Sheets. Verifique a URL.")
        df_fato = pd.DataFrame()

    # ==========================================
    # TAB 1: FORMULÁRIO DE ENTRADA
    # ==========================================
    with tab1:
        st.subheader("Novo Lançamento")
        with st.form("form_nf", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                nf_num = st.text_input("Nº NF")
                fornecedor = st.text_input("Fornecedor / Cliente")
            with col2:
                data_lanc = st.date_input("Data de lançamento")
                valor_bruto = st.number_input("Total da linha (R$)", min_value=0.0, format="%.2f")
            with col3:
                conta_sap = st.text_input("Conta SAP")
                arquivo_nf = st.file_uploader("Upload da NF", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento")

        if submit and nf_num and conta_sap:
            with st.spinner("Registrando nota..."):
                link_nf = upload_to_drive(arquivo_nf, drive_folder_id) if arquivo_nf and drive_folder_id else "Sem Anexo"
                try:
                    worksheet = sheet.worksheet("Lancamentos")
                    cabecalhos = worksheet.row_values(1)
                    nova_linha = [""] * len(cabecalhos)
                    
                    dados_para_inserir = {
                        "Nº NF": nf_num, "Nome do cliente/fornecedor": fornecedor,
                        "Data de lançamento": data_lanc.strftime("%d/%m/%Y"),
                        "Total documento": valor_bruto, "Total da linha": valor_bruto,
                        "Conta SAP": conta_sap, "Referência da Nota Fiscal": link_nf
                    }
                    for col_nome, valor in dados_para_inserir.items():
                        if col_nome in cabecalhos: nova_linha[cabecalhos.index(col_nome)] = valor
                            
                    worksheet.append_row(nova_linha)
                    st.success(f"✅ Nota {nf_num} gravada na conta {conta_sap}!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

    # ==========================================
    # TAB 2: CONSTRUTOR DE GRÁFICOS (EIXO X / EIXO Y)
    # ==========================================
    with tab2:
        if df_fato.empty:
            st.info("Aguardando leitura de dados para montar o painel.")
        else:
            st.markdown("### 🎛️ Eixos do Gráfico")
            
            # --- FORMULÁRIO DE PARAMETRIZAÇÃO ---
            with st.form("form_eixos"):
                
                # LINHA 1: Filtro Global
                meses_disp = sorted(df_fato["Competência"].dropna().unique().tolist())
                filtro_mes = st.multiselect("📅 Filtro de Meses (Deixe vazio para ver todo o período):", meses_disp, default=meses_disp[-1:] if meses_disp else [])
                
                st.markdown("---")
                
                # LINHA 2: Seleção de X e Y
                col_x, col_y = st.columns(2)
                
                with col_x:
                    opcoes_eixo_x = ["Competência", "CONTA", "Categoria (Tipo 1)", "Fornecedor"]
                    eixo_x = st.selectbox("👉 EIXO X (Como você quer agrupar/dividir os dados?)", opcoes_eixo_x)
                    
                with col_y:
                    # O usuário escolhe quais barras/linhas quer ver. O Delta é calculado depois.
                    eixo_y = st.multiselect("📊 EIXO Y (O que você quer medir/somar?)", ["Orçado", "Realizado", "Delta (Saldo)"], default=["Orçado", "Realizado"])

                st.markdown("<br>", unsafe_allow_html=True)
                btn_gerar = st.form_submit_button("⚙️ Gerar Gráficos e Comparação", use_container_width=True)

            # --- RENDERIZAÇÃO APÓS O CLIQUE ---
            if btn_gerar:
                st.markdown("---")
                
                if not eixo_y:
                    st.warning("Selecione pelo menos uma métrica no Eixo Y para gerar o gráfico.")
                else:
                    # 1. Aplica o filtro de Mês (se houver seleção)
                    df_plot = df_fato[df_fato["Competência"].isin(filtro_mes)] if filtro_mes else df_fato.copy()
                    
                    # 2. Agrupa a Tabela pelo Eixo X escolhido pelo usuário
                    df_agrupado = df_plot.groupby(eixo_x)[["Orçado", "Realizado"]].sum().reset_index()
                    
                    # 3. Calcula o Delta Matemático Pós-Agrupamento
                    df_agrupado["Delta (Saldo)"] = df_agrupado["Orçado"] - df_agrupado["Realizado"]
                    
                    # 4. Ordenação Padrão (Deixar os maiores valores à esquerda no gráfico)
                    col_ordem = "Orçado" if "Orçado" in eixo_y else "Realizado"
                    df_agrupado = df_agrupado.sort_values(by=col_ordem, ascending=False)
                    
                    # Extrai apenas as colunas que o usuário pediu para visualizar
                    df_final_grafico = df_agrupado.set_index(eixo_x)[eixo_y]

                    # --- EXIBIÇÃO ---
                    st.markdown(f"### 📈 Comparativo: {', '.join(eixo_y)} por {eixo_x}")
                    
                    # Gráficos de Comparação
                    g1, g2 = st.columns(2)
                    with g1:
                        st.markdown("##### Gráfico de Barras")
                        st.bar_chart(df_final_grafico)
                    with g2:
                        st.markdown("##### Gráfico de Linhas")
                        st.line_chart(df_final_grafico)
                        
                    st.markdown("---")
                    
                    # Tabela Analítica de Apoio
                    st.markdown("##### 📋 Tabela Analítica (Detalhe do Eixo X e Y)")
                    
                    def pintar_delta(val):
                        # Pinta de vermelho apenas se for o saldo/delta e for negativo
                        try:
                            if float(val) < 0: return 'color: #990000; font-weight: bold;'
                        except: pass
                        return ''

                    # Prepara a tabela apenas com as colunas solicitadas
                    colunas_tabela = [eixo_x] + eixo_y
                    df_exibicao_tabela = df_agrupado[colunas_tabela].copy()

                    st.dataframe(
                        df_exibicao_tabela.style.map(pintar_delta).format({col: formatar_moeda_br for col in eixo_y}),
                        use_container_width=True,
                        hide_index=True
                    )
