import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="App Controladoria", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI")
drive_folder_id = st.sidebar.text_input("11h3UccF6JH_8SQOUL_HhJZ9beIUQB4kp (Opcional)")

# --- ESCOPOS UNIFICADOS PARA DRIVE E SHEETS ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# --- NOVA FUNÇÃO DE AUTENTICAÇÃO (VIA SECRETS) ---
def get_credentials():
    """Lê as credenciais do cofre do Streamlit em vez de um arquivo físico"""
    try:
        # Transforma os segredos do Streamlit num dicionário Python
        creds_dict = dict(st.secrets["gcp_service_account"])
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    except KeyError:
        st.error("⚠️ Credenciais não encontradas nos Secrets do Streamlit!")
        st.stop()

def get_google_client():
    """Autentica com o Gspread (Sheets)"""
    creds = get_credentials()
    return gspread.authorize(creds)

def upload_to_drive(file, folder_id):
    """Autentica com o PyDrive2 (Drive)"""
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
        st.error(f"Erro no upload do Drive: {e}")
        return None

# --- FUNÇÃO PARA LIMPAR VALORES MONETÁRIOS DO SHEETS ---
def limpar_moeda(valor):
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return pd.to_numeric(valor, errors='coerce')

# --- APLICATIVO PRINCIPAL ---
st.title("📊 Painel de Custos Mensal")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha na barra lateral para começar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "📉 Dashboard Budget"])

    # --- TAB 1: FORMULÁRIO DE ENTRADA ---
    with tab1:
        st.subheader("Novo Lançamento (Padrão SAP)")
        with st.form("form_nf", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                nf_num = st.text_input("Nº NF")
                fornecedor = st.text_input("Fornecedor / Cliente")
            with col2:
                data_lanc = st.date_input("Data de lançamento")
                valor_bruto = st.number_input("Total documento (R$)", min_value=0.0, format="%.2f")
            with col3:
                conta_sap = st.text_input("Conta SAP", help="Ex: 4.1.02.01.0001")
                arquivo_nf = st.file_uploader("Upload da NF", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento")

        if submit:
            if nf_num and conta_sap:
                with st.spinner("Conectando ao Google e registrando nota..."):
                    link_nf = "Sem Anexo" 
                    if arquivo_nf and drive_folder_id:
                        link_nf = upload_to_drive(arquivo_nf, drive_folder_id) or "Erro no Link"

                    try:
                        client = get_google_client()
                        sheet = client.open_by_url(spreadsheet_url)
                        worksheet = sheet.worksheet("Lancamentos")
                        
                        cabecalhos = worksheet.row_values(1)
                        nova_linha = [""] * len(cabecalhos)
                        
                        dados_para_inserir = {
                            "Nº NF": nf_num,
                            "Nome do cliente/fornecedor": fornecedor,
                            "Data de lançamento": data_lanc.strftime("%d/%m/%Y"),
                            "Total documento": valor_bruto,
                            "Total da linha": valor_bruto,
                            "Conta SAP": conta_sap,
                            "Referência da Nota Fiscal": link_nf
                        }
                        
                        for col_nome, valor in dados_para_inserir.items():
                            if col_nome in cabecalhos:
                                idx = cabecalhos.index(col_nome)
                                nova_linha[idx] = valor
                                
                        worksheet.append_row(nova_linha)
                        st.success(f"Nota {nf_num} salva na Conta {conta_sap} com sucesso!")
                        
                    except Exception as e:
                        st.error(f"Erro ao salvar na planilha: {e}")
            else:
                st.error("Preencha Nº NF e Conta SAP.")

    # --- TAB 2: CONFRONTO BUDGET MENSAL ---
    with tab2:
        st.subheader("Análise Mensal: Orçamento vs. Realizado")
        
        try:
            client = get_google_client()
            sheet = client.open_by_url(spreadsheet_url)
            
            df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
            df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())

            if df_budget.empty or df_lanc.empty:
                st.info("Aguardando lançamentos e dados de budget para gerar o gráfico.")
            else:
                df_budget["Valor Budget"] = df_budget["BUDGET"].apply(limpar_moeda).fillna(0)
                df_lanc["Valor Realizado"] = df_lanc["Total documento"].apply(limpar_moeda).fillna(0)

                df_budget["Competência"] = pd.to_datetime(df_budget["MÊS"], format='%d/%m/%Y', errors='coerce').dt.strftime('%m/%Y')
                df_lanc["Competência"] = pd.to_datetime(df_lanc["Data de lançamento"], format='%d/%m/%Y', errors='coerce').dt.strftime('%m/%Y')

                meses_disponiveis = sorted(df_budget["Competência"].dropna().unique().tolist())
                
                if not meses_disponiveis:
                    st.warning("Verifique o formato das datas na aba Budget (deve ser DD/MM/AAAA).")
                else:
                    mes_selecionado = st.selectbox("Selecione a Competência (Mês/Ano):", meses_disponiveis)

                    budget_mes = df_budget[df_budget["Competência"] == mes_selecionado].copy()
                    lanc_mes = df_lanc[df_lanc["Competência"] == mes_selecionado].copy()

                    if "Conta SAP" not in lanc_mes.columns:
                        lanc_mes["Conta SAP"] = ""
                        
                    gastos_agrupados = lanc_mes.groupby("Conta SAP")["Valor Realizado"].sum().reset_index()
                    gastos_agrupados.rename(columns={"Conta SAP": "CONTA", "Valor Realizado": "Realizado"}, inplace=True)

                    budget_mes["CONTA"] = budget_mes["CONTA"].astype(str).str.strip()
                    gastos_agrupados["CONTA"] = gastos_agrupados["CONTA"].astype(str).str.strip()

                    df_comparativo = pd.merge(budget_mes, gastos_agrupados, on="CONTA", how="left").fillna(0)
                    df_comparativo["Saldo Restante"] = df_comparativo["Valor Budget"] - df_comparativo["Realizado"]
                    
                    df_exibicao = df_comparativo[["CONTA", "TIPO 1", "Valor Budget", "Realizado", "Saldo Restante"]]

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Budget do Mês", f"R$ {df_exibicao['Valor Budget'].sum():,.2f}")
                    m2.metric("Realizado do Mês", f"R$ {df_exibicao['Realizado'].sum():,.2f}")
                    m3.metric("Saldo do Mês", f"R$ {df_exibicao['Saldo Restante'].sum():,.2f}")

                    def pintar_estouro(row):
                        if row["Saldo Restante"] < 0:
                            return ['background-color: #ffe6e6; color: #990000'] * len(row)
                        return [''] * len(row)

                    st.write(f"### Detalhamento das Contas - {mes_selecionado}")
                    st.dataframe(
                        df_exibicao.style.apply(pintar_estouro, axis=1).format({
                            "Valor Budget": "R$ {:,.2f}",
                            "Realizado": "R$ {:,.2f}",
                            "Saldo Restante": "R$ {:,.2f}"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
        except Exception as e:
            st.error(f"Erro ao carregar o dashboard: {e}")
