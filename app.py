import streamlit as st
import pandas as pd
import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from streamlit_gsheets import GSheetsConnection
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Custos & Budget", layout="wide")

# --- 2. CONFIGURAÇÕES NA BARRA LATERAL ---
st.sidebar.header("⚙️ Configurações de Conexão")
spreadsheet_url = st.sidebar.text_input("URL da Planilha Google")
drive_folder_id = st.sidebar.text_input("ID da Pasta no Drive (para as NFs)")

# O arquivo JSON deve estar no diretório raiz ou configurado nos Secrets do Streamlit
# Para deploy, usaremos o nome padrão buscado pelo PyDrive2
JSON_KEY_FILE = 'suas-credenciais.json' 

# --- 3. FUNÇÕES DE SUPORTE (DRIVE) ---
def upload_to_drive(file, folder_id):
    try:
        scope = ["https://www.googleapis.com/auth/drive"]
        gauth = GoogleAuth()
        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        drive = GoogleDrive(gauth)
        
        file_drive = drive.CreateFile({'title': file.name, 'parents': [{'id': folder_id}]})
        
        # Guardar temporariamente para upload
        with open(file.name, "wb") as f:
            f.write(file.getbuffer())
        
        file_drive.SetContentFile(file.name)
        file_drive.Upload()
        os.remove(file.name) # Elimina o ficheiro temporário
        return file_drive['alternateLink']
    except Exception as e:
        st.error(f"Erro no Drive: {e}")
        return None

# --- 4. INTERFACE PRINCIPAL ---
st.title("📊 Sistema de Gestão Contabilística & Budget")

if not spreadsheet_url or not drive_folder_id:
    st.warning("⚠️ Por favor, preencha a URL da Planilha e o ID da pasta do Drive na barra lateral.")
else:
    tab1, tab2 = st.tabs(["📥 Lançamento de NF", "📈 Confronto Budget"])

    # --- TAB 1: FORMULÁRIO DE ENTRADA ---
    with tab1:
        st.subheader("Registo de Nova Nota Fiscal")
        with st.form("form_entrada", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nf = st.text_input("Nº Nota Fiscal")
                fornecedor = st.text_input("Fornecedor")
                data = st.date_input("Data de Lançamento (Competência)")
                valor = st.number_input("Valor Bruto (R$)", min_value=0.0, format="%.2f")
            
            with col2:
                cc = st.selectbox("Centro de Custo", ["TI", "Marketing", "RH", "Operações", "Vendas", "Financeiro"])
                conta = st.text_input("Conta SAP / Contábil")
                arquivo_nf = st.file_uploader("Upload do PDF da NF", type=["pdf", "png", "jpg"])
            
            submit = st.form_submit_button("🚀 Gravar e Enviar NF")

        if submit:
            if arquivo_nf and nf:
                with st.spinner("A processar lançamento..."):
                    # 1. Enviar para o Drive
                    link_drive = upload_to_drive(arquivo_nf, drive_folder_id)
                    
                    if link_drive:
                        # 2. Ligar ao Sheets
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        
                        # Criar novo registo
                        novo_dado = pd.DataFrame([{
                            "Nº NF": nf,
                            "Fornecedor": fornecedor,
                            "Data Lançamento": data.strftime("%d/%m/%Y"),
                            "Valor Bruto": valor,
                            "Centro de Custo": cc,
                            "Conta SAP": conta,
                            "Link NF": link_drive
                        }])

                        # Ler dados existentes, concatenar e atualizar
                        try:
                            df_antigo = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
                            df_final = pd.concat([df_antigo, novo_dado], ignore_index=True)
                            conn.update(spreadsheet=spreadsheet_url, worksheet="Lancamentos", data=df_final)
                            st.success(f"Sucesso! NF {nf} registada e arquivo salvo no Drive.")
                        except Exception as e:
                            st.error(f"Erro ao atualizar Sheets: {e}")
            else:
                st.error("Preencha o Nº da NF e anexe o ficheiro.")

    # --- TAB 2: DASHBOARD DE CONFRONTO ---
    with tab2:
        st.subheader("Análise Realizado vs. Orçado")
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        try:
            # Ler as duas abas cruciais
            df_gastos = conn.read(spreadsheet=spreadsheet_url, worksheet="Lancamentos")
            df_budget = conn.read(spreadsheet=spreadsheet_url, worksheet="Budget")

            # Processar Realizado
            resumo_gastos = df_gastos.groupby("Centro de Custo")["Valor Bruto"].sum().reset_index()
            resumo_gastos.columns = ["Centro de Custo", "Realizado"]

            # Cruzar (Merge) com o Budget
            df_final = pd.merge(df_budget, resumo_gastos, on="Centro de Custo", how="left").fillna(0)
            
            # Cálculos de Performance
            df_final["Saldo"] = df_final["Valor Orçado"] - df_final["Realizado"]
            df_final["Status"] = df_final["Saldo"].apply(lambda x: "✅ Dentro" if x >= 0 else "❌ Estourou")

            # Métricas Gerais
            m1, m2, m3 = st.columns(3)
            m1.metric("Budget Total", f"R$ {df_final['Valor Orçado'].sum():,.2f}")
            m2.metric("Realizado Total", f"R$ {df_final['Realizado'].sum():,.2f}")
            m3.metric("Saldo Global", f"R$ {df_final['Saldo'].sum():,.2f}")

            # Tabela de Confronto
            st.dataframe(df_final.style.highlight_between(left=-1e12, right=-0.01, subset=['Saldo'], color='#ffcccc'), use_container_width=True)

            # Gráfico de Barras
            st.bar_chart(df_final.set_index("Centro de Custo")[["Valor Orçado", "Realizado"]])

        except Exception as e:
            st.info("Aguardando dados nas abas 'Lancamentos' e 'Budget' para gerar o confronto.")
