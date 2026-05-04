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
spreadsheet_url = st.sidebar.text_input("https://docs.google.com/spreadsheets/d/1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI/edit?gid=0#gid=0")
drive_folder_id = st.sidebar.text_input("11h3UccF6JH_8SQOUL_HhJZ9beIUQB4kp (Opcional)")

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

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
        st.error(f"Erro no upload do Drive: {e}")
        return None

def limpeza_final(val):
    """Transforma qualquer formato de moeda em número puro para cálculos"""
    if val is None or val == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s: return 0.0
    if "." in s and "," in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    return pd.to_numeric(s, errors='coerce') or 0.0

# --- APLICATIVO PRINCIPAL ---
st.title("📊 Sistema SAP & B.I. Explorer")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL completa da Planilha Google na barra lateral para iniciar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "🛠️ B.I. Explorer (Análise Livre)"])

    # ==========================================
    # TAB 1: FORMULÁRIO DE ENTRADA (MANTIDO)
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
                arquivo_nf = st.file_uploader("Upload da NF (PDF/Imagem)", type=["pdf", "png", "jpg"])

            submit = st.form_submit_button("🚀 Gravar Lançamento no Sheets")

        if submit:
            if nf_num and conta_sap:
                with st.spinner("Registrando nota..."):
                    link_nf = "Sem Anexo" 
                    if arquivo_nf and drive_folder_id:
                        link_nf = upload_to_drive(arquivo_nf, drive_folder_id) or "Erro no link"
                    try:
                        client = get_google_client()
                        sheet = client.open_by_url(spreadsheet_url)
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
                            if col_nome in cabecalhos:
                                nova_linha[cabecalhos.index(col_nome)] = valor
                                
                        worksheet.append_row(nova_linha)
                        st.success(f"✅ Nota {nf_num} gravada com sucesso!")
                    except Exception as e:
                        import traceback
                        st.error("Erro ao salvar. Detalhe:")
                        st.code(traceback.format_exc())
            else:
                st.error("⚠️ 'Nº NF' e 'Conta SAP' são obrigatórios.")

    # ==========================================
    # TAB 2: B.I. EXPLORER (ESTILO METABASE)
    # ==========================================
    with tab2:
        st.subheader("B.I. Customizado: Monte a sua análise")
        
        try:
            client = get_google_client()
            sheet = client.open_by_url(spreadsheet_url)
            
            # 1. Carrega os dados brutos e já limpa os valores monetários
            df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
            df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())
            
            if not df_lanc.empty:
                df_lanc["Valor (Numérico)"] = df_lanc.get("Total da linha", pd.Series()).apply(limpeza_final)
            if not df_budget.empty:
                df_budget["Valor (Numérico)"] = df_budget.get("BUDGET", pd.Series()).apply(limpeza_final)

            # 2. Escolha da Base de Dados
            base_escolhida = st.radio(
                "Qual base você quer analisar?", 
                ["Lançamentos Realizados (NFs)", "Budget (Metas)"], 
                horizontal=True
            )
            
            df_alvo = df_lanc.copy() if base_escolhida == "Lançamentos Realizados (NFs)" else df_budget.copy()

            if df_alvo.empty:
                st.warning(f"A base '{base_escolhida}' está vazia.")
            else:
                st.markdown("---")
                st.markdown("### 1️⃣ Filtros (Opcional)")
                
                # O usuário escolhe quais colunas ele quer usar para filtrar
                colunas_filtro = st.multiselect("Quero filtrar as informações por:", df_alvo.columns.tolist())
                
                # Gera as caixinhas de filtro dinamicamente
                for col in colunas_filtro:
                    valores_unicos = df_alvo[col].astype(str).unique().tolist()
                    selecao = st.multiselect(f"Selecione os valores de '{col}':", valores_unicos, default=valores_unicos)
                    # Aplica o filtro no dataframe
                    df_alvo = df_alvo[df_alvo[col].astype(str).isin(selecao)]

                st.markdown("---")
                st.markdown("### 2️⃣ Agrupamento e Métricas (Pivot)")
                
                c1, c2 = st.columns(2)
                with c1:
                    # Linhas da Tabela Dinâmica
                    padrao_linhas = ["Conta SAP"] if base_escolhida == "Lançamentos Realizados (NFs)" and "Conta SAP" in df_alvo.columns else []
                    linhas_agrupamento = st.multiselect(
                        "Agrupar dados por (Ex: Mês, Fornecedor, Conta):", 
                        df_alvo.columns.tolist(), 
                        default=padrao_linhas
                    )
                    
                with c2:
                    # Valores para somar (Filtra apenas colunas numéricas geradas pela limpeza)
                    colunas_numericas = df_alvo.select_dtypes(include='number').columns.tolist()
                    valores_soma = st.multiselect(
                        "O que você quer somar? (Métricas):", 
                        colunas_numericas, 
                        default=["Valor (Numérico)"] if "Valor (Numérico)" in colunas_numericas else []
                    )

                # 3. Gerador do Relatório
                if linhas_agrupamento and valores_soma:
                    # Agrupa e soma
                    df_relatorio = df_alvo.groupby(linhas_agrupamento)[valores_soma].sum().reset_index()
                    
                    st.markdown("### 📊 Resultado da Análise")
                    
                    # Mostra os cartões com os totais gerais da visão atual
                    col_mets = st.columns(len(valores_soma))
                    for i, val_col in enumerate(valores_soma):
                        col_mets[i].metric(f"Soma Total: {val_col}", f"R$ {df_relatorio[val_col].sum():,.2f}")
                    
                    # Mostra a Tabela
                    st.dataframe(
                        df_relatorio.style.format({col: "R$ {:,.2f}" for col in valores_soma}),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Gráfico Dinâmico Automático
                    if len(linhas_agrupamento) == 1 and len(valores_soma) >= 1:
                        st.write(f"**Gráfico: {valores_soma[0]} por {linhas_agrupamento[0]}**")
                        st.bar_chart(df_relatorio.set_index(linhas_agrupamento[0])[valores_soma[0]])
                else:
                    st.info("👆 Selecione pelo menos uma coluna de Agrupamento e uma Métrica para gerar o relatório.")
                    
        except Exception as e:
            import traceback
            st.error("Erro ao processar dados no modo B.I. Detalhe técnico:")
            st.code(traceback.format_exc())
