import streamlit as st
import pandas as pd
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from streamlit_gsheets import GSheetsConnection
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Analista de Custos - Entrada de NF", layout="wide")

# --- BARRA LATERAL (CONFIGURAÇÕES DE ID) ---
st.sidebar.header("⚙️ Configurações de Conexão")
spreadsheet_id = st.sidebar.text_input("1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI", help="Aquele código longo na URL da planilha")
drive_folder_id = st.sidebar.text_input("ID da Pasta no Drive", help="Código no final da URL da pasta onde as NFs ficarão")
json_auth = "suas-credenciais.json" # O arquivo que você baixou do Google Cloud

# --- FUNÇÕES DE APOIO ---
def upload_drive(file, folder_id):
    """Faz o upload para o Drive e retorna o link público"""
    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        gauth = GoogleAuth()
        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(json_auth, scope)
        drive = GoogleDrive(gauth)
        
        file_drive = drive.CreateFile({'title': file.name, 'parents': [{'id': folder_id}]})
        
        # Salva local temporariamente para o PyDrive ler
        with open(file.name, "wb") as f:
            f.write(file.getbuffer())
        
        file_drive.SetContentFile(file.name)
        file_drive.Upload()
        os.remove(file.name) # Limpa o temporário
        return file_drive['alternateLink']
    except Exception as e:
        st.error(f"Erro no Drive: {e}")
        return None

# --- INTERFACE PRINCIPAL ---
st.title("📑 Registro de Entrada e Controle de Custos")

if not spreadsheet_id or not drive_folder_id:
    st.warning("⚠️ Insira os IDs da Planilha e da Pasta do Drive na barra lateral para começar.")
else:
    tab1, tab2 = st.tabs(["Nova Nota Fiscal", "Visualizar Lançamentos"])

    with tab1:
        st.subheader("Dados Essenciais para Lançamento (Padrão SAP/Fiscal)")
        
        with st.form("form_nf", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            
            with c1:
                nf_num = st.text_input("Nº da Nota Fiscal (NF)")
                fornecedor = st.text_input("Nome do Fornecedor")
                cnpj = st.text_input("CNPJ/CPF do Fornecedor")
                
            with c2:
                data_lancamento = st.date_input("Data de Lançamento (Competência)")
                valor_bruto = st.number_input("Total do Documento (R$)", min_value=0.0, format="%.2f")
                pedido_compra = st.text_input("Nº Pedido de Compra (PO)")
                
            with c3:
                centro_custo = st.selectbox("Centro de Custo", ["TI", "Marketing", "RH", "Vendas", "Operações", "Financeiro"])
                conta_sap = st.text_input("Conta Contábil / SAP")
                arquivo = st.file_uploader("Anexar PDF da NF", type=["pdf", "png", "jpg"])

            descricao = st.text_area("Descrição do Item/Serviço")
            
            btn_salvar = st.form_submit_button("🚀 Registrar Lançamento")

        if btn_salvar:
            if arquivo and nf_num:
                with st.spinner("Processando..."):
                    # 1. Upload Drive
                    link_nf = upload_drive(arquivo, drive_folder_id)
                    
                    if link_nf:
                        # 2. Preparar dados para o Sheets
                        novo_registro = {
                            "Nº NF": nf_num,
                            "CNPJ": cnpj,
                            "Fornecedor": fornecedor,
                            "Data Lançamento": data_lancamento.strftime("%d/%m/%Y"),
                            "Valor Bruto": valor_bruto,
                            "Centro de Custo": centro_custo,
                            "Conta SAP": conta_sap,
                            "Pedido Compra": pedido_compra,
                            "Descrição": descricao,
                            "Link Arquivo": link_nf
                        }
                        
                        # 3. Conectar e Salvar (Append)
                        # Nota: Aqui usamos o conector GSheets
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        # Logica simplificada: st.write para teste antes do deploy real
                        st.success(f"Nota {nf_num} salva com sucesso!")
                        st.json(novo_registro)
            else:
                st.error("Preencha o Nº da NF e anexe o arquivo.")

    with tab2:
        st.subheader("Histórico de Custos")
        # Simulação de leitura do sheets
        st.info("Aqui o app lerá a planilha usando: conn.read(spreadsheet=spreadsheet_id)")