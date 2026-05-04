import streamlit as st
import pandas as pd
import os
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="App Controladoria SAP", layout="wide")

st.sidebar.header("⚙️ Configurações")
spreadsheet_url = st.sidebar.text_input("https://docs.google.com/spreadsheets/d/1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI/edit?gid=1615718475#gid=1615718475")
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
        st.error("⚠️ Credenciais não encontradas nos Secrets!")
        st.stop()

def get_google_client():
    return gspread.authorize(get_credentials())

def limpar_valor(valor):
    """Limpa R$, pontos e vírgulas para cálculo numérico"""
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return pd.to_numeric(valor, errors='coerce')

# --- APP PRINCIPAL ---
st.title("📊 Painel de Confronto: Budget vs Realizado (SAP)")

if not spreadsheet_url:
    st.warning("⚠️ Insira a URL da Planilha para começar.")
else:
    tab1, tab2 = st.tabs(["📥 Entrada de NF", "📉 Dashboard de Budget"])

    with tab1:
        st.info("Formulário de entrada configurado para as colunas SAP.")
        # (O formulário de entrada segue a lógica anterior, salvando nas colunas mapeadas)

    with tab2:
        st.subheader("Análise Mensal de Custos")
        
        try:
            client = get_google_client()
            sheet = client.open_by_url(spreadsheet_url)
            
            # 1. Carregar dados das abas
            df_lanc = pd.DataFrame(sheet.worksheet("Lancamentos").get_all_records())
            df_budget = pd.DataFrame(sheet.worksheet("Budget").get_all_records())

            if df_budget.empty:
                st.warning("A aba 'Budget' está vazia.")
            else:
                # 2. Padronização Financeira (Coluna L para Realizado e Coluna D para Budget)
                df_lanc["Realizado_Num"] = df_lanc["Total da linha"].apply(limpar_valor).fillna(0)
                df_budget["Budget_Num"] = df_budget["BUDGET"].apply(limpar_valor).fillna(0)

                # 3. Padronização de Datas (Coluna D em Lançamentos e Coluna A em Budget)
                df_lanc["Mes_Ano"] = pd.to_datetime(df_lanc["Data de lançamento"], dayfirst=True, errors='coerce').dt.strftime('%m/%Y')
                df_budget["Mes_Ano"] = pd.to_datetime(df_budget["MÊS"], dayfirst=True, errors='coerce').dt.strftime('%m/%Y')

                # 4. Seletor de Mês
                lista_meses = sorted(df_budget["Mes_Ano"].dropna().unique().tolist())
                mes_foco = st.selectbox("Selecione o Mês para análise:", lista_meses)

                # 5. Filtrar dados do mês selecionado
                budget_foco = df_budget[df_budget["Mes_Ano"] == mes_foco].copy()
                lanc_foco = df_lanc[df_lanc["Mes_Ano"] == mes_foco].copy()

                # 6. Agrupar Realizado por Conta (Coluna AG -> 'Conta SAP')
                # Garantimos que as colunas de conta sejam strings para o cruzamento
                lanc_foco["Conta SAP"] = lanc_foco["Conta SAP"].astype(str).str.strip()
                realizado_agrupado = lanc_foco.groupby("Conta SAP")["Realizado_Num"].sum().reset_index()
                realizado_agrupado.columns = ["CONTA", "Valor_Realizado"]

                # 7. Cruzar com a aba Budget (Coluna B -> 'CONTA')
                budget_foco["CONTA"] = budget_foco["CONTA"].astype(str).str.strip()
                df_final = pd.merge(budget_foco, realizado_agrupado, on="CONTA", how="left").fillna(0)

                # 8. Cálculos Finais
                df_final["Diferença"] = df_final["Budget_Num"] - df_final["Valor_Realizado"]
                df_final["% Consumo"] = (df_final["Valor_Realizado"] / df_final["Budget_Num"] * 100).replace([float('inf'), -float('inf')], 0).fillna(0)

                # --- EXIBIÇÃO ---
                col1, col2, col3 = st.columns(3)
                total_b = df_final["Budget_Num"].sum()
                total_r = df_final["Valor_Realizado"].sum()
                
                col1.metric("Budget do Mês", f"R$ {total_b:,.2f}")
                col2.metric("Realizado do Mês", f"R$ {total_r:,.2f}", delta=f"{total_r-total_b:,.2f}", delta_color="inverse")
                col3.metric("Saldo Disponível", f"R$ {total_b - total_r:,.2f}")

                st.write(f"### Detalhado por Conta - Competência {mes_foco}")
                
                # Formatação visual
                def formatar_estouro(row):
                    color = 'background-color: #ffcccc' if row['Diferença'] < 0 else ''
                    return [color] * len(row)

                st.dataframe(
                    df_final[["CONTA", "TIPO 1", "Budget_Num", "Valor_Realizado", "Diferença", "% Consumo"]]
                    .style.apply(formatar_estouro, axis=1)
                    .format({
                        "Budget_Num": "R$ {:,.2f}",
                        "Valor_Realizado": "R$ {:,.2f}",
                        "Diferença": "R$ {:,.2f}",
                        "% Consumo": "{:.1f}%"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

        except Exception as e:
            import traceback
            st.error("Erro técnico no processamento das colunas SAP:")
            st.code(traceback.format_exc())
