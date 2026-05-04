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
st.set_page_config(page_title="SGGAG | Inteligência Financeira", layout="wide", page_icon="🌐")

st.sidebar.title("🌐 SGGAG Engine")
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

# --- ENGINE DE DADOS (NORMALIZAÇÃO) ---
def limpeza_final(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s: return 0.0
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."): s = s.replace(".", "").replace(",", ".")
        else: s = s.replace(",", "")
    elif "," in s: s = s.replace(",", ".")
    return pd.to_numeric(s, errors='coerce') or 0.0

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
    # Módulos do Sistema
    tab1, tab2, tab3, tab4 = st.tabs([
        "📥 1. Ingestão & Staging", 
        "📊 2. Visão Executiva (Matching)", 
        "🧠 3. Motor Preditivo (Forecasting)",
        "⚙️ 4. Auditoria (Logs)"
    ])

    # --- ETL GLOBAL (EXTRAÇÃO E TRANSFORMAÇÃO) ---
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
        df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
        df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())
        
        if not df_lanc.empty:
            df_lanc["Total da linha"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            df_lanc["Total documento"] = df_lanc.get("Total documento", pd.Series()).apply(limpeza_final)
            df_lanc["Data NF"] = pd.to_datetime(df_lanc.get("Data NF", df_lanc.get("Data de lançamento")), dayfirst=True, errors='coerce')
            df_lanc["Competência"] = df_lanc["Data NF"].dt.strftime('%m/%Y')
            df_lanc["Conta SAP"] = df_lanc.get("Conta SAP", pd.Series()).astype(str).str.strip()
            df_lanc["Nº NF"] = df_lanc.get("Nº NF", pd.Series()).astype(str).str.strip()
            df_lanc["CNPJ ou CPF"] = df_lanc.get("CNPJ ou CPF", pd.Series()).astype(str).str.strip()
        
        if not df_budget.empty:
            df_budget["Orçado"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)
            df_budget["Competência"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_budget["CONTA"] = df_budget.get("CONTA", pd.Series()).astype(str).str.strip()

    except Exception as e:
        st.error("Falha no Gateway de Dados.")
        df_lanc, df_budget = pd.DataFrame(), pd.DataFrame()

    # ==========================================
    # MÓDULO 1: INGESTÃO (STAGING & IDEMPOTÊNCIA)
    # ==========================================
    with tab1:
        st.markdown("### Gateway de Ingestão de Dados")
        st.caption("Fase de Staging: Validação de integridade, deduplicação (Hash) e normalização.")
        
        with st.form("form_staging", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: nf_num = st.text_input("Nº NF *")
            with c2: cnpj = st.text_input("CNPJ Fornecedor *")
            with c3: data_emissao = st.date_input("Data de Emissão (NF) *")
            with c4: conta_sap = st.text_input("Conta SAP (Apropriação) *")
            
            cv1, cv2, cv3 = st.columns(3)
            with cv1: fornecedor = st.text_input("Razão Social *")
            with cv2: valor_linha = st.number_input("Valor da Linha (R$) *", min_value=0.0, format="%.2f")
            with cv3: arquivo_nf = st.file_uploader("Documento Fiscal (Storage)", type=["pdf"])

            submit = st.form_submit_button("🛡️ Validar e Ingerir", use_container_width=True)

        if submit:
            erros = []
            if not nf_num or not cnpj or not fornecedor or not conta_sap:
                erros.append("Campos obrigatórios ausentes.")
            
            # Validação de Idempotência (Evitar Duplicidade)
            if not df_lanc.empty:
                duplicidade = df_lanc[(df_lanc["Nº NF"] == str(nf_num)) & (df_lanc["CNPJ ou CPF"] == str(cnpj))]
                if not duplicidade.empty:
                    erros.append(f"Idempotência: A NF {nf_num} do CNPJ {cnpj} já existe no banco de dados.")

            if erros:
                for erro in erros: st.error(f"❌ {erro}")
            else:
                with st.spinner("Staging... Normalizando e gravando na fato_nf..."):
                    link_nf = upload_to_drive(arquivo_nf, drive_folder_id) if arquivo_nf and drive_folder_id else "Sem Anexo"
                    try:
                        worksheet = sheet.worksheet("Lancamentos")
                        cabecalhos = worksheet.row_values(1)
                        nova_linha = [""] * len(cabecalhos)
                        
                        dados_insert = {
                            "Nº NF": nf_num, "CNPJ ou CPF": cnpj, "Nome do cliente/fornecedor": fornecedor,
                            "Data NF": data_emissao.strftime("%d/%m/%Y"), "Data de lançamento": data_emissao.strftime("%d/%m/%Y"),
                            "Total da linha": valor_linha, "Total documento": valor_linha,
                            "Conta SAP": conta_sap, "Referência da Nota Fiscal": link_nf,
                            "Data Sistema Entrada": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        }
                        for col_nome, valor in dados_insert.items():
                            if col_nome in cabecalhos: nova_linha[cabecalhos.index(col_nome)] = valor
                                
                        worksheet.append_row(nova_linha)
                        st.success(f"✅ Pipeline concluído. NF {nf_num} inserida no SGGAG.")
                    except Exception as e:
                        st.error(f"Erro de I/O no BD: {e}")

    # ==========================================
    # MÓDULO 2: VISÃO EXECUTIVA (MATCHING ENGINE)
    # ==========================================
    with tab2:
        if not df_lanc.empty and not df_budget.empty:
            meses_dash = sorted(df_budget["Competência"].dropna().unique().tolist())
            mes_alvo = st.selectbox("Período de Referência:", meses_dash, index=len(meses_dash)-1 if meses_dash else 0)
            
            # Matching Realizado vs Orçado
            b_mes = df_budget[df_budget["Competência"] == mes_alvo]
            l_mes = df_lanc[df_lanc["Competência"] == mes_alvo]
            l_grp = l_mes.groupby("Conta SAP")["Total da linha"].sum().reset_index()
            l_grp.rename(columns={"Conta SAP": "CONTA", "Total da linha": "Realizado"}, inplace=True)
            
            df_bi = pd.merge(b_mes, l_grp, on="CONTA", how="left").fillna(0)
            df_bi["Desvio"] = df_bi["Orçado"] - df_bi["Realizado"]
            
            tot_orc = df_bi["Orçado"].sum()
            tot_real = df_bi["Realizado"].sum()
            pct_consumo = (tot_real / tot_orc * 100) if tot_orc > 0 else 0

            # Velocímetro e KPIs
            col_gauge, col_kpis = st.columns([1, 3])
            with col_gauge:
                st.markdown(f"### {pct_consumo:.1f}%")
                st.progress(min(pct_consumo / 100, 1.0))
                st.caption("Consumo Global do Budget")
                
            with col_kpis:
                k1, k2, k3 = st.columns(3)
                k1.metric("Budget Planejado", formatar_moeda_br(tot_orc))
                k2.metric("Total Realizado", formatar_moeda_br(tot_real), f"Desvio: {formatar_moeda_br(tot_orc - tot_real)}", delta_color="inverse")
                k3.metric("Status Global", "🟢 Saudável" if tot_real <= tot_orc else "🔴 Estourado")

            st.markdown("##### 🔍 Detalhamento por Centro de Custo / Conta SAP")
            df_bi["Status"] = np.where(df_bi["Realizado"] > df_bi["Orçado"], "🔴 Estourado", np.where(df_bi["Realizado"] > df_bi["Orçado"]*0.85, "🟡 Alerta", "🟢 OK"))
            st.dataframe(
                df_bi[["CONTA", "TIPO 1", "Orçado", "Realizado", "Desvio", "Status"]].style.format({
                    "Orçado": formatar_moeda_br, "Realizado": formatar_moeda_br, "Desvio": formatar_moeda_br
                }), use_container_width=True, hide_index=True
            )

    # ==========================================
    # MÓDULO 3: MOTOR PREDITIVO (FORECASTING & AI)
    # ==========================================
    with tab3:
        st.markdown("### 🧠 Inteligência de Planejamento (Forecasting & Sugestão)")
        if not df_lanc.empty:
            # Preparação da Série Temporal Histórica
            df_hist = df_lanc.copy()
            df_hist["Data_Obj"] = pd.to_datetime(df_hist["Competência"], format='%m/%Y')
            df_hist = df_hist.sort_values("Data_Obj")
            
            st.sidebar.markdown("---")
            st.sidebar.markdown("**Parâmetros de I.A.**")
            margem_seguranca = st.sidebar.slider("Margem de Segurança para Sugestão (%)", 0, 30, 5) / 100
            
            # Análise Global de Tendência
            hist_global = df_hist.groupby("Competência")["Total da linha"].sum().reset_index()
            
            if len(hist_global) >= 2:
                col_graf, col_sugestao = st.columns([2, 1])
                
                with col_graf:
                    st.markdown("##### 📈 Curva Histórica de Realizado")
                    st.line_chart(hist_global.set_index("Competência")["Total da linha"])
                
                with col_sugestao:
                    st.markdown("##### 💡 Sugestão Algorítmica de Budget")
                    st.caption("Cálculo baseado na Mediana Histórica + Margem de Segurança")
                    
                    # Matemática da Sugestão
                    mediana_historica = hist_global["Total da linha"].median()
                    sugestao_budget = mediana_historica * (1 + margem_seguranca)
                    
                    st.metric("Mediana Mensal (Histórico)", formatar_moeda_br(mediana_historica))
                    st.metric(f"Sugestão Próximo Ciclo (+{margem_seguranca*100:.0f}%)", formatar_moeda_br(sugestao_budget), "Proposta de Teto", delta_color="normal")
            
            st.markdown("---")
            st.markdown("##### 🎯 Sugestão de Budget Detalhado por Conta (Próximo Mês)")
            # Sugestão Granular por Conta SAP
            hist_contas = df_hist.groupby("Conta SAP")["Total da linha"].median().reset_index()
            hist_contas["Sugestão de Budget"] = hist_contas["Total da linha"] * (1 + margem_seguranca)
            hist_contas.rename(columns={"Total da linha": "Mediana Histórica (R$)"}, inplace=True)
            
            st.dataframe(
                hist_contas.style.format({
                    "Mediana Histórica (R$)": formatar_moeda_br,
                    "Sugestão de Budget": formatar_moeda_br
                }), use_container_width=True, hide_index=True
            )
        else:
            st.info("Volume de dados histórico insuficiente para rodar a regressão preditiva.")

    # ==========================================
    # MÓDULO 4: AUDITORIA DE SEGURANÇA (LOGS)
    # ==========================================
    with tab4:
        st.markdown("### ⚙️ Logs do Sistema (Audit_Logs)")
        if not df_lanc.empty:
            cols_audit = ["Data Sistema Entrada", "Nº NF", "CNPJ ou CPF", "Conta SAP", "Total documento"]
            # Exibe as entradas mais recentes baseadas na data do sistema (Soft tracking)
            if "Data Sistema Entrada" in df_lanc.columns:
                df_audit = df_lanc[cols_audit].sort_values(by="Data Sistema Entrada", ascending=False).head(20)
                st.dataframe(df_audit.style.format({"Total documento": formatar_moeda_br}), use_container_width=True, hide_index=True)
            else:
                st.write("Registros de metadados do sistema indisponíveis.")
