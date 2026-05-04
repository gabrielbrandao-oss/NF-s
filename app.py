import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Controladoria: Custos vs Budget", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("https://docs.google.com/spreadsheets/d/1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI/edit?gid=1615718475#gid=1615718475")
drive_folder_id = st.sidebar.text_input("11h3UccF6JH_8SQOUL_HhJZ9beIUQB4kp (Opcional)")

# --- ESCOPOS UNIFICADOS PARA DRIVE E SHEETS ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# --- FUNÇÕES DE AUTENTICAÇÃO E APIs ---
def get_credentials():
    """Lê as credenciais do cofre do Streamlit em vez de um arquivo físico"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    except KeyError:
        st.error("⚠️ Credenciais não encontradas nos Secrets do Streamlit! Verifique as configurações do painel.")
        st.stop()

def get_google_client():
    """Autentica com o Gspread (Sheets)"""
    creds = get_credentials()
    return gspread.authorize(creds)

def upload_to_drive(file, folder_id):
    """Faz o upload do PDF da Nota Fiscal para o Google Drive"""
    try:
        gauth = GoogleAuth()
        gauth.credentials = get_credentials()
        drive = GoogleDrive(gauth)
        file_drive = drive.CreateFile({'title': file.name, 'parents': [{'id': folder_id}]})
        
        with open(file.name, "wb") as f:
            f.write(file.getbuffer())
        
        file_drive.SetContentFile(file.name)
        file_drive.Upload()
        os.remove(file.name) # Limpa o cache local
        return file_drive['alternateLink']
    except Exception as e:
        st.error(f"Erro no upload do Drive: {e}")
        return None

# --- FUNÇÃO DE LIMPEZA FINANCEIRA EXTREMA ---
def limpeza_final(val):
    """Garante que qualquer formato (R$ 1.500,00 ou 1500.00 ou 1,500.00) vire número puro no Python"""
    if val is None or val == "": 
        return 0.0
    if isinstance(val, (int, float)): 
        return float(val)
    
    # Remove R$, espaços e caracteres invisíveis
    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s: 
        return 0.0
    
    # Se houver ponto e vírgula (ex: 1.234,56), remove o ponto de milhar e troca a vírgula decimal
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    # Se houver apenas vírgula decimal (ex: 1234,56)
    elif "," in s:
        s = s.replace(",", ".")
        
    return pd.to_numeric(s, errors='coerce') or 0.0

# --- APLICATIVO PRINCIPAL ---
st.title("📊 Painel de Custos Mensal (Padrão SAP)")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL completa da Planilha Google na barra lateral para iniciar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "📉 Dashboard Budget x Realizado"])

    # ==========================================
    # TAB 1: FORMULÁRIO DE ENTRADA DE NOTA FISCAL
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
                conta_sap = st.text_input("Conta SAP", help="Ex: 4.1.02.01.0001 (Deve existir na aba Budget)")
                arquivo_nf = st.file_uploader("Upload da NF (PDF/Imagem)", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento no Sheets")

        if submit:
            if nf_num and conta_sap:
                with st.spinner("Conectando ao Google e registrando nota..."):
                    # 1. Enviar anexo para o Drive
                    link_nf = "Sem Anexo / Drive não configurado" 
                    if arquivo_nf and drive_folder_id:
                        link_nf = upload_to_drive(arquivo_nf, drive_folder_id) or "Erro ao gerar link"

                    try:
                        # 2. Conectar à Planilha
                        client = get_google_client()
                        sheet = client.open_by_url(spreadsheet_url)
                        worksheet = sheet.worksheet("Lancamentos")
                        
                        # 3. Mapear as 37 Colunas
                        cabecalhos = worksheet.row_values(1)
                        nova_linha = [""] * len(cabecalhos)
                        
                        # Colocamos os dados exatamente nas colunas com estes nomes:
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
                                
                        # 4. Gravar a linha
                        worksheet.append_row(nova_linha)
                        st.success(f"✅ Nota {nf_num} contabilizada na Conta {conta_sap} com sucesso!")
                        
                    except Exception as e:
                        import traceback
                        st.error("Erro ao salvar na planilha. Veja o detalhe técnico abaixo:")
                        st.code(traceback.format_exc())
            else:
                st.error("⚠️ Os campos 'Nº NF' e 'Conta SAP' são obrigatórios.")

    # ==========================================
    # TAB 2: DASHBOARD DE CONFRONTO
    # ==========================================
    with tab2:
        st.subheader("Análise: Orçamento vs. Realizado")
        
        try:
            # 1. Puxar os dados da nuvem
            client = get_google_client()
            sheet = client.open_by_url(spreadsheet_url)
            
            raw_lanc = sheet.worksheet("Lancamentos").get_all_records()
            raw_budget = sheet.worksheet("Budget").get_all_records()
            
            df_lanc = pd.DataFrame(raw_lanc)
            df_budget = pd.DataFrame(raw_budget)

            if df_budget.empty:
                st.info("Aguardando configuração de metas na aba 'Budget'.")
            else:
                # 2. Limpeza Numérica Segura
                df_lanc["Realizado_Limpo"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
                df_budget["Budget_Limpo"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)

                # 3. Tratamento de Datas (Garante que 05/01/2026 seja interpretado como Janeiro)
                df_lanc["Data_Proc"] = pd.to_datetime(df_lanc.get("Data de lançamento"), dayfirst=True, errors='coerce')
                df_budget["Data_Proc"] = pd.to_datetime(df_budget.get("MÊS"), dayfirst=True, errors='coerce')
                
                df_lanc["Mes_Ano"] = df_lanc["Data_Proc"].dt.strftime('%m/%Y')
                df_budget["Mes_Ano"] = df_budget["Data_Proc"].dt.strftime('%m/%Y')

                # 4. Filtro na Tela (Drop-down de Meses)
                meses = sorted(df_budget["Mes_Ano"].dropna().unique().tolist())
                if not meses:
                    st.warning("Não encontrei datas válidas na aba Budget (Use o formato DD/MM/AAAA).")
                else:
                    mes_selecionado = st.selectbox("Selecione a Competência (Mês/Ano):", meses)

                    # Filtrar pelo Mês
                    b_mes = df_budget[df_budget["Mes_Ano"] == mes_selecionado].copy()
                    l_mes = df_lanc[df_lanc["Mes_Ano"] == mes_selecionado].copy()

                    # 5. Agrupar Lançamentos por Conta
                    if "Conta SAP" not in l_mes.columns:
                        l_mes["Conta SAP"] = ""
                        
                    # Remove espaços em branco do início/fim das contas para não falhar o cruzamento
                    l_mes["Conta SAP"] = l_mes["Conta SAP"].astype(str).str.strip()
                    b_mes["CONTA"] = b_mes.get("CONTA", pd.Series()).astype(str).str.strip()

                    realizado_agrupado = l_mes.groupby("Conta SAP")["Realizado_Limpo"].sum().reset_index()
                    realizado_agrupado.columns = ["CONTA", "Soma_Realizado"]

                    # 6. Cruzar Budget x Realizado (PROCV)
                    df_final = pd.merge(b_mes, realizado_agrupado, on="CONTA", how="left").fillna(0)
                    df_final["Saldo"] = df_final["Budget_Limpo"] - df_final["Soma_Realizado"]

                    # 7. Exibição das Métricas Principais
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Budget Planejado", f"R$ {df_final['Budget_Limpo'].sum():,.2f}")
                    m2.metric("Soma Realizado", f"R$ {df_final['Soma_Realizado'].sum():,.2f}")
                    m3.metric("Saldo Disponível", f"R$ {df_final['Saldo'].sum():,.2f}")

                    # 8. Exibição da Tabela Analítica
                    st.write("### Detalhamento por Conta Contábil")
                    
                    def pintar_estouro(row):
                        if row["Saldo"] < 0:
                            return ['background-color: #ffe6e6; color: #990000'] * len(row)
                        return [''] * len(row)

                    st.dataframe(
                        df_final[["CONTA", "TIPO 1", "Budget_Limpo", "Soma_Realizado", "Saldo"]]
                        .style.apply(pintar_estouro, axis=1)
                        .format({
                            "Budget_Limpo": "R$ {:,.2f}",
                            "Soma_Realizado": "R$ {:,.2f}",
                            "Saldo": "R$ {:,.2f}"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

                    # 9. Área de Auditoria / Debug (Escondida em um expansor)
                    with st.expander("🔍 Auditoria: O que o sistema está lendo para este mês?"):
                        st.write("Verifique se os valores lidos ('Realizado_Limpo') estão corretos. Se um lançamento não estiver aqui, verifique se a data e a conta SAP estão digitadas corretamente no Sheets.")
                        st.dataframe(l_mes[["Data de lançamento", "Conta SAP", "Nº NF", "Total da linha", "Realizado_Limpo"]])

        except Exception as e:
            import traceback
            st.error("Erro técnico ao carregar o dashboard. Detalhe:")
            st.code(traceback.format_exc())
