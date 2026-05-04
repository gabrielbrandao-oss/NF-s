import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Controladoria Executiva", layout="wide")

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
    if val is None or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s: return 0.0
    if "." in s and "," in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    return pd.to_numeric(s, errors='coerce') or 0.0

# --- APLICATIVO PRINCIPAL ---
st.title("🚀 Hub de Controladoria e B.I.")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha Google na barra lateral para iniciar.")
else:
    # Criação das 3 Abas
    tab1, tab2, tab3 = st.tabs(["📥 Entrada de NF", "🛠️ B.I. Explorer", "📊 Dashboard Gerencial"])

    # ==========================================
    # PROCESSAMENTO DE DADOS GLOBAL (Usado nas abas 2 e 3)
    # ==========================================
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
        # Leitura bruta
        df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
        df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())
        
        # Limpeza Lançamentos
        if not df_lanc.empty:
            df_lanc["Realizado"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            df_lanc["Competência"] = pd.to_datetime(df_lanc.get("Data de lançamento"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_lanc["Conta SAP"] = df_lanc.get("Conta SAP", pd.Series()).astype(str).str.strip()
        
        # Limpeza Budget
        if not df_budget.empty:
            df_budget["Orçado"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)
            df_budget["Competência"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_budget["CONTA"] = df_budget.get("CONTA", pd.Series()).astype(str).str.strip()

    except Exception as e:
        st.error("Erro ao carregar dados do Google Sheets. Verifique a URL.")
        df_lanc = pd.DataFrame()
        df_budget = pd.DataFrame()

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
                conta_sap = st.text_input("Conta SAP", help="Ex: 4.1.02.01.0001")
                arquivo_nf = st.file_uploader("Upload da NF", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento")

        if submit:
            if nf_num and conta_sap:
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
                            if col_nome in cabecalhos:
                                nova_linha[cabecalhos.index(col_nome)] = valor
                                
                        worksheet.append_row(nova_linha)
                        st.success(f"✅ Nota {nf_num} gravada na conta {conta_sap}!")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
            else:
                st.error("⚠️ 'Nº NF' e 'Conta SAP' são obrigatórios.")

    # ==========================================
    # TAB 2: B.I. EXPLORER (Análise Livre)
    # ==========================================
    with tab2:
        st.subheader("🛠️ Construtor de Análises")
        if not df_lanc.empty and not df_budget.empty:
            
            # Preparando a Base Unificada para o B.I.
            df_lanc_agrupado = df_lanc.groupby(["Competência", "Conta SAP"]).agg({"Realizado": "sum"}).reset_index()
            df_lanc_agrupado.rename(columns={"Conta SAP": "CONTA"}, inplace=True)
            df_unificado = pd.merge(df_budget, df_lanc_agrupado, on=["Competência", "CONTA"], how="outer").fillna(0)
            df_unificado["Saldo"] = df_unificado["Orçado"] - df_unificado["Realizado"]

            base_escolhida = st.radio(
                "Escolha o conjunto de dados:", 
                ["Visão Unificada (Budget x Realizado)", "Apenas Lançamentos (NFs)"], 
                horizontal=True
            )
            
            df_alvo = df_unificado if base_escolhida == "Visão Unificada (Budget x Realizado)" else df_lanc

            st.markdown("---")
            col_f, col_p = st.columns([1, 2])
            
            with col_f:
                st.markdown("### 1️⃣ Filtros")
                meses_un = sorted(df_alvo["Competência"].astype(str).unique().tolist())
                filtro_mes = st.multiselect("Filtrar por Competência (Mês/Ano):", meses_un, default=meses_un)
                df_alvo = df_alvo[df_alvo["Competência"].astype(str).isin(filtro_mes)]

            with col_p:
                st.markdown("### 2️⃣ Estrutura da Tabela")
                linhas = st.multiselect("Agrupar dados por:", df_alvo.columns.tolist(), default=["CONTA"] if "CONTA" in df_alvo.columns else ["Conta SAP"])
                
                cols_numericas = df_alvo.select_dtypes(include='number').columns.tolist()
                metricas_padrao = ["Orçado", "Realizado", "Saldo"] if base_escolhida == "Visão Unificada (Budget x Realizado)" else ["Realizado"]
                metricas = st.multiselect("Métricas (Soma):", cols_numericas, default=metricas_padrao)

            if linhas and metricas:
                df_relatorio = df_alvo.groupby(linhas)[metricas].sum().reset_index()
                st.markdown("### 📊 Relatório Gerado")
                st.dataframe(df_relatorio.style.format({col: "R$ {:,.2f}" for col in metricas}), use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 3: DASHBOARD GERENCIAL C-LEVEL
    # ==========================================
    with tab3:
        if df_lanc.empty or df_budget.empty:
            st.info("O Dashboard precisa que ambas as abas (Lançamentos e Budget) tenham dados válidos.")
        else:
            st.subheader("📈 Visão Executiva")
            
            # Seletor Global do Dashboard
            meses_dash = sorted(df_budget["Competência"].dropna().unique().tolist())
            mes_dash_selecionado = st.selectbox("Selecione o Período para Análise:", meses_dash, index=len(meses_dash)-1 if meses_dash else 0)
            
            # Filtragem do Período
            b_dash = df_budget[df_budget["Competência"] == mes_dash_selecionado]
            l_dash = df_lanc[df_lanc["Competência"] == mes_dash_selecionado]
            
            # Agrupamento para KPIs
            l_dash_grp = l_dash.groupby("Conta SAP")["Realizado"].sum().reset_index()
            l_dash_grp.rename(columns={"Conta SAP": "CONTA"}, inplace=True)
            df_dash = pd.merge(b_dash, l_dash_grp, on="CONTA", how="left").fillna(0)
            
            # Métricas Globais do Mês
            total_orcado = df_dash["Orçado"].sum()
            total_realizado = df_dash["Realizado"].sum()
            saldo_geral = total_orcado - total_realizado
            pct_consumo = (total_realizado / total_orcado * 100) if total_orcado > 0 else 0
            
            # Linha de KPIs (Cards)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Budget do Mês", f"R$ {total_orcado:,.2f}")
            k2.metric("Consumo Realizado", f"R$ {total_realizado:,.2f}", f"{pct_consumo:.1f}% do Budget", delta_color="inverse")
            k3.metric("Saldo Disponível", f"R$ {saldo_geral:,.2f}", "Atenção" if saldo_geral < 0 else "Saudável")
            
            # Barra de Progresso Visual
            st.progress(min(pct_consumo / 100, 1.0))
            
            st.markdown("---")
            
            # Gráficos Lado a Lado
            cg1, cg2 = st.columns(2)
            
            with cg1:
                st.markdown("##### 🚨 Top 5 Contas com Maior Consumo")
                df_top_contas = df_dash.sort_values(by="Realizado", ascending=False).head(5)
                # Prepara df para grafico de barras comparativo nativo do Streamlit
                chart_data = df_top_contas.set_index("TIPO 1" if "TIPO 1" in df_top_contas else "CONTA")[["Orçado", "Realizado"]]
                st.bar_chart(chart_data)
                
            with cg2:
                st.markdown("##### 🏆 Top 5 Maiores Fornecedores do Mês")
                if "Nome do cliente/fornecedor" in l_dash.columns:
                    top_fornecedores = l_dash.groupby("Nome do cliente/fornecedor")["Realizado"].sum().sort_values(ascending=False).head(5)
                    st.bar_chart(top_fornecedores, color="#ff4b4b")
                else:
                    st.write("Dados de fornecedores indisponíveis.")

            st.markdown("---")
            st.markdown("##### 📋 Resumo Analítico")
            df_dash["% Executado"] = (df_dash["Realizado"] / df_dash["Orçado"] * 100).replace([float('inf'), -float('inf')], 0).fillna(0)
            df_dash["Status"] = df_dash["% Executado"].apply(lambda x: "🔴 Estourado" if x > 100 else ("🟡 Alerta" if x > 85 else "🟢 OK"))
            
            st.dataframe(
                df_dash[["CONTA", "TIPO 1", "Orçado", "Realizado", "Status", "% Executado"]].style.format({
                    "Orçado": "R$ {:,.2f}",
                    "Realizado": "R$ {:,.2f}",
                    "% Executado": "{:.1f}%"
                }),
                use_container_width=True,
                hide_index=True
            )
