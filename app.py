import streamlit as st
import pandas as pd
import numpy as np
import os
import gspread
import datetime
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DO SGGAG ---
st.set_page_config(page_title="SGGAG | Dashboard Executivo", layout="wide", page_icon="📊")

st.sidebar.title("📊 SGGAG Engine")
st.sidebar.caption("Sistema Global de Gestão e Análise de Gastos")
spreadsheet_url = st.sidebar.text_input("Data Lake (Google Sheets URL)")
drive_folder_id = st.sidebar.text_input("AWS S3 / Drive Bucket (Opcional)")

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
        st.error("⚠️ Falha de Autenticação com o BD.")
        st.stop()

def get_google_client():
    return gspread.authorize(get_credentials())

def upload_to_drive(file, folder_id):
    try:
        gauth = GoogleAuth()
        gauth.credentials = get_credentials()
        drive = GoogleDrive(gauth)
        file_drive = drive.CreateFile({'title': file.name, 'parents': [{'id': folder_id}]})
        with open(file.name, "wb") as f: f.write(file.getbuffer())
        file_drive.SetContentFile(file.name)
        file_drive.Upload()
        os.remove(file.name)
        return file_drive['alternateLink']
    except Exception: return None

# --- ENGINE DE DADOS (NORMALIZAÇÃO ABSOLUTA) ---
def limpeza_final(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).upper().replace("R$", "").strip()
    s = ''.join(c for c in s if c.isdigit() or c in '.,-')
    if not s: return 0.0
    qtd_pontos = s.count('.')
    qtd_virgulas = s.count(',')
    
    if qtd_pontos == 1 and qtd_virgulas == 1:
        if s.rfind(',') > s.rfind('.'): s = s.replace('.', '').replace(',', '.')
        else: s = s.replace(',', '') 
    elif qtd_pontos > 1 and qtd_virgulas <= 1: s = s.replace('.', '').replace(',', '.') 
    elif qtd_virgulas > 1 and qtd_pontos <= 1: s = s.replace(',', '') 
    elif qtd_pontos == 1 and qtd_virgulas == 0:
        if len(s.split('.')[-1]) == 3: s = s.replace('.', '') 
    elif qtd_virgulas == 1 and qtd_pontos == 0:
        if len(s.split(',')[-1]) == 3: s = s.replace(',', '') 
        else: s = s.replace(',', '.') 
    try: return float(s)
    except: return 0.0

def formatar_moeda_br(valor):
    try:
        if pd.isna(valor): return "R$ 0,00"
        txt = f"{float(valor):,.2f}"
        return f"R$ {txt.replace(',', 'X').replace('.', ',').replace('X', '.')}"
    except: return "R$ 0,00"

# --- CORE DO SISTEMA ---
if not spreadsheet_url:
    st.info("Conecte o Data Lake (URL da Planilha) para inicializar o SGGAG.")
else:
    tab1, tab2, tab3 = st.tabs([
        "📥 Ingestão & Staging", 
        "📈 Dashboard Executivo", 
        "⚙️ Configurações & Logs"
    ])

    # --- ETL GLOBAL: EXTRAÇÃO DE ALTA FIDELIDADE ---
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
        ws_lanc = sheet.worksheet("Lancamentos").get_all_values()
        df_lanc = pd.DataFrame(ws_lanc[1:], columns=ws_lanc[0]) if ws_lanc and len(ws_lanc) > 1 else pd.DataFrame()
            
        ws_budget = sheet.worksheet("Budget").get_all_values()
        df_budget = pd.DataFrame(ws_budget[1:], columns=ws_budget[0]) if ws_budget and len(ws_budget) > 1 else pd.DataFrame()
        
        if not df_lanc.empty:
            df_lanc["Total da linha (Num)"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            df_lanc["Data NF"] = pd.to_datetime(df_lanc.get("Data NF", df_lanc.get("Data de lançamento")), dayfirst=True, errors='coerce')
            df_lanc["Competência"] = df_lanc["Data NF"].dt.strftime('%m/%Y')
            df_lanc["Conta SAP"] = df_lanc.get("Conta SAP", pd.Series()).astype(str).str.strip()
            df_lanc["Nº NF"] = df_lanc.get("Nº NF", pd.Series()).astype(str).str.strip()
            df_lanc["CNPJ ou CPF"] = df_lanc.get("CNPJ ou CPF", pd.Series()).astype(str).str.strip()
            if "Descrição do item/serviço" not in df_lanc.columns: df_lanc["Descrição do item/serviço"] = "N/A"
        
        if not df_budget.empty:
            df_budget["Orçado"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)
            df_budget["Competência"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_budget["CONTA"] = df_budget.get("CONTA", pd.Series()).astype(str).str.strip()

    except Exception as e:
        st.error("Falha no Gateway de Dados. Verifique a estrutura da planilha.")
        df_lanc, df_budget = pd.DataFrame(), pd.DataFrame()

    # ==========================================
    # MÓDULO 1: INGESTÃO
    # ==========================================
    with tab1:
        st.markdown("### Formulário de Ingestão de Documentos Fiscais")
        with st.form("form_staging", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: nf_num = st.text_input("Nº NF *")
            with c2: cnpj = st.text_input("CNPJ Fornecedor *")
            with c3: data_emissao = st.date_input("Data de Emissão *")
            with c4: conta_sap = st.text_input("Conta SAP *")
            
            cv1, cv2, cv3 = st.columns(3)
            with cv1: fornecedor = st.text_input("Razão Social *")
            with cv2: valor_linha = st.number_input("Valor da Linha (R$) *", min_value=0.0, format="%.2f")
            with cv3: arquivo_nf = st.file_uploader("Documento Fiscal (Anexo)", type=["pdf"])

            submit = st.form_submit_button("🚀 Ingerir Dados", use_container_width=True)

        if submit:
            erros = [e for e, c in [("Campos obrigatórios ausentes.", not (nf_num and cnpj and fornecedor and conta_sap)), 
                                    (f"A NF {nf_num} já existe.", not df_lanc.empty and not df_lanc[(df_lanc["Nº NF"] == str(nf_num)) & (df_lanc["CNPJ ou CPF"] == str(cnpj))].empty)] if c]
            if erros:
                for erro in erros: st.error(f"❌ {erro}")
            else:
                with st.spinner("Processando..."):
                    link_nf = upload_to_drive(arquivo_nf, drive_folder_id) if arquivo_nf and drive_folder_id else "Sem Anexo"
                    try:
                        worksheet = sheet.worksheet("Lancamentos")
                        cabecalhos = worksheet.row_values(1)
                        nova_linha = [""] * len(cabecalhos)
                        dados_insert = {
                            "Nº NF": nf_num, "CNPJ ou CPF": cnpj, "Nome do cliente/fornecedor": fornecedor,
                            "Data NF": data_emissao.strftime("%d/%m/%Y"), "Data de lançamento": data_emissao.strftime("%d/%m/%Y"),
                            "Total da linha": str(valor_linha).replace(".", ","), "Total documento": str(valor_linha).replace(".", ","),
                            "Conta SAP": conta_sap, "Referência da Nota Fiscal": link_nf,
                            "Data Sistema Entrada": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        }
                        for col_nome, valor in dados_insert.items():
                            if col_nome in cabecalhos: nova_linha[cabecalhos.index(col_nome)] = valor
                        worksheet.append_row(nova_linha)
                        st.success("✅ NF gravada com sucesso.")
                    except Exception as e: st.error(f"Erro no BD: {e}")

    # ==========================================
    # MÓDULO 2: DASHBOARD EXECUTIVO (TURBINADO)
    # ==========================================
    with tab2:
        if not df_lanc.empty and not df_budget.empty:
            
            # --- FILTRO GLOBAL ---
            meses_dash = sorted(df_budget["Competência"].dropna().unique().tolist())
            col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
            with col_f2:
                mes_alvo = st.selectbox("📅 Selecione a Competência para Análise:", meses_dash, index=len(meses_dash)-1 if meses_dash else 0)
            
            st.markdown("---")
            
            # --- PREPARAÇÃO DOS DADOS ---
            b_mes = df_budget[df_budget["Competência"] == mes_alvo].copy()
            l_mes = df_lanc[df_lanc["Competência"] == mes_alvo].copy()
            
            l_grp = l_mes.groupby("Conta SAP")["Total da linha (Num)"].sum().reset_index()
            l_grp.rename(columns={"Conta SAP": "CONTA", "Total da linha (Num)": "Realizado"}, inplace=True)
            
            df_bi = pd.merge(b_mes, l_grp, on="CONTA", how="left").fillna(0)
            df_bi["Desvio"] = df_bi["Orçado"] - df_bi["Realizado"]
            
            tot_orc = df_bi["Orçado"].sum()
            tot_real = df_bi["Realizado"].sum()
            pct_consumo = (tot_real / tot_orc * 100) if tot_orc > 0 else 0

            # --- LINHA 1: KPIS PRINCIPAIS ---
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💼 Budget Aprovado", formatar_moeda_br(tot_orc))
            k2.metric("💸 Consumo Realizado", formatar_moeda_br(tot_real), f"Impacto: {pct_consumo:.1f}%", delta_color="off")
            k3.metric("⚖️ Variância (Saldo)", formatar_moeda_br(tot_orc - tot_real), "Saudável" if (tot_orc - tot_real) >= 0 else "Estourado", delta_color="normal")
            
            # Gauge de Progresso
            with k4:
                st.markdown(f"**Nível de Consumo:** `{pct_consumo:.1f}%`")
                st.progress(min(pct_consumo / 100, 1.0))

            st.markdown("<br>", unsafe_allow_html=True)

            # --- LINHA 2: GRÁFICOS ANALÍTICOS ---
            col_chart1, col_chart2 = st.columns(2)
            
            # Preparando rótulo para os gráficos (Usa TIPO 1 se tiver, senão usa CONTA)
            coluna_rotulo = "TIPO 1" if "TIPO 1" in df_bi.columns else "CONTA"
            
            with col_chart1:
                st.markdown("##### 📊 Orçado vs Realizado (Visão Geral)")
                df_chart_comp = df_bi.set_index(coluna_rotulo)[["Orçado", "Realizado"]].sort_values("Orçado", ascending=False)
                st.bar_chart(df_chart_comp, color=["#1f77b4", "#ff7f0e"]) # Azul para Budget, Laranja para Realizado
                
            with col_chart2:
                st.markdown("##### 🔥 Top 5 Ofensores do Mês")
                df_top5 = df_bi.sort_values("Realizado", ascending=False).head(5)
                st.bar_chart(df_top5.set_index(coluna_rotulo)["Realizado"], color="#d62728") # Vermelho para alerta

            st.markdown("---")

            # --- LINHA 3: TABELA MATRIZ COM BARRAS DE PROGRESSO ---
            st.markdown("##### 📋 Matriz Detalhada de Despesas")
            
            # Calcula a porcentagem individual para a tabela
            df_bi["% Utilizado"] = np.where(df_bi["Orçado"] > 0, (df_bi["Realizado"] / df_bi["Orçado"]) * 100, 0)
            
            # Status Emoji
            df_bi["Status"] = np.where(df_bi["Realizado"] > df_bi["Orçado"], "🔴 Estourou", np.where(df_bi["Realizado"] > df_bi["Orçado"]*0.85, "🟡 Alerta", "🟢 Seguro"))

            # Exibição rica do dataframe usando configurações de coluna nativas do Streamlit
            st.dataframe(
                df_bi[["CONTA", coluna_rotulo, "Orçado", "Realizado", "Desvio", "% Utilizado", "Status"]],
                column_config={
                    "CONTA": st.column_config.TextColumn("Conta SAP"),
                    coluna_rotulo: st.column_config.TextColumn("Categoria"),
                    "Orçado": st.column_config.NumberColumn("Budget P.", format="R$ %.2f"),
                    "Realizado": st.column_config.NumberColumn("Realizado", format="R$ %.2f"),
                    "Desvio": st.column_config.NumberColumn("Saldo/Desvio", format="R$ %.2f"),
                    "% Utilizado": st.column_config.ProgressColumn(
                        "% Consumo",
                        help="Percentual do Budget gasto (barra enche até 100%)",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    ),
                    "Status": st.column_config.TextColumn("Status")
                },
                hide_index=True,
                use_container_width=True
            )

            # --- LINHA 4: AUDITORIA DRILL-DOWN ---
            with st.expander("🕵️ Clique aqui para Abrir a Auditoria de Notas (Drill-Down)"):
                st.caption("Investigue exatamente quais notas fiscais formam o valor de cada conta.")
                
                contas_usadas = sorted(l_mes[l_mes["Total da linha (Num)"] > 0]["Conta SAP"].unique().tolist())
                conta_auditoria = st.selectbox("Escolha a Conta SAP para rastrear:", [""] + contas_usadas)
                
                if conta_auditoria:
                    df_auditoria = l_mes[l_mes["Conta SAP"] == conta_auditoria]
                    colunas_chave = [c for c in ["Data NF", "Nº NF", "Nome do cliente/fornecedor", "Descrição do item/serviço", "Total da linha (Num)"] if c in df_auditoria.columns]
                    
                    st.dataframe(
                        df_auditoria[colunas_chave].style.format({"Total da linha (Num)": formatar_moeda_br}),
                        use_container_width=True, hide_index=True
                    )

    # ==========================================
    # MÓDULO 3: CONFIGURAÇÕES E LOGS
    # ==========================================
    with tab3:
        st.markdown("### ⚙️ Logs do Sistema (Audit)")
        if not df_lanc.empty:
            cols_audit = ["Data Sistema Entrada", "Nº NF", "Nome do cliente/fornecedor"]
            if "Data Sistema Entrada" in df_lanc.columns:
                st.dataframe(df_lanc[cols_audit].tail(10).sort_values("Data Sistema Entrada", ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info("Log indisponível.")
