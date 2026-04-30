import streamlit as st
import pandas as pd
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from streamlit_gsheets import GSheetsConnection
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="App Controladoria", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI")
drive_folder_id = st.sidebar.text_input("11h3UccF6JH_8SQOUL_HhJZ9beIUQB4kp (Opcional)")
JSON_KEY_FILE = 'suas-credenciais.json'

# --- FUNÇÃO PARA LIMPAR VALORES MONETÁRIOS DO SHEETS ---
def limpar_moeda(valor):
    """Converte 'R$ 1.500,00' do Sheets para 1500.00 no Python"""
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return pd.to_numeric(valor, errors='coerce')

# --- FUNÇÃO DE UPLOAD PARA O DRIVE ---
def upload_to_drive(file, folder_id):
    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        gauth = GoogleAuth()
        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
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

# --- APLICATIVO PRINCIPAL ---
st.title("📊 Painel de Custos Mensal")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha na barra lateral para começar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "📉 Dashboard Budget"])

    # --- TAB 1: FORMULÁRIO DE ENTRADA (MANTIDO) ---
    with tab1:
        st.subheader("Novo Lançamento (Padrão SAP)")
        with st.form("form_nf", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                nf_num = st.text_input("Nº NF")
                fornecedor = st.text_input("Fornecedor")
            with col2:
                data_lanc = st.date_input("Data de lançamento")
                valor_bruto = st.number_input("Total documento (R$)", min_value=0.0, format="%.2f")
            with col3:
                conta_sap = st.text_input("Conta SAP", help="Ex: 4.1.02.01.0001")
                arquivo_nf = st.file_uploader("Upload da NF", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento")

        if submit:
            if nf_num and conta_sap:
                with st.spinner("Registrando nota..."):
                    link_nf = "Sem Anexo/Drive não configurado" 
                    if arquivo_nf and drive_folder_id:
                        link_nf = upload_to_drive(arquivo_nf, drive_folder_id) or "Erro no Link"

                    novo_registro = pd.DataFrame([{
                        "Nº NF": nf_num,
                        "Nome do cliente/fornecedor": fornecedor,
                        "Data de lançamento": data_lanc.strftime("%d/%m/%Y"),
                        "Total documento": valor_bruto,
                        "Conta SAP": conta_sap,
                        "Referência da Nota Fiscal": link_nf
                    }])

                    try:
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_antigo = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
                        df_final = pd.concat([df_antigo, novo_registro], ignore_index=True)
                        conn.update(spreadsheet=spreadsheet_url, worksheet="Lancamentos", data=df_final)
                        st.success(f"Nota {nf_num} salva na Conta {conta_sap} com sucesso!")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
            else:
                st.error("Preencha Nº NF e Conta SAP.")

    # --- TAB 2: CONFRONTO BUDGET MENSAL ---
    with tab2:
        st.subheader("Análise Mensal: Orçamento vs. Realizado")
        
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            # 1. Puxar os dados
            df_lanc = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
            df_budget = conn.read(spreadsheet=spreadsheet_url, worksheet="Budget")

            # 2. Limpar e padronizar os Dados Financeiros
            df_budget["Valor Budget"] = df_budget["BUDGET"].apply(limpar_moeda).fillna(0)
            df_lanc["Valor Realizado"] = df_lanc["Total documento"].apply(limpar_moeda).fillna(0)

            # 3. Padronizar as Datas para criar o Filtro de Mês/Ano (MM/YYYY)
            # Para o Budget (Ex: de '01/01/2026' para '01/2026')
            df_budget["Competência"] = pd.to_datetime(df_budget["MÊS"], format='%d/%m/%Y', errors='coerce').dt.strftime('%m/%Y')
            
            # Para os Lançamentos (Ex: da Data da NF para '01/2026')
            df_lanc["Competência"] = pd.to_datetime(df_lanc["Data de lançamento"], format='%d/%m/%Y', errors='coerce').dt.strftime('%m/%Y')

            # 4. Criar o Filtro na Tela
            meses_disponiveis = sorted(df_budget["Competência"].dropna().unique().tolist())
            if not meses_disponiveis:
                st.warning("Não encontrei datas válidas na coluna MÊS da aba Budget. O formato deve ser DD/MM/AAAA.")
            else:
                mes_selecionado = st.selectbox("Selecione a Competência (Mês/Ano):", meses_disponiveis)

                # 5. Filtrar os dados apenas para o mês selecionado
                budget_mes = df_budget[df_budget["Competência"] == mes_selecionado]
                lanc_mes = df_lanc[df_lanc["Competência"] == mes_selecionado]

                # 6. Agrupar os gastos reais do mês por Conta
                gastos_agrupados = lanc_mes.groupby("Conta SAP")["Valor Realizado"].sum().reset_index()
                gastos_agrupados.rename(columns={"Conta SAP": "CONTA", "Valor Realizado": "Realizado"}, inplace=True)

                # Garantir que a coluna CONTA seja texto para o cruzamento funcionar perfeitamente
                budget_mes["CONTA"] = budget_mes["CONTA"].astype(str).str.strip()
                gastos_agrupados["CONTA"] = gastos_agrupados["CONTA"].astype(str).str.strip()

                # 7. Cruzar Budget do Mês x Gastos do Mês
                df_comparativo = pd.merge(budget_mes, gastos_agrupados, on="CONTA", how="left").fillna(0)
                
                # 8. Calcular Saldo
                df_comparativo["Saldo Restante"] = df_comparativo["Valor Budget"] - df_comparativo["Realizado"]
                
                # Organizar as colunas para exibição bonita
                df_exibicao = df_comparativo[["CONTA", "TIPO 1", "Valor Budget", "Realizado", "Saldo Restante"]]

                # --- EXIBIÇÃO DO DASHBOARD ---
                m1, m2, m3 = st.columns(3)
                m1.metric("Budget do Mês", f"R$ {df_exibicao['Valor Budget'].sum():,.2f}")
                m2.metric("Realizado do Mês", f"R$ {df_exibicao['Realizado'].sum():,.2f}")
                m3.metric("Saldo do Mês", f"R$ {df_exibicao['Saldo Restante'].sum():,.2f}")

                # Função para pintar a linha de vermelho se estourar
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
            st.error(f"Erro ao processar dados. Verifique as abas da planilha. Detalhe técnico: {e}")
