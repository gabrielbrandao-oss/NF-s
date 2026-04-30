import streamlit as st
import pandas as pd
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from streamlit_gsheets import GSheetsConnection
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="App Controladoria - SAP & Budget", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI")
drive_folder_id = st.sidebar.text_input("11h3UccF6JH_8SQOUL_HhJZ9beIUQB4kp")
JSON_KEY_FILE = 'suas-credenciais.json'

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
        st.error(f"Erro ao enviar para o Drive: {e}")
        return None

# --- APLICATIVO PRINCIPAL ---
st.title("📊 Painel de Custos: Lançamentos vs. Budget")

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
                fornecedor = st.text_input("Nome do cliente/fornecedor")
                cnpj = st.text_input("CNPJ ou CPF")
                
            with col2:
                data_lanc = st.date_input("Data de lançamento")
                valor_bruto = st.number_input("Total documento (R$)", min_value=0.0, format="%.2f")
                pedido = st.text_input("Num Pedido de Compra")
                
            with col3:
                conta_sap = st.text_input("Conta SAP", help="Deve bater com a coluna CONTA do Budget")
                centro_custo = st.text_input("Centro de Custos")
                arquivo_nf = st.file_uploader("Upload da NF", type=["pdf", "png", "jpg"])

            descricao = st.text_area("Descrição do item/serviço")
            submit = st.form_submit_button("🚀 Gravar Lançamento")

        if submit:
            if arquivo_nf and nf_num and conta_sap:
                with st.spinner("Registrando nota e processando anexo..."):
                    
                    # 1. Upload do Arquivo
                    link_nf = "Simulação sem ID do Drive" 
                    if drive_folder_id:
                        link_nf = upload_to_drive(arquivo_nf, drive_folder_id) or "Erro no Link"

                    # 2. Montar os dados EXACTAMENTE com os nomes das colunas da sua planilha
                    novo_registro = pd.DataFrame([{
                        "Nº NF": nf_num,
                        "Nr. NF": nf_num, # Preenchendo as duas colunas que parecem similares
                        "Nome do cliente/fornecedor": fornecedor,
                        "CNPJ ou CPF": cnpj,
                        "Data de lançamento": data_lanc.strftime("%d/%m/%Y"),
                        "Total documento": valor_bruto,
                        "Total da linha": valor_bruto,
                        "Centro de Custos": centro_custo,
                        "Conta SAP": conta_sap,
                        "Num Pedido de Compra": pedido,
                        "Descrição do item/serviço": descricao,
                        "Referência da Nota Fiscal": link_nf, # Usando esta coluna para o link
                        "Status Documento": "Inserido via App"
                    }])

                    # 3. Salvar no Sheets
                    try:
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_antigo = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
                        
                        # Concatena preservando todas as outras dezenas de colunas vazias (Pandas lida com isso preenchendo com NaN)
                        df_final = pd.concat([df_antigo, novo_registro], ignore_index=True)
                        conn.update(spreadsheet=spreadsheet_url, worksheet="Lancamentos", data=df_final)
                        
                        st.success(f"Nota {nf_num} contabilizada na Conta SAP {conta_sap} com sucesso!")
                    except Exception as e:
                        st.error(f"Erro na conexão com o Sheets: {e}")
            else:
                st.error("Preencha Nº NF, Conta SAP e anexe a nota.")

    # --- TAB 2: CONFRONTO BUDGET ---
    with tab2:
        st.subheader("Análise: Orçamento vs. Realizado")
        
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            # Ler as duas abas
            df_lanc = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
            df_budget = conn.read(spreadsheet=spreadsheet_url, worksheet="Budget")

            # Converter coluna de valor para número (caso venha como texto do Sheets)
            df_lanc["Total documento"] = pd.to_numeric(df_lanc["Total documento"], errors='coerce').fillna(0)
            df_budget["BUDGET"] = pd.to_numeric(df_budget["BUDGET"], errors='coerce').fillna(0)

            # 1. Somar os gastos agrupando pela "Conta SAP"
            gastos_conta = df_lanc.groupby("Conta SAP")["Total documento"].sum().reset_index()
            gastos_conta.columns = ["CONTA", "Realizado"] # Renomeia para bater com a aba Budget

            # Garantir que a coluna CONTA seja do mesmo tipo nas duas tabelas (string para evitar bugs de merge)
            df_budget["CONTA"] = df_budget["CONTA"].astype(str).str.strip()
            gastos_conta["CONTA"] = gastos_conta["CONTA"].astype(str).str.strip()

            # 2. Fazer o cruzamento (PROCV)
            df_comparativo = pd.merge(df_budget, gastos_conta, on="CONTA", how="left").fillna(0)
            
            # 3. Cálculos de Variação
            df_comparativo["Saldo Restante"] = df_comparativo["BUDGET"] - df_comparativo["Realizado"]
            
            def colorir_linha(row):
                if row["Saldo Restante"] < 0:
                    return ['background-color: #ffe6e6'] * len(row) # Vermelho se estourar
                return [''] * len(row)

            # --- EXIBIÇÃO ---
            m1, m2, m3 = st.columns(3)
            m1.metric("Budget Total (Todas as Contas)", f"R$ {df_comparativo['BUDGET'].sum():,.2f}")
            m2.metric("Total Realizado (NF)", f"R$ {df_comparativo['Realizado'].sum():,.2f}")
            m3.metric("Saldo Geral", f"R$ {df_comparativo['Saldo Restante'].sum():,.2f}")

            st.write("### Desempenho por Conta Contábil")
            st.dataframe(
                df_comparativo.style.apply(colorir_linha, axis=1).format({
                    "BUDGET": "R$ {:.2f}",
                    "Realizado": "R$ {:.2f}",
                    "Saldo Restante": "R$ {:.2f}"
                }),
                use_container_width=True
            )

        except Exception as e:
            st.info(f"Ocorreu um erro ao gerar o dashboard. Verifique se as abas estão preenchidas. Detalhe: {e}")
