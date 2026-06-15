# app_facilities_ia.py — Dashboard Facilities Cobli + Análise IA
# Link da planilha fixo em secrets.toml → url_planilha
# Análise de IA via Anthropic SDK (claude-sonnet-4-6)

import streamlit as st
import pandas as pd
import numpy as np
import gspread
import datetime
import json
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import anthropic
import logging

logging.basicConfig(level=logging.INFO)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Facilities Intelligence · Cobli",
    page_icon="🏢", layout="wide",
    initial_sidebar_state="collapsed",
)

# URL FIXA — não precisa digitar toda vez
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI/edit"

# ─── TEMA COBLI (dark) ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  background:#0d1117!important;color:#e6edf3!important;
  font-family:'Inter',-apple-system,sans-serif!important;}
[data-testid="stSidebar"]{background:#161b22!important;}
[data-testid="stHeader"]{background:#0d1117!important;}
[data-testid="stToolbar"],footer{display:none!important;}
section[data-testid="stMain"]>div{padding-top:12px!important;}
[data-testid="stMetric"]{background:#161b22;border:1px solid #21283a;
  border-radius:10px;padding:16px 20px!important;}
[data-testid="stMetricValue"]{color:#e6edf3!important;font-weight:700;font-size:1.4rem!important;}
[data-testid="stMetricLabel"]{color:#7d8590!important;font-size:.7rem!important;
  text-transform:uppercase;letter-spacing:.05em;}
[data-testid="stTabs"] button{background:#161b22!important;color:#7d8590!important;
  border-bottom:2px solid transparent!important;border-radius:0!important;
  font-size:.83rem;font-weight:500;padding:10px 18px;}
[data-testid="stTabs"] button[aria-selected="true"]{color:#2490d8!important;
  border-bottom-color:#2490d8!important;background:#0d1117!important;}
[data-testid="stSelectbox"]>div>div,[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input{background:#161b22!important;
  border:1px solid #21283a!important;border-radius:8px!important;
  color:#e6edf3!important;font-size:.83rem!important;}
[data-testid="stSelectbox"] svg{fill:#7d8590!important;}
[data-testid="stButton"]>button{background:#1d6fa4!important;color:#fff!important;
  border:none!important;border-radius:8px!important;font-weight:600!important;
  font-size:.83rem!important;padding:8px 18px!important;}
[data-testid="stButton"]>button:hover{background:#2490d8!important;}
[data-testid="stButton"]>button[kind="secondary"]{background:#161b22!important;
  border:1px solid #21283a!important;color:#e6edf3!important;}
[data-testid="stDataFrame"]{border:1px solid #21283a;border-radius:10px;overflow:hidden;}
[data-testid="stDataFrame"] th{background:#161b22!important;color:#7d8590!important;
  font-size:.72rem!important;text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid #21283a!important;}
[data-testid="stDataFrame"] td{color:#e6edf3!important;font-size:.8rem!important;
  border-color:#21283a!important;}
[data-testid="stExpander"]{background:#161b22!important;border:1px solid #21283a!important;
  border-radius:10px!important;}
[data-testid="stRadio"] label{color:#7d8590!important;font-size:.82rem!important;}
hr{border-color:#21283a!important;}
.stTextArea textarea{background:#161b22!important;border:1px solid #21283a!important;
  color:#e6edf3!important;font-size:.83rem!important;border-radius:8px!important;}
/* Card KPI */
.kpi-card{background:#161b22;border:1px solid #21283a;border-radius:10px;
  padding:16px 20px;margin-bottom:4px;}
.kpi-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;
  color:#7d8590;margin-bottom:4px;}
.kpi-val{font-size:1.4rem;font-weight:700;color:#e6edf3;line-height:1.2;}
.kpi-sub{font-size:.72rem;color:#7d8590;margin-top:3px;}
.green{color:#1da462!important;} .red{color:#e85454!important;}
.yellow{color:#d4a017!important;} .blue{color:#2490d8!important;}
/* IA box */
.ia-box{background:linear-gradient(135deg,rgba(36,144,216,.08),rgba(29,164,98,.05));
  border:1px solid rgba(36,144,216,.25);border-radius:12px;padding:20px 24px;
  margin-top:8px;}
.ia-header{font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;
  color:#2490d8;font-weight:600;margin-bottom:10px;}
.ia-content{font-size:.84rem;line-height:1.65;color:#c9d1d9;white-space:pre-wrap;}
/* Badge */
.badge{background:rgba(29,111,164,.15);color:#2490d8;
  border:1px solid rgba(36,144,216,.3);border-radius:20px;
  font-size:.7rem;font-weight:600;padding:2px 10px;margin-left:8px;}
.badge-ia{background:rgba(29,164,98,.12);color:#1da462;
  border:1px solid rgba(29,164,98,.3);border-radius:20px;
  font-size:.7rem;font-weight:600;padding:2px 10px;margin-left:6px;}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTES ──────────────────────────────────────────────────────────────
PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
C_BUD="#1d6fa4"; C_REAL="#1da462"; C_VERM="#e85454"; C_DELT="#d4a017"
PALETTE=["#2490d8","#1da462","#d4a017","#e85454","#a064c8",
         "#50c8c8","#e6823c","#78a05a","#c878a0","#6488dc"]
PLOTLY_BASE=dict(
    paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter,sans-serif",color="#7d8590",size=11),
    margin=dict(t=40,b=8,l=8,r=8),
    legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1,
                font=dict(size=10),bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor="#21283a",linecolor="#21283a",tickfont=dict(size=10,color="#7d8590")),
    yaxis=dict(gridcolor="#21283a",linecolor="#21283a",tickfont=dict(size=10,color="#7d8590")),
)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def fmt_mes(dt):
    if pd.isna(dt): return None
    try: return f"{PT[dt.month-1]}/{str(dt.year)[2:]}"
    except: return None

def mes_ord(m):
    if not m: return 9999
    try: mon,yr=m.split("/"); return int(yr)*12+PT.index(mon)
    except: return 9999

def brl(v):
    try:
        v=float(v)
        return f"R$ {abs(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "R$ 0,00"

def parse_num(s):
    s=str(s).replace("R$","").strip().replace(".","").replace(",",".")
    try: return float(s)
    except: return 0.0

def kpi(label,val,sub="",color=""):
    c=f' class="{color}"' if color else ""
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-val"{c}>{val}</div>
      <div class="kpi-sub">{sub}</div></div>""",unsafe_allow_html=True)

def title_l(txt):
    return dict(text=txt,font=dict(size=13,color="#e6edf3"),x=0,xanchor="left")

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def check_auth():
    # Busca senha — try/except porque st.secrets lança KeyError se a chave não existe
    pwd = ""
    for key in ["senha_app", "senha_app_hash", "SENHA_APP", "password"]:
        try:
            val = st.secrets[key]
            if val:
                pwd = str(val).strip()
                break
        except (KeyError, Exception):
            continue

    # Se não houver senha configurada, mostra instrução clara e para
    if not pwd:
        st.markdown("""
        <div style='max-width:520px;margin:80px auto;background:#161b22;
                    border:1px solid #e85454;border-radius:12px;padding:28px 32px;'>
          <div style='font-size:1rem;font-weight:700;color:#e85454;margin-bottom:12px;'>
            ⚠️ Senha não configurada</div>
          <div style='font-size:.85rem;color:#c9d1d9;line-height:1.7;'>
            Adicione a senha no painel de Secrets do Streamlit Cloud:<br><br>
            <code style='background:#0d1117;padding:10px 14px;border-radius:6px;
                         display:block;font-size:.82rem;color:#1da462;'>
              senha_app = "sua_senha_aqui"
            </code><br>
            <b>Como acessar:</b> App → ⋮ (menu) → Settings → Secrets
          </div>
        </div>""", unsafe_allow_html=True)
        st.stop()

    if st.session_state.get("_ok"): return

    _,col,_=st.columns([1,1.1,1])
    with col:
        st.markdown("<br><br>",unsafe_allow_html=True)
        st.markdown("""<div style='text-align:center;margin-bottom:20px'>
        <div style='font-size:2rem'>🏢</div>
        <div style='font-size:1.1rem;font-weight:700;color:#e6edf3;margin-top:8px'>
            Facilities Intelligence</div>
        <div style='font-size:.8rem;color:#7d8590;margin-top:4px'>
            Cobli · Análise de Gastos com IA</div></div>""",unsafe_allow_html=True)
        s=st.text_input("Senha",type="password",placeholder="Digite a senha")
        if st.button("Entrar",use_container_width=True):
            ok=False
            # Suporte a hash bcrypt ($2b$...) e texto plano
            if pwd.startswith("$2"):
                try:
                    import bcrypt
                    ok=bcrypt.checkpw(s.encode("utf-8"),pwd.encode("utf-8"))
                except: pass
            if not ok: ok=(s==pwd)
            if ok: st.session_state["_ok"]=True; st.rerun()
            else: st.error("Senha incorreta.")
    st.stop()

# ─── GSPREAD ─────────────────────────────────────────────────────────────────
@st.cache_resource(ttl=3600)
def get_client():
    scope=["https://spreadsheets.google.com/feeds",
           "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/drive"]
    creds=ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]),scope)
    return gspread.authorize(creds)

# ─── ETL ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60,show_spinner=False)
def load_query_geral(_cli,url):
    ws=_cli.open_by_url(url).worksheet("Query Geral")
    data=ws.get_all_values()
    if len(data)<2: return pd.DataFrame()
    records=[]
    for r in data[1:]:
        def g(i): return r[i].strip() if i<len(r) else ""
        if g(14).lower()!="facilities": continue
        records.append({
            "_mes": g(0), "Conta": g(13),
            "CentroCusto": g(15) or "(sem centro)",
            "Fornecedor": g(5),
            "_val": g(3),
        })
    if not records: return pd.DataFrame(columns=["Mes","Ano","Conta","CentroCusto","Fornecedor","Valor"])
    df=pd.DataFrame(records)
    df["_dt"]=pd.to_datetime(df["_mes"],errors="coerce")
    df["Mes"]=df["_dt"].apply(fmt_mes)
    df["Ano"]=df["_dt"].dt.year.astype("Int64").astype(str)
    df["Valor"]=df["_val"].apply(parse_num)
    df["Conta"]=df["Conta"].astype(str).str.strip()
    df["CentroCusto"]=df["CentroCusto"].astype(str).str.strip()
    df.loc[df["CentroCusto"]=="","CentroCusto"]="(sem centro)"
    return df[["Mes","Ano","Conta","CentroCusto","Fornecedor","Valor"]].dropna(subset=["Mes"])

@st.cache_data(ttl=60,show_spinner=False)
def load_budget(_cli,url):
    ws=_cli.open_by_url(url).worksheet("Budget")
    data=ws.get_all_values()
    if len(data)<2: return pd.DataFrame()
    hdr=[str(v).strip().upper() for v in data[0]]
    def idx(names,fb):
        for n in names:
            try: return hdr.index(n)
            except: pass
        return fb
    im=idx(["MÊS","MES","DATA"],0); ic=idx(["TIPO 1"],2)
    ib=idx(["BUDGET"],3); ir=idx(["REALIZADO"],4)
    id_=idx(["DELTA"],5); it=idx(["TIPO"],6)
    records=[]
    for r in data[1:]:
        def g(i): return r[i].strip() if i<len(r) else ""
        if not g(im) and not g(ib): continue
        records.append({
            "_mes":g(im),"Conta":g(ic),"Tipo":g(it),
            "_b":g(ib),"_r":g(ir),"_d":g(id_),
        })
    if not records: return pd.DataFrame(columns=["Mes","Ano","Conta","Tipo","Budget","Realizado","Delta"])
    df=pd.DataFrame(records)
    df["_dt"]=pd.to_datetime(df["_mes"],errors="coerce")
    df["Mes"]=df["_dt"].apply(fmt_mes)
    df["Ano"]=df["_dt"].dt.year.astype("Int64").astype(str)
    df["Conta"]=df["Conta"].astype(str).str.strip()
    df["Tipo"]=df["Tipo"].astype(str).str.strip()
    df["Budget"]=df["_b"].apply(parse_num)
    df["Realizado"]=df["_r"].apply(parse_num)
    df["Delta"]=df["_d"].apply(parse_num)
    return df[["Mes","Ano","Conta","Tipo","Budget","Realizado","Delta"]].dropna(subset=["Mes"])

@st.cache_data(ttl=60,show_spinner=False)
def load_mrr(_cli,url):
    try:
        ws=_cli.open_by_url(url).worksheet("MRR")
        data=ws.get_all_values()
        if len(data)<2: return pd.DataFrame()
        hdr=[str(v).strip().upper() for v in data[0]]
        def idx(names,fb):
            for n in names:
                try: return hdr.index(n)
                except: pass
            return fb
        im=idx(["DATA","DATE","MÊS","MES"],1)
        ir=idx(["R$ MRR","MRR"],0)
        ih=idx(["HC"],2)
        records=[]
        for r in data[1:]:
            def g(i): return r[i].strip() if i<len(r) else ""
            records.append({"_dt":g(im),"MRR":parse_num(g(ir)),"HC":parse_num(g(ih))})
        df=pd.DataFrame(records)
        df["Mes"]=pd.to_datetime(df["_dt"],errors="coerce").apply(fmt_mes)
        return df[["Mes","MRR","HC"]].dropna(subset=["Mes"])
    except Exception as e:
        logging.warning(f"MRR: {e}"); return pd.DataFrame()

# ─── MOTOR DE IA ──────────────────────────────────────────────────────────────
def construir_contexto(df_bud, df_qg, df_mrr, filtros):
    """Monta um JSON enxuto com os dados mais relevantes para a IA analisar."""
    fb = df_bud.copy()
    fq = df_qg.copy()
    ano, mes, tipo = filtros.get("ano"), filtros.get("mes"), filtros.get("tipo")
    if ano and ano != "Todos":
        fb = fb[fb["Ano"] == ano]; fq = fq[fq["Ano"] == ano]
    if mes and mes != "Todos":
        fb = fb[fb["Mes"] == mes]; fq = fq[fq["Mes"] == mes]
    if tipo and tipo != "Todos":
        fb = fb[fb["Tipo"] == tipo]

    # Resumo mensal
    mes_agg = (fb.groupby("Mes", as_index=False)
                 .agg(Budget=("Budget","sum"), Realizado=("Realizado","sum"), Delta=("Delta","sum"))
                 .sort_values("Mes", key=lambda s: s.map(mes_ord)))

    # Contas com maior desvio (estouros)
    conta_agg = (fb.groupby("Conta", as_index=False)
                   .agg(Budget=("Budget","sum"), Realizado=("Realizado","sum"), Delta=("Delta","sum")))
    conta_agg["PctExec"] = np.where(
        conta_agg["Budget"] > 0,
        conta_agg["Realizado"] / conta_agg["Budget"] * 100, 0)
    estouros = conta_agg[conta_agg["PctExec"] > 100].sort_values("PctExec", ascending=False)

    # Top fornecedores por gasto
    top_forn = (fq.groupby("Fornecedor")["Valor"].sum()
                  .sort_values(ascending=False).head(10).reset_index())

    # Centros de custo
    cc_agg = (fq.groupby("CentroCusto")["Valor"].sum()
                .sort_values(ascending=False).head(10).reset_index())

    # MRR
    mrr_last = df_mrr.sort_values("Mes", key=lambda s: s.map(mes_ord)).tail(3).to_dict("records") if not df_mrr.empty else []

    ctx = {
        "periodo_analisado": f"Ano={ano}, Mês={mes}, Tipo={tipo}",
        "resumo_mensal": mes_agg.round(2).to_dict("records"),
        "total_budget": float(fb["Budget"].sum()),
        "total_realizado": float(fb["Realizado"].sum()),
        "total_delta": float(fb["Delta"].sum()),
        "contas_estouradas": estouros[["Conta","Budget","Realizado","PctExec","Delta"]].round(2).to_dict("records"),
        "top_10_fornecedores": top_forn.rename(columns={"Valor":"Total_Realizado"}).round(2).to_dict("records"),
        "centros_custo": cc_agg.rename(columns={"Valor":"Realizado"}).round(2).to_dict("records"),
        "mrr_recente": mrr_last,
        "total_lancamentos_qg": len(fq),
    }
    return ctx

def chamar_ia(contexto: dict, pergunta: str, historico: list) -> str:
    """Chama Claude para analisar os dados de Facilities."""
    api_key = st.secrets.get("anthropic_api_key", "")
    if not api_key:
        return "⚠️ Configure `anthropic_api_key` no secrets.toml para usar a análise IA."

    system = """Você é um analista financeiro sênior especializado em gestão de custos de Facilities.
Seu objetivo é identificar oportunidades de redução de gastos, tendências preocupantes e gerar
insights acionáveis para o CFO e gestor de Facilities da Cobli.

Você recebe dados reais da empresa em JSON e deve:
1. Identificar anomalias e contas com maior desvio do budget
2. Apontar fornecedores com gastos elevados ou concentração de risco
3. Calcular tendências e projeções quando possível
4. Propor ações concretas e priorizadas de redução de custos
5. Usar linguagem executiva, direta e objetiva
6. Formatar valores sempre em R$ com separadores brasileiros
7. Responder em português do Brasil

Dados contextuais da empresa:
""" + json.dumps(contexto, ensure_ascii=False, default=str)

    msgs = []
    for h in historico:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": pergunta})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system,
            messages=msgs,
        )
        return resp.content[0].text
    except Exception as e:
        return f"⚠️ Erro na IA: {e}"

# ─── GRÁFICOS ─────────────────────────────────────────────────────────────────
def fig_bvr(df, modo="Barras"):
    fig = go.Figure()
    if modo == "Barras":
        fig.add_bar(name="Budget", x=df["Mes"], y=df["Budget"],
                    marker_color=C_BUD, marker_line_width=0,
                    hovertemplate="%{x}<br>Budget: R$ %{y:,.0f}<extra></extra>")
        fig.add_bar(name="Realizado", x=df["Mes"], y=df["Realizado"],
                    marker_color=C_REAL, marker_line_width=0,
                    hovertemplate="%{x}<br>Realizado: R$ %{y:,.0f}<extra></extra>")
        fig.update_layout(**PLOTLY_BASE, barmode="group",
                          title=title_l("Budget × Realizado por Mês"))
    else:
        fig.add_scatter(name="Budget", x=df["Mes"], y=df["Budget"],
                        mode="lines+markers", line=dict(color=C_BUD, width=2), marker=dict(size=5))
        fig.add_scatter(name="Realizado", x=df["Mes"], y=df["Realizado"],
                        mode="lines+markers", line=dict(color=C_REAL, width=2), marker=dict(size=5))
        fig.update_layout(**PLOTLY_BASE, title=title_l("Evolução Mensal"))
    return fig

def fig_delta(df):
    cores=[C_REAL if v>=0 else C_VERM for v in df["Delta"]]
    fig=go.Figure()
    fig.add_bar(x=df["Mes"],y=df["Delta"],marker_color=cores,marker_line_width=0,
                name="Delta",hovertemplate="%{x}<br>Delta: R$ %{y:,.0f}<extra></extra>")
    fig.add_hline(y=0,line_color="#21283a",line_width=1)
    fig.update_layout(**PLOTLY_BASE,showlegend=False,
                      title=title_l("Delta Mensal (Budget − Realizado)"))
    return fig

def fig_contas(df):
    top=df.nlargest(12,"Realizado")
    fig=go.Figure()
    fig.add_bar(name="Budget",y=top["Conta"],x=top["Budget"],
                orientation="h",marker_color=C_BUD,marker_line_width=0)
    fig.add_bar(name="Realizado",y=top["Conta"],x=top["Realizado"],
                orientation="h",marker_color=C_REAL,marker_line_width=0)
    layout={**PLOTLY_BASE,"barmode":"group","height":360,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":title_l("Top Contas · Budget vs Realizado")}
    fig.update_layout(**layout)
    return fig

def fig_fornecedores(df):
    top=df.groupby("Fornecedor")["Valor"].sum().nlargest(10).reset_index()
    fig=go.Figure()
    fig.add_bar(y=top["Fornecedor"],x=top["Valor"],orientation="h",
                marker_color=C_DELT,marker_line_width=0,
                hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>")
    layout={**PLOTLY_BASE,"height":340,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":title_l("Top 10 Fornecedores por Gasto")}
    fig.update_layout(**layout)
    return fig

def fig_cc_juntos(df_cc):
    fig=go.Figure()
    fig.add_bar(y=df_cc["CentroCusto"],x=df_cc["Realizado"],orientation="h",
                marker_color=C_REAL,marker_line_width=0)
    layout={**PLOTLY_BASE,"height":300,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":title_l("Realizado por Centro de Custo")}
    fig.update_layout(**layout)
    return fig

def fig_cc_empilhado(df_qg, meses):
    centros=sorted(df_qg["CentroCusto"].unique())
    fig=go.Figure()
    for i,cc in enumerate(centros):
        sub=(df_qg[df_qg["CentroCusto"]==cc]
             .groupby("Mes")["Valor"].sum()
             .reindex(meses,fill_value=0))
        fig.add_bar(name=cc,x=meses,y=sub.values,
                    marker_color=PALETTE[i%len(PALETTE)],marker_line_width=0)
    fig.update_layout(**PLOTLY_BASE,barmode="stack",
                      title=title_l("Realizado por Mês — empilhado por Centro"))
    return fig

def fig_cc_separados(df_qg, centros, meses):
    n=len(centros)
    if n==0: return None
    cols=min(3,n); rows=(n+cols-1)//cols
    fig=make_subplots(rows=rows,cols=cols,
                      subplot_titles=[c[:22] for c in centros],
                      vertical_spacing=0.12,horizontal_spacing=0.06)
    for i,cc in enumerate(centros):
        row,col=divmod(i,cols); row+=1; col+=1
        sub=(df_qg[df_qg["CentroCusto"]==cc]
             .groupby("Mes")["Valor"].sum()
             .reindex(meses,fill_value=0))
        fig.add_bar(name=cc,x=meses,y=sub.values,
                    marker_color=PALETTE[i%len(PALETTE)],
                    marker_line_width=0,showlegend=False,
                    row=row,col=col)
        fig.update_xaxes(tickfont=dict(size=8,color="#7d8590"),gridcolor="#21283a",row=row,col=col)
        fig.update_yaxes(tickfont=dict(size=8,color="#7d8590"),gridcolor="#21283a",row=row,col=col)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter,sans-serif",color="#7d8590",size=10),
                      height=max(220*rows,300),margin=dict(t=40,b=8,l=8,r=8),
                      showlegend=False,title=title_l("Realizado por Centro — Separados"))
    for ann in fig.layout.annotations:
        ann.font.color="#e6edf3"; ann.font.size=11
    return fig

def fig_mrr_vs_fac(df_mrr, df_mes):
    m=pd.merge(df_mrr,df_mes[["Mes","Realizado"]],on="Mes",how="inner")
    if m.empty: return None
    fig=make_subplots(specs=[[{"secondary_y":True}]])
    fig.add_bar(name="MRR",x=m["Mes"],y=m["MRR"],
                marker_color="#2490d8",marker_line_width=0,secondary_y=False)
    fig.add_scatter(name="Facilities",x=m["Mes"],y=m["Realizado"],
                    mode="lines+markers",line=dict(color=C_VERM,width=2),
                    marker=dict(size=5),secondary_y=True)
    fig.update_layout(**PLOTLY_BASE,title=title_l("MRR × Custo Facilities"))
    fig.update_yaxes(gridcolor="#21283a",tickfont=dict(size=10,color="#7d8590"),secondary_y=False)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)",tickfont=dict(size=10,color="#7d8590"),secondary_y=True)
    return fig

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    check_auth()

    # Header
    st.markdown("""
    <div style='display:flex;align-items:center;gap:10px;
                padding:14px 0 10px;border-bottom:1px solid #21283a;margin-bottom:16px;'>
      <div>
        <div style='font-size:1.15rem;font-weight:700;color:#e6edf3;'>
          🏢 Facilities Intelligence
          <span class="badge">Cobli</span>
          <span class="badge-ia">✦ IA</span>
        </div>
        <div style='font-size:.78rem;color:#7d8590;margin-top:2px;'>
          Análise inteligente de gastos · Budget × Realizado · Redução de Custos</div>
      </div>
    </div>""",unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### Facilities Intelligence")
        if st.button("🚪 Sair"):
            st.session_state["_ok"]=False; st.rerun()
        st.markdown("---")
        if st.checkbox("🔄 Auto-refresh 60s", value=True):
            st.markdown("<script>setTimeout(()=>location.reload(),60000)</script>",
                        unsafe_allow_html=True)
        st.markdown("---")
        st.caption(f"📊 Planilha conectada")
        st.caption(f"🔗 [Abrir no Sheets]({URL_PLANILHA})")

    # URL fixa — sem input manual
    url = st.secrets.get("url_planilha", URL_PLANILHA)

    with st.spinner("Carregando dados da planilha…"):
        try:
            cli   = get_client()
            df_qg = load_query_geral(cli, url)
            df_bud= load_budget(cli, url)
            df_mrr= load_mrr(cli, url)
        except Exception as e:
            st.error(f"Erro ao conectar: {e}"); st.stop()

    if df_qg.empty and df_bud.empty:
        st.warning("Nenhum dado encontrado na planilha."); return

    # ── FILTROS ──────────────────────────────────────────────────────────────
    st.markdown("---")
    anos_all=sorted(set(df_bud["Ano"].dropna())|set(df_qg["Ano"].dropna()),reverse=True)
    anos_all=[a for a in anos_all if str(a).isdigit()]

    c1,c2,c3,c4,c5=st.columns([.8,1,1.2,1.3,.9])
    with c1:
        ano=st.selectbox("Ano",["Todos"]+anos_all,
                         index=1 if "2026" in anos_all else 0)
    with c2:
        db_a=df_bud[df_bud["Ano"]==ano] if ano!="Todos" else df_bud
        dq_a=df_qg[df_qg["Ano"]==ano]   if ano!="Todos" else df_qg
        meses=sorted(set(db_a["Mes"].dropna())|set(dq_a["Mes"].dropna()),key=mes_ord)
        mes=st.selectbox("Mês",["Todos"]+meses)
    with c3:
        tipos=sorted(db_a["Tipo"].dropna().unique()) if not db_a.empty else []
        tipo=st.selectbox("Tipo",["Todos"]+tipos)
    with c4:
        ccs=sorted(dq_a["CentroCusto"].dropna().unique()) if not dq_a.empty else []
        cc_sel=st.selectbox("Centro de Custo",["Todos"]+ccs)
    with c5:
        if st.button("↺ Atualizar",use_container_width=True):
            st.cache_data.clear(); st.rerun()

    # Aplicar filtros
    fb=df_bud.copy(); fq=df_qg.copy()
    if ano!="Todos":    fb=fb[fb["Ano"]==ano];         fq=fq[fq["Ano"]==ano]
    if mes!="Todos":    fb=fb[fb["Mes"]==mes];         fq=fq[fq["Mes"]==mes]
    if tipo!="Todos":   fb=fb[fb["Tipo"]==tipo]
    if cc_sel!="Todos": fq=fq[fq["CentroCusto"]==cc_sel]

    filtros={"ano":ano,"mes":mes,"tipo":tipo,"cc":cc_sel}

    if fb.empty and fq.empty:
        st.info("Nenhum dado para os filtros."); return

    # Agregações
    df_mes=(fb.groupby("Mes",as_index=False)
              .agg(Budget=("Budget","sum"),Realizado=("Realizado","sum"),Delta=("Delta","sum"))
              .sort_values("Mes",key=lambda s:s.map(mes_ord)))
    meses_ord_l=df_mes["Mes"].tolist()
    df_contas=(fb.groupby("Conta",as_index=False)
                 .agg(Budget=("Budget","sum"),Realizado=("Realizado","sum"),Delta=("Delta","sum")))
    df_cc=(fq.groupby("CentroCusto",as_index=False)
             .agg(Realizado=("Valor","sum"))
             .sort_values("Realizado",ascending=False))
    meses_qg=sorted(fq["Mes"].dropna().unique(),key=mes_ord)

    tot_b=df_mes["Budget"].sum()
    tot_r=df_mes["Realizado"].sum()
    tot_d=df_mes["Delta"].sum()
    pct=tot_r/tot_b*100 if tot_b>0 else 0

    # ── ABAS ─────────────────────────────────────────────────────────────────
    tab1,tab2,tab3,tab4,tab5,tab6=st.tabs([
        "📊 Visão Geral",
        "📋 Por Conta",
        "🏢 Centro de Custo",
        "🏭 Fornecedores",
        "📈 MRR vs Custo",
        "✦ Análise IA",
    ])

    # ══ ABA 1 — VISÃO GERAL ══════════════════════════════════════════════════
    with tab1:
        k1,k2,k3,k4=st.columns(4)
        with k1: kpi("Total Budget",brl(tot_b),f"{len(df_mes)} meses")
        with k2:
            cor="red" if tot_r>tot_b else "green"
            kpi("Realizado",brl(tot_r),f"{pct:.1f}% executado",cor)
        with k3:
            cor="green" if tot_d>=0 else "red"
            kpi("Delta (Economia)",("+") if tot_d>=0 else ""+brl(tot_d),
                "Abaixo do budget ✓" if tot_d>=0 else "Acima do budget ⚠️",cor)
        with k4:
            tot_qg=fq["Valor"].sum()
            kpi("Realizado (Query Geral)",brl(tot_qg),f"{len(fq):,} lançamentos","blue")
        st.markdown("---")
        modo=st.radio("Gráfico",["Barras","Linha"],horizontal=True,key="g1")
        if not df_mes.empty:
            st.plotly_chart(fig_bvr(df_mes,modo),use_container_width=True)
            st.plotly_chart(fig_delta(df_mes),use_container_width=True)

    # ══ ABA 2 — POR CONTA ════════════════════════════════════════════════════
    with tab2:
        if not df_contas.empty:
            st.plotly_chart(fig_contas(df_contas),use_container_width=True)
            st.markdown("---")
            df_contas["%Exec"]=np.where(df_contas["Budget"]>0,
                                        df_contas["Realizado"]/df_contas["Budget"]*100,0)
            df_contas["Status"]=np.select(
                [df_contas["Realizado"]>df_contas["Budget"],
                 df_contas["Realizado"]>=df_contas["Budget"]*0.85],
                ["🔴 Estourou","🟡 Alerta"],default="🟢 OK")
            st.dataframe(
                df_contas[["Status","Conta","Budget","Realizado","Delta","%Exec"]]
                  .sort_values("Realizado",ascending=False).reset_index(drop=True),
                hide_index=True,use_container_width=True,
                column_config={
                    "Status":   st.column_config.TextColumn("Alerta",width="small"),
                    "Conta":    st.column_config.TextColumn("Conta"),
                    "Budget":   st.column_config.NumberColumn("Budget",   format="R$ %.2f"),
                    "Realizado":st.column_config.NumberColumn("Realizado",format="R$ %.2f"),
                    "Delta":    st.column_config.NumberColumn("Delta",    format="R$ %.2f"),
                    "%Exec":    st.column_config.ProgressColumn("Execução",format="%.1f%%",
                                                                min_value=0,max_value=100),
                })

    # ══ ABA 3 — CENTRO DE CUSTO ══════════════════════════════════════════════
    with tab3:
        if fq.empty:
            st.info("Sem lançamentos Facilities para os filtros selecionados.")
        else:
            k1,k2,k3,k4=st.columns(4)
            with k1: kpi("Centros Ativos",str(len(df_cc)),"col P")
            with k2: kpi("Realizado Total",brl(df_cc["Realizado"].sum()))
            if not df_cc.empty:
                with k3: kpi("Maior Centro",df_cc.iloc[0]["CentroCusto"][:22],
                             brl(df_cc.iloc[0]["Realizado"]))
                with k4: kpi("Menor Centro",df_cc.iloc[-1]["CentroCusto"][:22],
                             brl(df_cc.iloc[-1]["Realizado"]))
            st.markdown("---")
            modo_cc=st.radio("Visualização",["Juntos","Separados"],horizontal=True,key="gcc")
            centros_l=df_cc["CentroCusto"].tolist()
            if modo_cc=="Juntos":
                col1,col2=st.columns(2)
                with col1: st.plotly_chart(fig_cc_juntos(df_cc),use_container_width=True)
                with col2:
                    if meses_qg:
                        st.plotly_chart(fig_cc_empilhado(fq,meses_qg),use_container_width=True)
            else:
                fig_s=fig_cc_separados(fq,centros_l,meses_qg)
                if fig_s: st.plotly_chart(fig_s,use_container_width=True)
            st.markdown("---")
            df_cc["%Total"]=np.where(df_cc["Realizado"].sum()>0,
                                     df_cc["Realizado"]/df_cc["Realizado"].sum()*100,0)
            st.dataframe(df_cc.reset_index(drop=True),hide_index=True,
                         use_container_width=True,
                         column_config={
                             "CentroCusto": st.column_config.TextColumn("Centro de Custo"),
                             "Realizado":   st.column_config.NumberColumn("Realizado",format="R$ %.2f"),
                             "%Total":      st.column_config.ProgressColumn("% do Total",
                                            format="%.1f%%",min_value=0,max_value=100),
                         })

    # ══ ABA 4 — FORNECEDORES ═════════════════════════════════════════════════
    with tab4:
        if fq.empty:
            st.info("Sem dados de fornecedores.")
        else:
            top10=fq.groupby("Fornecedor")["Valor"].sum().nlargest(10).reset_index()
            k1,k2,k3=st.columns(3)
            with k1: kpi("Fornecedores únicos",str(fq["Fornecedor"].nunique()))
            with k2: kpi("Top 1",top10.iloc[0]["Fornecedor"][:28] if not top10.empty else "—",
                         brl(top10.iloc[0]["Valor"]) if not top10.empty else "")
            with k3:
                conc=top10["Valor"].sum()/fq["Valor"].sum()*100 if fq["Valor"].sum()>0 else 0
                kpi("Concentração Top 10",f"{conc:.1f}%","do total realizado",
                    "red" if conc>70 else "yellow" if conc>50 else "green")
            st.markdown("---")
            st.plotly_chart(fig_fornecedores(fq),use_container_width=True)
            st.markdown("---")
            st.markdown("##### Detalhamento por Fornecedor")
            forn_tab=(fq.groupby("Fornecedor",as_index=False)
                        .agg(Realizado=("Valor","sum"),Lançamentos=("Valor","count"))
                        .sort_values("Realizado",ascending=False).reset_index(drop=True))
            forn_tab["%Total"]=np.where(forn_tab["Realizado"].sum()>0,
                                         forn_tab["Realizado"]/forn_tab["Realizado"].sum()*100,0)
            st.dataframe(forn_tab,hide_index=True,use_container_width=True,
                         column_config={
                             "Fornecedor":   st.column_config.TextColumn("Fornecedor"),
                             "Realizado":    st.column_config.NumberColumn("Total",format="R$ %.2f"),
                             "Lançamentos":  st.column_config.NumberColumn("NFs",format="%d"),
                             "%Total":       st.column_config.ProgressColumn("% do Total",
                                             format="%.1f%%",min_value=0,max_value=100),
                         })

    # ══ ABA 5 — MRR VS CUSTO ═════════════════════════════════════════════════
    with tab5:
        if df_mrr.empty:
            st.info("Aba MRR não encontrada ou sem dados.")
        else:
            df_mrr_f=df_mrr.copy()
            if ano!="Todos":
                df_mrr_f=df_mrr_f[df_mrr_f["Mes"].str.endswith(ano[2:])]
            merged=pd.merge(df_mrr_f,df_mes[["Mes","Realizado"]],on="Mes",how="inner")
            if merged.empty:
                st.info("Sem sobreposição de meses.")
            else:
                merged["%Fac/MRR"]=np.where(merged["MRR"]>0,
                                             merged["Realizado"]/merged["MRR"]*100,0)
                k1,k2,k3=st.columns(3)
                with k1: kpi("MRR Médio",brl(merged["MRR"].mean()))
                with k2: kpi("% Médio Facilities/MRR",f"{merged['%Fac/MRR'].mean():.2f}%")
                with k3: kpi("HC Médio",str(int(df_mrr_f["HC"].mean())))
                st.markdown("---")
                fig_m=fig_mrr_vs_fac(df_mrr_f,df_mes)
                if fig_m: st.plotly_chart(fig_m,use_container_width=True)
                st.dataframe(
                    merged[["Mes","MRR","Realizado","%Fac/MRR"]]
                      .sort_values("Mes",key=lambda s:s.map(mes_ord)).reset_index(drop=True),
                    hide_index=True,use_container_width=True,
                    column_config={
                        "Mes":       st.column_config.TextColumn("Mês"),
                        "MRR":       st.column_config.NumberColumn("MRR",       format="R$ %.2f"),
                        "Realizado": st.column_config.NumberColumn("Facilities", format="R$ %.2f"),
                        "%Fac/MRR":  st.column_config.ProgressColumn("% Custo/MRR",
                                     format="%.2f%%",min_value=0,max_value=10),
                    })

    # ══ ABA 6 — ANÁLISE IA ═══════════════════════════════════════════════════
    with tab6:
        st.markdown("""
        <div style='margin-bottom:16px;'>
          <div style='font-size:.9rem;font-weight:600;color:#e6edf3;margin-bottom:4px;'>
            ✦ Análise Inteligente de Gastos</div>
          <div style='font-size:.78rem;color:#7d8590;'>
            O assistente analisa os dados do período filtrado e identifica oportunidades de
            redução de custos, anomalias e tendências. Faça perguntas específicas ou use
            as análises pré-configuradas abaixo.</div>
        </div>""",unsafe_allow_html=True)

        # Análises pré-configuradas
        st.markdown("##### Análises Rápidas")
        sugestoes = [
            "🔍 Identifique as principais oportunidades de redução de gastos",
            "⚠️ Quais contas estão estourando o budget e por quê?",
            "🏭 Analise a concentração de fornecedores e riscos de dependência",
            "📈 Identifique tendências e projete os próximos 3 meses",
            "💡 Sugira 5 ações concretas e priorizadas para reduzir custos este semestre",
            "🏢 Qual centro de custo tem maior potencial de otimização?",
        ]
        cols_s = st.columns(3)
        for i, s in enumerate(sugestoes):
            with cols_s[i % 3]:
                if st.button(s, use_container_width=True, key=f"sug_{i}"):
                    st.session_state["ia_pergunta"] = s.split(" ", 1)[1]

        st.markdown("---")

        # Histórico de conversa
        if "ia_historico" not in st.session_state:
            st.session_state["ia_historico"] = []
        if "ia_pergunta" not in st.session_state:
            st.session_state["ia_pergunta"] = ""

        # Exibir histórico
        for msg in st.session_state["ia_historico"]:
            if msg["role"] == "user":
                st.markdown(f"""
                <div style='background:#21283a;border-radius:8px;padding:10px 14px;
                            margin-bottom:8px;font-size:.83rem;color:#c9d1d9;'>
                  👤 {msg["content"]}</div>""",unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="ia-box">
                  <div class="ia-header">✦ Análise IA · Facilities Intelligence</div>
                  <div class="ia-content">{msg["content"]}</div>
                </div>""",unsafe_allow_html=True)

        # Input
        st.markdown("##### Pergunte ao assistente")
        pergunta = st.text_area(
            "Pergunta",
            value=st.session_state.get("ia_pergunta", ""),
            placeholder="Ex: Quais fornecedores têm maior potencial de negociação? "
                        "Ou: Qual conta tem o maior desvio do budget?",
            height=90, label_visibility="collapsed", key="ia_input"
        )

        col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1, 1])
        with col_btn1:
            analisar = st.button("✦ Analisar com IA", use_container_width=True, type="primary")
        with col_btn2:
            if st.button("🗑️ Limpar conversa", use_container_width=True):
                st.session_state["ia_historico"] = []
                st.session_state["ia_pergunta"] = ""
                st.rerun()
        with col_btn3:
            auto_analise = st.button("⚡ Análise completa", use_container_width=True)

        if auto_analise:
            pergunta = ("Faça uma análise executiva completa dos gastos de Facilities: "
                        "principais desvios de budget, fornecedores críticos, tendências e "
                        "5 ações prioritárias de redução de custos para este semestre.")

        if (analisar or auto_analise) and pergunta.strip():
            ctx = construir_contexto(df_bud, df_qg, df_mrr, filtros)
            with st.spinner("✦ Analisando dados…"):
                resposta = chamar_ia(ctx, pergunta.strip(), st.session_state["ia_historico"])
            st.session_state["ia_historico"].append({"role":"user","content":pergunta.strip()})
            st.session_state["ia_historico"].append({"role":"assistant","content":resposta})
            st.session_state["ia_pergunta"] = ""
            st.rerun()

        if not st.session_state["ia_historico"]:
            st.markdown("""
            <div style='text-align:center;padding:40px;color:#7d8590;font-size:.82rem;'>
              ✦ Selecione uma análise rápida ou faça uma pergunta para começar.<br>
              <span style='font-size:.75rem;opacity:.7;'>
                O assistente usa os dados do período filtrado para gerar insights acionáveis.
              </span>
            </div>""",unsafe_allow_html=True)

if __name__ == "__main__":
    main()
