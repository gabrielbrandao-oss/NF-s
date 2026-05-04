import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Hub Financeiro On-Demand", layout="wide")

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
st.title("🚀 Hub Financeiro On-Demand")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha Google na barra lateral para iniciar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "🛠️ Construtor de Dashboard"])

    # ==========================================
    # PROCESSAMENTO DE DADOS GLOBAL
    # ==========================================
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
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
    # TAB 2: CONSTRUTOR DE DASHBOARD
    # ==========================================
    with tab2:
        if df_lanc.empty or df_budget.empty:
            st.info("Aguardando leitura de dados das abas 'Lancamentos' e 'Budget'.")
        else:
            # 1. Base Unificada Inteligente
            df_lanc_agrupado = df_lanc.groupby(["Competência", "Conta SAP"]).agg({"Realizado": "sum"}).reset_index()
            df_lanc_agrupado.rename(columns={"Conta SAP": "CONTA"}, inplace=True)
            df_comp = pd.merge(df_budget, df_lanc_agrupado, on=["Competência", "CONTA"], how="outer").fillna(0)
            df_comp["Saldo"] = df_comp["Orçado"] - df_comp["Realizado"]

            # --- ÁREA DE PARAMETRIZAÇÃO MANUAL ---
            st.markdown("### 🎛️ Painel de Configuração")
            
            with st.form("construtor_dash"):
                col_param1, col_param2, col_param3 = st.columns(3)
                
                with col_param1:
                    base_sel = st.selectbox("1. Qual base analisar?", ["Comparativo (Budget x Realizado)", "Apenas Lançamentos (Detalhado)"])
                    meses_disponiveis = sorted(df_comp["Competência"].astype(str).unique().tolist())
                    meses_sel = st.multiselect("2. Filtrar Meses:", meses_disponiveis, default=meses_disponiveis[-1:] if meses_disponiveis else [])
                
                with col_param2:
                    df_alvo = df_comp if base_sel == "Comparativo (Budget x Realizado)" else df_lanc
                    
                    opcoes_agrupamento = df_alvo.columns.tolist()
                    default_grp = "CONTA" if "CONTA" in opcoes_agrupamento else "Conta SAP"
                    
                    agrupamento_sel = st.selectbox("3. Agrupar Análise Por (Eixo X):", opcoes_agrupamento, index=opcoes_agrupamento.index(default_grp) if default_grp in opcoes_agrupamento else 0)
                    
                    opcoes_metricas = ["Orçado", "Realizado", "Saldo"] if base_sel == "Comparativo (Budget x Realizado)" else ["Realizado"]
                    metricas_sel = st.multiselect("4. Valores para Somar (Eixo Y):", opcoes_metricas, default=opcoes_metricas)

                with col_param3:
                    visuais_sel = st.multiselect(
                        "5. O que gerar no Dashboard?", 
                        ["Cartões Resumo (KPIs)", "Gráfico de Barras", "Gráfico de Linha", "Tabela de Dados"], 
                        default=["Cartões Resumo (KPIs)", "Gráfico de Barras", "Tabela de Dados"]
                    )
                
                btn_gerar = st.form_submit_button("🚀 Gerar Dashboard Agora", use_container_width=True)

            # --- GERAÇÃO DO DASHBOARD SOB DEMANDA ---
            if btn_gerar:
                st.markdown("---")
                
                if not meses_sel:
                    st.error("Selecione ao menos um mês para gerar o relatório.")
                elif not metricas_sel:
                    st.error("Selecione ao menos uma métrica (Valor) para somar.")
                else:
                    # Aplica o filtro de mês
                    df_filtrado = df_alvo[df_alvo["Competência"].astype(str).isin(meses_sel)].copy()
                    
                    # Gera a Tabela Dinâmica com as seleções do usuário
                    df_relatorio = df_filtrado.groupby(agrupamento_sel)[metricas_sel].sum().reset_index()

                    st.markdown(f"## 📊 Dashboard de {agrupamento_sel}")
                    st.caption(f"Meses analisados: {', '.join(meses_sel)} | Base: {base_sel}")
                    
                    # 1. Módulo: Cartões Resumo (KPIs)
                    if "Cartões Resumo (KPIs)" in visuais_sel:
                        cols_kpi = st.columns(len(metricas_sel))
                        for i, metrica in enumerate(metricas_sel):
                            total = df_relatorio[metrica].sum()
                            cols_kpi[i].metric(f"Total: {metrica}", formatar_moeda_br(total))
                        st.markdown("<br>", unsafe_allow_html=True)

                    # 2. Módulo: Gráfico de Barras
                    if "Gráfico de Barras" in visuais_sel:
                        st.markdown("##### Visão em Barras")
                        # Ordena pelo primeiro valor selecionado para o gráfico ficar bonito
                        df_chart = df_relatorio.sort_values(by=metricas_sel[0], ascending=False).head(15) 
                        st.bar_chart(df_chart.set_index(agrupamento_sel)[metricas_sel])

                    # 3. Módulo: Gráfico de Linha
                    if "Gráfico de Linha" in visuais_sel:
                        st.markdown("##### Visão em Linha")
                        st.line_chart(df_relatorio.set_index(agrupamento_sel)[metricas_sel])

                    # 4. Módulo: Tabela de Dados (Matriz)
                    if "Tabela de Dados" in visuais_sel:
                        st.markdown("##### Matriz de Dados")
                        
                        # Função interna para pintar o "Saldo" de vermelho se for negativo
                        def pintar_saldo(row):
                            if "Saldo" in row.index and row["Saldo"] < 0:
                                return ['background-color: #ffe6e6'] * len(row)
                            return [''] * len(row)

                        st.dataframe(
                            df_relatorio.style.apply(pintar_saldo, axis=1).format({col: formatar_moeda_br for col in metricas_sel}),
                            use_container_width=True,
                            hide_index=True
                        )
