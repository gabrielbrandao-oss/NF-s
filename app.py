import streamlit as st
import pandas as pd
import os
import gspread
import datetime
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PÁGINA (VISÃO PLATAFORMA) ---
st.set_page_config(page_title="Plataforma de Inteligência Financeira", layout="wide", page_icon="🏢")

st.sidebar.header("⚙️ Configurações do Sistema")
spreadsheet_url = st.sidebar.text_input("URL do Banco de Dados (Sheets)")
drive_folder_id = st.sidebar.text_input("Bucket do Drive (Opcional)")

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
        st.error("⚠️ Falha de Autenticação: Credenciais não encontradas.")
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

# --- MOTOR DE NORMALIZAÇÃO DE DADOS ---
def limpeza_final(val):
    """Garante a integridade do dado financeiro (Data Quality)"""
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
st.title("🏢 Plataforma de Inteligência Financeira")

if not spreadsheet_url:
    st.info("Conecte a string do Banco de Dados (Sheets URL) para inicializar o sistema.")
else:
    # Arquitetura em Módulos
    tab1, tab2, tab3 = st.tabs([
        "📥 Módulo de Ingestão (Data Pipeline)", 
        "📊 Dashboard Gerencial (BI)", 
        "⚙️ Auditoria & CFOP"
    ])

    # ==========================================
    # CAMADA DE DADOS (ETL / EXTRAÇÃO)
    # ==========================================
    try:
        client = get_google_client()
        sheet = client.open_by_url(spreadsheet_url)
        
        df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
        df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())
        
        # Normalização de Lançamentos
        if not df_lanc.empty:
            df_lanc["Total da linha"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            df_lanc["Total documento"] = df_lanc.get("Total documento", pd.Series()).apply(limpeza_final)
            df_lanc["Total Impostos Retidos"] = df_lanc.get("Total Impostos Retidos", pd.Series()).apply(limpeza_final)
            
            df_lanc["Data NF"] = pd.to_datetime(df_lanc.get("Data NF", df_lanc.get("Data de lançamento")), dayfirst=True, errors='coerce')
            df_lanc["Data de vencimento"] = pd.to_datetime(df_lanc.get("Data de vencimento"), dayfirst=True, errors='coerce')
            df_lanc["Competência"] = df_lanc["Data NF"].dt.strftime('%m/%Y')
            df_lanc["Conta SAP"] = df_lanc.get("Conta SAP", pd.Series()).astype(str).str.strip()
            df_lanc["CFOP"] = df_lanc.get("Código CFOP para documento", pd.Series()).astype(str).str.strip()
        
        # Normalização de Budget
        if not df_budget.empty:
            df_budget["Orçado"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)
            df_budget["Competência"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
            df_budget["CONTA"] = df_budget.get("CONTA", pd.Series()).astype(str).str.strip()

    except Exception as e:
        st.error("Falha no ETL: Erro ao conectar com o banco de dados.")
        df_lanc = pd.DataFrame()
        df_budget = pd.DataFrame()

    # ==========================================
    # MÓDULO A: INGESTÃO E VALIDAÇÃO DE DADOS
    # ==========================================
    with tab1:
        st.markdown("### Processamento e Validação de NF")
        st.caption("O sistema bloqueia entradas com inconsistências de data ou valores divergentes.")
        
        with st.form("form_pipeline", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nf_num = st.text_input("Nº NF *")
                cnpj = st.text_input("CNPJ Fornecedor *")
            with c2:
                fornecedor = st.text_input("Razão Social *")
                cfop = st.text_input("CFOP (Ex: 5102, 1933)")
            with c3:
                data_emissao = st.date_input("Data de Emissão (NF) *")
                data_vencimento = st.date_input("Data de Vencimento *")
            with c4:
                conta_sap = st.text_input("Conta SAP / Contábil *")
                arquivo_nf = st.file_uploader("Documento Fiscal (PDF)", type=["pdf"])

            st.markdown("#### Quebra de Valores (O Desafio Técnico)")
            st.caption("A nota será registrada com o Total do Documento para o Contas a Pagar, mas a apropriação gerencial será feita pelo Total da Linha.")
            
            cv1, cv2, cv3 = st.columns(3)
            with cv1:
                valor_doc = st.number_input("Total do Documento (R$) *", min_value=0.0, format="%.2f")
            with cv2:
                valor_linha = st.number_input("Total da Linha (Rateio) (R$) *", min_value=0.0, format="%.2f")
            with cv3:
                impostos = st.number_input("Impostos Retidos (R$)", min_value=0.0, format="%.2f")

            submit = st.form_submit_button("🛡️ Validar e Ingerir Dados", use_container_width=True)

        if submit:
            # 1. MOTOR DE VALIDAÇÃO (Regras de Negócio)
            erros_validacao = []
            if not nf_num or not cnpj or not fornecedor or not conta_sap:
                erros_validacao.append("Campos obrigatórios (*) não preenchidos.")
            if data_vencimento < data_emissao:
                erros_validacao.append("Erro Lógico: A Data de Vencimento não pode ser anterior à Data de Emissão.")
            if valor_linha > valor_doc:
                erros_validacao.append("Erro de Rateio: O Total da Linha não pode ser maior que o Total do Documento.")
            
            if erros_validacao:
                for erro in erros_validacao:
                    st.error(f"❌ {erro}")
            else:
                with st.spinner("Pipeline rodando: Validando, fazendo upload e gravando no BD..."):
                    link_nf = upload_to_drive(arquivo_nf, drive_folder_id) if arquivo_nf and drive_folder_id else "Sem Anexo"
                    try:
                        worksheet = sheet.worksheet("Lancamentos")
                        cabecalhos = worksheet.row_values(1)
                        nova_linha = [""] * len(cabecalhos)
                        
                        dados_insert = {
                            "Nº NF": nf_num, "CNPJ ou CPF": cnpj, "Nome do cliente/fornecedor": fornecedor,
                            "Código CFOP para documento": cfop,
                            "Data NF": data_emissao.strftime("%d/%m/%Y"),
                            "Data de vencimento": data_vencimento.strftime("%d/%m/%Y"),
                            "Data de lançamento": data_emissao.strftime("%d/%m/%Y"), # Usando emissão como competência
                            "Total documento": valor_doc, "Total da linha": valor_linha,
                            "Total Impostos Retidos": impostos,
                            "Conta SAP": conta_sap, "Referência da Nota Fiscal": link_nf,
                            "Status Documento": "Integrado", "Nome do usuário": "App_Streamlit",
                            "Data Sistema Entrada": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        }
                        
                        for col_nome, valor in dados_insert.items():
                            if col_nome in cabecalhos: nova_linha[cabecalhos.index(col_nome)] = valor
                                
                        worksheet.append_row(nova_linha)
                        st.success(f"✅ Transação {nf_num} ingerida com sucesso no Data Lake/Sheets.")
                    except Exception as e:
                        st.error(f"Erro de Banco de Dados: {e}")

    # ==========================================
    # MÓDULO B: DASHBOARD GERENCIAL E HEATMAP
    # ==========================================
    with tab2:
        if df_lanc.empty or df_budget.empty:
            st.warning("O BI Gerencial requer dados na base de Lançamentos e Budget.")
        else:
            # Filtro Global do Dashboard
            meses_dash = sorted(df_budget["Competência"].dropna().unique().tolist())
            mes_alvo = st.selectbox("Período de Análise:", meses_dash, index=len(meses_dash)-1 if meses_dash else 0)
            
            # Isolando as tabelas (O "Select" do Banco)
            b_mes = df_budget[df_budget["Competência"] == mes_alvo]
            l_mes = df_lanc[df_lanc["Competência"] == mes_alvo]
            
            # Tabela de Agregação (View)
            l_grp = l_mes.groupby("Conta SAP")["Total da linha"].sum().reset_index()
            l_grp.rename(columns={"Conta SAP": "CONTA", "Total da linha": "Realizado"}, inplace=True)
            
            # Join Relacional (Comparativo)
            df_bi = pd.merge(b_mes, l_grp, on="CONTA", how="left").fillna(0)
            df_bi["Desvio (Variância)"] = df_bi["Orçado"] - df_bi["Realizado"]
            df_bi["% Consumido"] = (df_bi["Realizado"] / df_bi["Orçado"] * 100).replace([float('inf'), -float('inf')], 0).fillna(0)

            # --- LINHA 1: KPIs EXECUTIVOS ---
            total_b = df_bi["Orçado"].sum()
            total_r = df_bi["Realizado"].sum()
            variancia_total = total_b - total_r
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Budget do Período", formatar_moeda_br(total_b))
            k2.metric("Realizado (Soma das Linhas)", formatar_moeda_br(total_r), f"{(total_r/total_b*100):.1f}% do Planejado" if total_b > 0 else "0%", delta_color="inverse")
            k3.metric("Variância (Saving/Estouro)", formatar_moeda_br(variancia_total), "Saudável" if variancia_total >= 0 else "Atenção")
            
            impostos_total = l_mes["Total Impostos Retidos"].sum() if "Total Impostos Retidos" in l_mes else 0
            k4.metric("Impostos Retidos (Cashflow)", formatar_moeda_br(impostos_total))

            st.markdown("---")

            # --- LINHA 2: HEATMAP E TIMELINE ---
            col_heat, col_time = st.columns([2, 1])
            
            with col_heat:
                st.markdown("##### 🔥 Heatmap de Consumo de Budget")
                st.caption("Contas com % de consumo elevado são destacadas em gradiente térmico.")
                
                df_heat = df_bi[["CONTA", "Categoria (Tipo 1)" if "Categoria (Tipo 1)" in df_bi else "TIPO 1", "Orçado", "Realizado", "% Consumido"]].copy()
                
                # Renderiza o Heatmap usando Pandas Styling nativo do Streamlit
                st.dataframe(
                    df_heat.style.background_gradient(subset=["% Consumido"], cmap="YlOrRd")
                    .format({
                        "Orçado": formatar_moeda_br,
                        "Realizado": formatar_moeda_br,
                        "% Consumido": "{:.1f}%"
                    }),
                    use_container_width=True, hide_index=True
                )
                
            with col_time:
                st.markdown("##### 📅 Timeline de Vencimentos")
                if not l_mes.empty:
                    vencimentos = l_mes.groupby(l_mes["Data de vencimento"].dt.strftime('%d/%m'))["Total documento"].sum().reset_index()
                    vencimentos.columns = ["Dia", "Montante a Pagar"]
                    st.bar_chart(vencimentos.set_index("Dia"), color="#4caf50")
                else:
                    st.info("Sem vencimentos mapeados para este mês.")

    # ==========================================
    # MÓDULO C: AUDITORIA E ANÁLISE DE CFOP
    # ==========================================
    with tab3:
        st.markdown("### Motor Analítico Contábil")
        if not df_lanc.empty:
            c_cfop, c_audit = st.columns(2)
            
            with c_cfop:
                st.markdown("##### 📊 Distribuição por CFOP (Natureza da Operação)")
                st.caption("Visão para a Contabilidade entender onde o dinheiro está alocado.")
                
                df_cfop = df_lanc[df_lanc["CFOP"] != "nan"].groupby("CFOP")["Total da linha"].sum().reset_index()
                if not df_cfop.empty and len(df_cfop) > 0:
                    df_cfop = df_cfop.sort_values(by="Total da linha", ascending=False)
                    st.dataframe(df_cfop.style.format({"Total da linha": formatar_moeda_br}), use_container_width=True, hide_index=True)
                else:
                    st.write("Sem CFOPs preenchidos no período.")
                    
            with c_audit:
                st.markdown("##### 🕵️ Log de Auditoria de Entradas")
                st.caption("Rastreabilidade de quem lançou o dado e quando (Security/Compliance).")
                
                cols_audit = ["Nº NF", "Nome do usuário", "Data Sistema Entrada", "Total documento"]
                df_audit = df_lanc[cols_audit].tail(10).sort_values(by="Data Sistema Entrada", ascending=False)
                st.dataframe(df_audit.style.format({"Total documento": formatar_moeda_br}), use_container_width=True, hide_index=True)
        else:
            st.info("Aguardando lançamentos no banco de dados para gerar a auditoria.")
