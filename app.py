# app_facilities_ia.py — Dashboard NFs Cobli + Análise IA
# Planilha: abas "Lancamentos" + "Budget"
# Lancamentos: col12=Total linha, col16=CC, col34=Nome conta, col8=Fornecedor, col6=Data NF
# Budget: col1=Mês, col3=TIPO 1 (conta), col4=BUDGET

import streamlit as st
import pandas as pd
import numpy as np
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai
import logging

logging.basicConfig(level=logging.INFO)

# ─── URL FIXA ────────────────────────────────────────────────────────────────
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1sfVgLYOjM5pJDGl9ML6FN22g1sKaj7Om1x4g1O9ITPI/edit"

# ─── CONFIG ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Facilities Intelligence · Cobli",
                   page_icon="🏢", layout="wide",
                   initial_sidebar_state="collapsed")

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
[data-testid="stDataFrame"]{border:1px solid #21283a;border-radius:10px;overflow:hidden;}
[data-testid="stDataFrame"] th{background:#161b22!important;color:#7d8590!important;
  font-size:.72rem!important;text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid #21283a!important;}
[data-testid="stDataFrame"] td{color:#e6edf3!important;font-size:.8rem!important;
  border-color:#21283a!important;}
[data-testid="stExpander"]{background:#161b22!important;border:1px solid #21283a!important;
  border-radius:10px!important;}
hr{border-color:#21283a!important;}
.stTextArea textarea{background:#161b22!important;border:1px solid #21283a!important;
  color:#e6edf3!important;font-size:.83rem!important;border-radius:8px!important;}
.kpi-card{background:#161b22;border:1px solid #21283a;border-radius:10px;
  padding:16px 20px;margin-bottom:4px;}
.kpi-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;
  color:#7d8590;margin-bottom:4px;}
.kpi-val{font-size:1.4rem;font-weight:700;color:#e6edf3;line-height:1.2;}
.kpi-sub{font-size:.72rem;color:#7d8590;margin-top:3px;}
.green{color:#1da462!important;}.red{color:#e85454!important;}
.yellow{color:#d4a017!important;}.blue{color:#2490d8!important;}
.ia-box{background:linear-gradient(135deg,rgba(36,144,216,.08),rgba(29,164,98,.05));
  border:1px solid rgba(36,144,216,.25);border-radius:12px;padding:20px 24px;margin-top:8px;}
.ia-header{font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;
  color:#2490d8;font-weight:600;margin-bottom:10px;}
.ia-content{font-size:.84rem;line-height:1.65;color:#c9d1d9;white-space:pre-wrap;}
.badge{background:rgba(29,111,164,.15);color:#2490d8;border:1px solid rgba(36,144,216,.3);
  border-radius:20px;font-size:.7rem;font-weight:600;padding:2px 10px;margin-left:8px;}
.badge-ia{background:rgba(29,164,98,.12);color:#1da462;border:1px solid rgba(29,164,98,.3);
  border-radius:20px;font-size:.7rem;font-weight:600;padding:2px 10px;margin-left:6px;}
</style>""", unsafe_allow_html=True)

# ─── CONSTANTES ──────────────────────────────────────────────────────────────
PT=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
C_BUD="#1d6fa4"; C_REAL="#1da462"; C_VERM="#e85454"; C_DELT="#d4a017"
PALETTE=["#2490d8","#1da462","#d4a017","#e85454","#a064c8",
         "#50c8c8","#e6823c","#78a05a","#c878a0","#6488dc",
         "#b4b45a","#8c8c8c"]
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
    try: v=float(v); return f"R$ {abs(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "R$ 0,00"

def parse_num(s):
    if isinstance(s,(int,float)): return float(s)
    s=str(s).replace("R$","").strip().replace(".","").replace(",",".")
    try: return float(s)
    except: return 0.0

def kpi(label,val,sub="",color=""):
    c=f' class="{color}"' if color else ""
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-val"{c}>{val}</div>
      <div class="kpi-sub">{sub}</div></div>""",unsafe_allow_html=True)

def tl(txt):
    return dict(text=txt,font=dict(size=13,color="#e6edf3"),x=0,xanchor="left")

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def check_auth():
    pwd=""
    for key in ["senha_app","senha_app_hash","SENHA_APP","password"]:
        try:
            val=st.secrets[key]
            if val: pwd=str(val).strip(); break
        except: continue

    if not pwd:
        st.markdown("""
        <div style='max-width:520px;margin:80px auto;background:#161b22;
                    border:1px solid #e85454;border-radius:12px;padding:28px 32px;'>
          <div style='font-size:1rem;font-weight:700;color:#e85454;margin-bottom:12px;'>
            ⚠️ Senha não configurada</div>
          <div style='font-size:.85rem;color:#c9d1d9;line-height:1.7;'>
            No Streamlit Cloud: App → ⋮ → Settings → Secrets<br><br>
            <code style='background:#0d1117;padding:10px 14px;border-radius:6px;
                         display:block;font-size:.82rem;color:#1da462;'>
              senha_app = "sua_senha_aqui"</code>
          </div></div>""",unsafe_allow_html=True)
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
            if pwd.startswith("$2"):
                try:
                    import bcrypt; ok=bcrypt.checkpw(s.encode("utf-8"),pwd.encode("utf-8"))
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
def load_lancamentos(_cli, url):
    """
    Aba Lancamentos — colunas confirmadas pelo XLSX:
      col 6  = Data NF
      col 8  = Nome fornecedor
      col 12 = Total da linha (valor)
      col 16 = Centro de Custos
      col 27 = CNPJ ou CPF
      col 33 = Conta SAP (código)
      col 34 = Nome da conta
    """
    ws   = _cli.open_by_url(url).worksheet("Lancamentos")
    data = ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()

    records = []
    for r in data[1:]:
        def g(i): return r[i].strip() if i < len(r) else ""
        val = parse_num(g(11))   # col 12 (idx 11)
        if val == 0: continue
        records.append({
            "_data":    g(5),    # col 6  — Data NF
            "Fornecedor": g(7),  # col 8
            "Valor":    val,
            "CC":       g(15),   # col 16 — Centro de Custos
            "ContaSAP": g(32),   # col 33 — código SAP
            "Conta":    g(33),   # col 34 — nome da conta
            "CNPJ":     g(26),   # col 27
            "Descricao":g(10),   # col 11 — Descrição do item
            "NF":       g(1),    # col 2  — Nº NF
        })

    if not records:
        return pd.DataFrame(columns=["Mes","Ano","Fornecedor","Valor","CC","ContaSAP","Conta"])

    df = pd.DataFrame(records)
    df["_dt"]  = pd.to_datetime(df["_data"], dayfirst=True, errors="coerce")
    df["Mes"]  = df["_dt"].apply(fmt_mes)
    df["Ano"]  = df["_dt"].dt.year.astype("Int64").astype(str)
    df["Valor"]= df["Valor"].astype(float)
    return df[["Mes","Ano","Fornecedor","Valor","CC","ContaSAP","Conta","CNPJ","Descricao","NF"]].dropna(subset=["Mes"])


@st.cache_data(ttl=60,show_spinner=False)
def load_budget(_cli, url):
    """
    Aba Budget — colunas:
      col 1 = MÊS
      col 2 = CONTA (código SAP)
      col 3 = TIPO 1 (nome da conta)
      col 4 = BUDGET
    """
    ws   = _cli.open_by_url(url).worksheet("Budget")
    data = ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()

    records = []
    for r in data[1:]:
        def g(i): return r[i].strip() if i < len(r) else ""
        bud = parse_num(g(3))   # col 4
        if not g(0): continue
        records.append({
            "_mes":  g(0),
            "ContaSAP": g(1),   # col 2 — código
            "Conta": g(2),      # col 3 — nome
            "Budget": bud,
        })

    if not records:
        return pd.DataFrame(columns=["Mes","Ano","ContaSAP","Conta","Budget"])

    df = pd.DataFrame(records)
    df["_dt"] = pd.to_datetime(df["_mes"], dayfirst=True, errors="coerce")
    df["Mes"] = df["_dt"].apply(fmt_mes)
    df["Ano"] = df["_dt"].dt.year.astype("Int64").astype(str)
    df["Budget"] = df["Budget"].astype(float)
    return df[["Mes","Ano","ContaSAP","Conta","Budget"]].dropna(subset=["Mes"])

# ─── MOTOR DE IA ──────────────────────────────────────────────────────────────
def construir_contexto(df_l, df_b, df_bi, filtros):
    top_forn = (df_l.groupby("Fornecedor")["Valor"].sum()
                  .nlargest(10).reset_index()
                  .rename(columns={"Valor":"Total"})
                  .round(2).to_dict("records"))
    top_cc   = (df_l.groupby("CC")["Valor"].sum()
                  .nlargest(10).reset_index()
                  .rename(columns={"Valor":"Total"})
                  .round(2).to_dict("records"))
    estouros = df_bi[df_bi["PctExec"]>100].sort_values("PctExec",ascending=False)

    ctx = {
        "periodo": filtros,
        "total_lancamentos": len(df_l),
        "total_realizado": float(df_l["Valor"].sum()),
        "total_budget": float(df_b["Budget"].sum()),
        "saldo_budget": float(df_b["Budget"].sum() - df_l["Valor"].sum()),
        "resumo_mensal": (
            df_l.groupby("Mes")["Valor"].sum()
                .reset_index().sort_values("Mes",key=lambda s:s.map(mes_ord))
                .round(2).to_dict("records")
        ),
        "contas_estouradas": estouros[["Conta","Budget","Realizado","PctExec"]].round(2).to_dict("records"),
        "top_10_fornecedores": top_forn,
        "centros_custo": top_cc,
        "fornecedores_unicos": int(df_l["Fornecedor"].nunique()),
        "contas_unicas": int(df_l["Conta"].nunique()),
    }
    return ctx

def chamar_ia(ctx, pergunta, historico):
    # Busca chave Gemini no secrets (nunca no código)
    api_key = ""
    for k in ["gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY"]:
        try:
            v = st.secrets[k]
            if v: api_key = str(v).strip(); break
        except: continue

    if not api_key:
        return (
            "⚠️ Configure a chave Gemini no secrets do Streamlit Cloud:\n\n"
            "App → ⋮ (menu) → Settings → Secrets\n\n"
            "```toml\n"
            "gemini_api_key = \"AIza...\"\n"
            "```\n\n"
            "Obtenha sua chave gratuita em: https://aistudio.google.com/apikey"
        )

    system_prompt = (
        "Você é um analista financeiro sênior especializado em gestão de custos de Facilities da Cobli. "
        "Seu objetivo é identificar oportunidades de redução de gastos, anomalias e gerar insights "
        "acionáveis para o CFO.\n\n"
        "Regras:\n"
        "1. Identifique contas e fornecedores com maior desvio ou concentração de risco\n"
        "2. Proponha ações concretas e priorizadas por impacto financeiro\n"
        "3. Use linguagem executiva, direta e objetiva\n"
        "4. Formate valores em R$ com separadores brasileiros\n"
        "5. Responda sempre em português do Brasil\n\n"
        "Dados do período analisado:\n"
        + json.dumps(ctx, ensure_ascii=False, default=str)
    )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=system_prompt,
        )
        # Monta histórico no formato Gemini
        history = []
        for h in historico:
            role = "user" if h["role"] == "user" else "model"
            history.append({"role": role, "parts": [h["content"]]})

        chat = model.start_chat(history=history)
        resp = chat.send_message(pergunta)
        return resp.text
    except Exception as e:
        return f"⚠️ Erro no Gemini: {e}"

# ─── GRÁFICOS ─────────────────────────────────────────────────────────────────
def fig_bvr(df, modo):
    fig=go.Figure()
    if modo=="Barras":
        fig.add_bar(name="Budget",x=df["Mes"],y=df["Budget"],
                    marker_color=C_BUD,marker_line_width=0,
                    hovertemplate="%{x}<br>Budget: R$ %{y:,.0f}<extra></extra>")
        fig.add_bar(name="Realizado",x=df["Mes"],y=df["Realizado"],
                    marker_color=C_REAL,marker_line_width=0,
                    hovertemplate="%{x}<br>Realizado: R$ %{y:,.0f}<extra></extra>")
        fig.update_layout(**PLOTLY_BASE,barmode="group",title=tl("Budget × Realizado por Mês"))
    else:
        fig.add_scatter(name="Budget",x=df["Mes"],y=df["Budget"],
                        mode="lines+markers",line=dict(color=C_BUD,width=2),marker=dict(size=5))
        fig.add_scatter(name="Realizado",x=df["Mes"],y=df["Realizado"],
                        mode="lines+markers",line=dict(color=C_REAL,width=2),marker=dict(size=5))
        fig.update_layout(**PLOTLY_BASE,title=tl("Evolução Mensal"))
    return fig

def fig_delta(df):
    cores=[C_REAL if v>=0 else C_VERM for v in df["Delta"]]
    fig=go.Figure()
    fig.add_bar(x=df["Mes"],y=df["Delta"],marker_color=cores,marker_line_width=0,name="Delta",
                hovertemplate="%{x}<br>Delta: R$ %{y:,.0f}<extra></extra>")
    fig.add_hline(y=0,line_color="#21283a",line_width=1)
    fig.update_layout(**PLOTLY_BASE,showlegend=False,title=tl("Delta Mensal (Budget − Realizado)"))
    return fig

def fig_contas(df):
    top=df.nlargest(12,"Realizado")
    fig=go.Figure()
    fig.add_bar(name="Budget",y=top["Conta"],x=top["Budget"],
                orientation="h",marker_color=C_BUD,marker_line_width=0)
    fig.add_bar(name="Realizado",y=top["Conta"],x=top["Realizado"],
                orientation="h",marker_color=C_REAL,marker_line_width=0)
    layout={**PLOTLY_BASE,"barmode":"group","height":380,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":tl("Top Contas · Budget vs Realizado")}
    fig.update_layout(**layout)
    return fig

def fig_forn(df):
    top=df.groupby("Fornecedor")["Valor"].sum().nlargest(12).reset_index()
    fig=go.Figure()
    fig.add_bar(y=top["Fornecedor"],x=top["Valor"],orientation="h",
                marker_color=C_DELT,marker_line_width=0,
                hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>")
    layout={**PLOTLY_BASE,"height":380,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":tl("Top 12 Fornecedores por Gasto")}
    fig.update_layout(**layout)
    return fig

def fig_cc(df):
    top=df.groupby("CC")["Valor"].sum().nlargest(15).reset_index()
    fig=go.Figure()
    fig.add_bar(y=top["CC"],x=top["Valor"],orientation="h",
                marker_color="#a064c8",marker_line_width=0,
                hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>")
    layout={**PLOTLY_BASE,"height":380,
            "yaxis":{**PLOTLY_BASE["yaxis"],"autorange":"reversed"},
            "title":tl("Realizado por Centro de Custo")}
    fig.update_layout(**layout)
    return fig

def fig_cc_empilhado(df, meses):
    ccs=df.groupby("CC")["Valor"].sum().nlargest(10).index.tolist()
    fig=go.Figure()
    for i,cc in enumerate(ccs):
        sub=(df[df["CC"]==cc].groupby("Mes")["Valor"].sum()
               .reindex(meses,fill_value=0))
        fig.add_bar(name=cc,x=meses,y=sub.values,
                    marker_color=PALETTE[i%len(PALETTE)],marker_line_width=0)
    fig.update_layout(**PLOTLY_BASE,barmode="stack",
                      title=tl("Realizado por Mês — empilhado por Centro de Custo"))
    return fig

def fig_cc_separados(df, meses):
    ccs=df.groupby("CC")["Valor"].sum().nlargest(9).index.tolist()
    n=len(ccs); cols=min(3,n); rows=(n+cols-1)//cols
    if n==0: return None
    fig=make_subplots(rows=rows,cols=cols,subplot_titles=ccs,
                      vertical_spacing=0.12,horizontal_spacing=0.06)
    for i,cc in enumerate(ccs):
        row,col=divmod(i,cols); row+=1; col+=1
        sub=(df[df["CC"]==cc].groupby("Mes")["Valor"].sum()
               .reindex(meses,fill_value=0))
        fig.add_bar(x=meses,y=sub.values,
                    marker_color=PALETTE[i%len(PALETTE)],
                    marker_line_width=0,showlegend=False,row=row,col=col)
        fig.update_xaxes(tickfont=dict(size=8,color="#7d8590"),gridcolor="#21283a",row=row,col=col)
        fig.update_yaxes(tickfont=dict(size=8,color="#7d8590"),gridcolor="#21283a",row=row,col=col)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter,sans-serif",color="#7d8590",size=10),
                      height=max(220*rows,300),margin=dict(t=40,b=8,l=8,r=8),
                      showlegend=False,title=tl("Realizado por Centro — Separados"))
    for ann in fig.layout.annotations:
        ann.font.color="#e6edf3"; ann.font.size=11
    return fig

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    check_auth()

    st.markdown("""
    <div style='display:flex;align-items:center;gap:10px;padding:14px 0 10px;
                border-bottom:1px solid #21283a;margin-bottom:16px;'>
      <div>
        <div style='font-size:1.15rem;font-weight:700;color:#e6edf3;'>
          🏢 Facilities Intelligence
          <span class="badge">Cobli</span>
          <span class="badge-ia">✦ IA</span></div>
        <div style='font-size:.78rem;color:#7d8590;margin-top:2px;'>
          Análise inteligente de NFs · Budget × Realizado · Redução de Custos</div>
      </div></div>""",unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### Facilities Intelligence")
        if st.button("🚪 Sair"):
            st.session_state["_ok"]=False; st.rerun()
        st.markdown("---")
        if st.checkbox("🔄 Auto-refresh 60s",value=True):
            st.markdown("<script>setTimeout(()=>location.reload(),60000)</script>",
                        unsafe_allow_html=True)
        st.markdown("---")
        st.caption("📊 Planilha conectada")
        st.caption(f"🔗 [Abrir no Sheets]({URL_PLANILHA})")

    url=st.secrets.get("url_planilha","") if "url_planilha" in st.secrets else URL_PLANILHA

    with st.spinner("Carregando dados…"):
        try:
            cli   = get_client()
            df_l  = load_lancamentos(cli, url)
            df_b  = load_budget(cli, url)
        except Exception as e:
            st.error(f"Erro ao carregar planilha: {e}"); st.stop()

    if df_l.empty and df_b.empty:
        st.warning("Nenhum dado encontrado."); return

    # ── FILTROS ──────────────────────────────────────────────────────────────
    st.markdown("---")
    anos=sorted(set(df_l["Ano"].dropna())|set(df_b["Ano"].dropna()),reverse=True)
    anos=[a for a in anos if str(a).isdigit()]

    c1,c2,c3,c4,c5=st.columns([.8,1,1.2,1.3,.9])
    with c1:
        ano=st.selectbox("Ano",["Todos"]+anos,
                         index=1 if "2026" in anos else 0)
    with c2:
        la=df_l[df_l["Ano"]==ano] if ano!="Todos" else df_l
        ba=df_b[df_b["Ano"]==ano] if ano!="Todos" else df_b
        meses=sorted(set(la["Mes"].dropna())|set(ba["Mes"].dropna()),key=mes_ord)
        mes=st.selectbox("Mês",["Todos"]+meses)
    with c3:
        ccs=sorted(la["CC"].dropna().replace("","(sem CC)").unique())
        cc_sel=st.selectbox("Centro de Custo",["Todos"]+[c for c in ccs if c])
    with c4:
        contas_disp=sorted(la["Conta"].dropna().unique())
        conta_sel=st.selectbox("Conta",["Todas"]+contas_disp)
    with c5:
        if st.button("↺ Atualizar",use_container_width=True):
            st.cache_data.clear(); st.rerun()

    # Aplicar filtros
    fl=df_l.copy(); fb=df_b.copy()
    if ano!="Todos":      fl=fl[fl["Ano"]==ano];      fb=fb[fb["Ano"]==ano]
    if mes!="Todos":      fl=fl[fl["Mes"]==mes];      fb=fb[fb["Mes"]==mes]
    if cc_sel!="Todos":   fl=fl[fl["CC"]==cc_sel]
    if conta_sel!="Todas":fl=fl[fl["Conta"]==conta_sel]; fb=fb[fb["Conta"]==conta_sel]

    if fl.empty and fb.empty:
        st.info("Nenhum dado para os filtros selecionados."); return

    # Cruzamento Budget × Realizado por conta
    real_conta=(fl.groupby("Conta",as_index=False)["Valor"].sum()
                  .rename(columns={"Valor":"Realizado"}))
    bud_conta =(fb.groupby("Conta",as_index=False)["Budget"].sum())
    df_bi=pd.merge(bud_conta,real_conta,on="Conta",how="outer").fillna(0)
    df_bi["Delta"]=df_bi["Budget"]-df_bi["Realizado"]
    df_bi["PctExec"]=np.where(df_bi["Budget"]>0,
                               df_bi["Realizado"]/df_bi["Budget"]*100,0)
    df_bi["Status"]=np.select(
        [df_bi["Realizado"]>df_bi["Budget"],
         df_bi["Realizado"]>=df_bi["Budget"]*0.85],
        ["🔴 Estourou","🟡 Alerta"],default="🟢 OK")

    # Resumo mensal
    real_mes=(fl.groupby("Mes",as_index=False)["Valor"].sum()
                .rename(columns={"Valor":"Realizado"}))
    bud_mes =(fb.groupby("Mes",as_index=False)["Budget"].sum())
    df_mes=pd.merge(bud_mes,real_mes,on="Mes",how="outer").fillna(0)
    df_mes["Delta"]=df_mes["Budget"]-df_mes["Realizado"]
    df_mes=df_mes.sort_values("Mes",key=lambda s:s.map(mes_ord))
    meses_l=df_mes["Mes"].tolist()
    meses_real=sorted(fl["Mes"].dropna().unique(),key=mes_ord)

    tot_b  = df_mes["Budget"].sum()
    tot_r  = df_mes["Realizado"].sum()
    tot_d  = df_mes["Delta"].sum()
    pct    = tot_r/tot_b*100 if tot_b>0 else 0

    # ── ABAS ─────────────────────────────────────────────────────────────────
    tab1,tab2,tab3,tab4,tab5,tab6=st.tabs([
        "📊 Visão Geral","📋 Por Conta","🏢 Centro de Custo",
        "🏭 Fornecedores","🔎 Lançamentos","✦ Análise IA",
    ])

    # ══ VISÃO GERAL ══════════════════════════════════════════════════════════
    with tab1:
        k1,k2,k3,k4=st.columns(4)
        with k1: kpi("Total Budget",brl(tot_b),f"{len(df_mes)} meses")
        with k2:
            cor="red" if tot_r>tot_b else "green"
            kpi("Total Realizado",brl(tot_r),f"{pct:.1f}% executado",cor)
        with k3:
            cor="green" if tot_d>=0 else "red"
            sinal="+" if tot_d>=0 else ""
            kpi("Saldo (Delta)",f"{sinal}{brl(tot_d)}",
                "Dentro do budget ✓" if tot_d>=0 else "Acima do budget ⚠️",cor)
        with k4:
            kpi("NFs / Fornecedores",
                f"{len(fl):,}",
                f"{fl['Fornecedor'].nunique()} fornecedores únicos","blue")

        st.markdown("---")
        modo=st.radio("Gráfico",["Barras","Linha"],horizontal=True,key="g1")
        if not df_mes.empty:
            st.plotly_chart(fig_bvr(df_mes,modo),use_container_width=True)
            st.plotly_chart(fig_delta(df_mes),use_container_width=True)

    # ══ POR CONTA ════════════════════════════════════════════════════════════
    with tab2:
        if not df_bi.empty:
            st.plotly_chart(fig_contas(df_bi),use_container_width=True)
            st.markdown("---")
            st.dataframe(
                df_bi[["Status","Conta","Budget","Realizado","Delta","PctExec"]]
                  .sort_values("Realizado",ascending=False).reset_index(drop=True),
                hide_index=True,use_container_width=True,
                column_config={
                    "Status":   st.column_config.TextColumn("Alerta",width="small"),
                    "Conta":    st.column_config.TextColumn("Conta"),
                    "Budget":   st.column_config.NumberColumn("Budget",   format="R$ %.2f"),
                    "Realizado":st.column_config.NumberColumn("Realizado",format="R$ %.2f"),
                    "Delta":    st.column_config.NumberColumn("Saldo",    format="R$ %.2f"),
                    "PctExec":  st.column_config.ProgressColumn("Execução",format="%.1f%%",
                                                                 min_value=0,max_value=100),
                })

    # ══ CENTRO DE CUSTO ══════════════════════════════════════════════════════
    with tab3:
        if fl.empty:
            st.info("Sem lançamentos para os filtros selecionados.")
        else:
            cc_agg=(fl.groupby("CC",as_index=False)["Valor"].sum()
                      .sort_values("Valor",ascending=False))
            k1,k2,k3,k4=st.columns(4)
            with k1: kpi("Centros Ativos",str(len(cc_agg)))
            with k2: kpi("Total Realizado",brl(cc_agg["Valor"].sum()))
            with k3:
                top_cc=cc_agg.iloc[0]
                kpi("Maior CC",top_cc["CC"],brl(top_cc["Valor"]))
            with k4:
                conc=cc_agg.head(3)["Valor"].sum()/cc_agg["Valor"].sum()*100
                kpi("Concentração Top 3",f"{conc:.1f}%","do total","red" if conc>70 else "yellow")

            st.markdown("---")
            modo_cc=st.radio("Visualização",["Juntos","Separados"],horizontal=True,key="gcc")
            if modo_cc=="Juntos":
                col1,col2=st.columns(2)
                with col1: st.plotly_chart(fig_cc(fl),use_container_width=True)
                with col2:
                    if meses_real:
                        st.plotly_chart(fig_cc_empilhado(fl,meses_real),use_container_width=True)
            else:
                fs=fig_cc_separados(fl,meses_real)
                if fs: st.plotly_chart(fs,use_container_width=True)

            st.markdown("---")
            cc_agg["%Total"]=np.where(cc_agg["Valor"].sum()>0,
                                       cc_agg["Valor"]/cc_agg["Valor"].sum()*100,0)
            st.dataframe(cc_agg.reset_index(drop=True),hide_index=True,
                         use_container_width=True,
                         column_config={
                             "CC":     st.column_config.TextColumn("Centro de Custo"),
                             "Valor":  st.column_config.NumberColumn("Realizado",format="R$ %.2f"),
                             "%Total": st.column_config.ProgressColumn("% do Total",
                                       format="%.1f%%",min_value=0,max_value=100),
                         })

    # ══ FORNECEDORES ═════════════════════════════════════════════════════════
    with tab4:
        if fl.empty:
            st.info("Sem dados de fornecedores.")
        else:
            top10=fl.groupby("Fornecedor")["Valor"].sum().nlargest(10).reset_index()
            k1,k2,k3=st.columns(3)
            with k1: kpi("Fornecedores únicos",str(fl["Fornecedor"].nunique()))
            with k2:
                t1=top10.iloc[0]
                kpi("Maior Fornecedor",t1["Fornecedor"][:26],brl(t1["Valor"]))
            with k3:
                conc=top10["Valor"].sum()/fl["Valor"].sum()*100
                kpi("Concentração Top 10",f"{conc:.1f}%","do total realizado",
                    "red" if conc>70 else "yellow" if conc>50 else "green")

            st.markdown("---")
            st.plotly_chart(fig_forn(fl),use_container_width=True)
            st.markdown("---")
            ft=(fl.groupby("Fornecedor",as_index=False)
                  .agg(Realizado=("Valor","sum"),NFs=("NF","count"),
                       Contas=("Conta","nunique"))
                  .sort_values("Realizado",ascending=False).reset_index(drop=True))
            ft["%Total"]=np.where(ft["Realizado"].sum()>0,
                                   ft["Realizado"]/ft["Realizado"].sum()*100,0)
            st.dataframe(ft,hide_index=True,use_container_width=True,
                         column_config={
                             "Fornecedor": st.column_config.TextColumn("Fornecedor"),
                             "Realizado":  st.column_config.NumberColumn("Total",format="R$ %.2f"),
                             "NFs":        st.column_config.NumberColumn("Qtd NFs",format="%d"),
                             "Contas":     st.column_config.NumberColumn("Contas",format="%d"),
                             "%Total":     st.column_config.ProgressColumn("% Total",
                                           format="%.1f%%",min_value=0,max_value=100),
                         })

    # ══ LANÇAMENTOS ══════════════════════════════════════════════════════════
    with tab5:
        if fl.empty:
            st.info("Sem lançamentos para os filtros selecionados.")
        else:
            k1,k2,k3=st.columns(3)
            with k1: kpi("Total Lançamentos",f"{len(fl):,}")
            with k2: kpi("Total Realizado",brl(fl["Valor"].sum()))
            with k3: kpi("Ticket Médio",brl(fl["Valor"].mean()))
            st.markdown("---")

            # Pivot conta × mês
            if not fl.empty:
                pivot=(fl.groupby(["Conta","Mes"])["Valor"]
                         .sum().unstack(fill_value=0).reset_index())
                mcols=sorted([c for c in pivot.columns if c!="Conta"],key=mes_ord)
                pivot=pivot[["Conta"]+mcols]
                pivot["Total"]=pivot[mcols].sum(axis=1)
                st.markdown("##### Pivot: Conta × Mês")
                st.dataframe(pivot.sort_values("Total",ascending=False).reset_index(drop=True),
                             hide_index=True,use_container_width=True)

            st.markdown("---")
            st.markdown("##### Detalhe linha a linha")
            cols_show=["Mes","Fornecedor","Conta","CC","Valor","NF","Descricao"]
            st.dataframe(
                fl[cols_show].sort_values(["Mes","Valor"],ascending=[True,False])
                  .reset_index(drop=True),
                hide_index=True,use_container_width=True,
                column_config={
                    "Mes":       st.column_config.TextColumn("Mês"),
                    "Fornecedor":st.column_config.TextColumn("Fornecedor"),
                    "Conta":     st.column_config.TextColumn("Conta"),
                    "CC":        st.column_config.TextColumn("Centro"),
                    "Valor":     st.column_config.NumberColumn("Valor",format="R$ %.2f"),
                    "NF":        st.column_config.TextColumn("Nº NF"),
                    "Descricao": st.column_config.TextColumn("Descrição"),
                })

    # ══ ANÁLISE IA ════════════════════════════════════════════════════════════
    with tab6:
        st.markdown("""
        <div style='margin-bottom:16px;'>
          <div style='font-size:.9rem;font-weight:600;color:#e6edf3;margin-bottom:4px;'>
            ✦ Análise Inteligente de Gastos</div>
          <div style='font-size:.78rem;color:#7d8590;'>
            O assistente analisa os dados do período filtrado e identifica oportunidades de
            redução de custos, anomalias e tendências.</div></div>""",unsafe_allow_html=True)

        sugestoes=[
            "🔍 Identifique as principais oportunidades de redução de gastos",
            "⚠️ Quais contas estão estourando o budget e por quê?",
            "🏭 Analise a concentração de fornecedores e riscos",
            "📈 Identifique tendências e projete os próximos 3 meses",
            "💡 Sugira 5 ações concretas para reduzir custos este semestre",
            "🏢 Qual centro de custo tem maior potencial de otimização?",
        ]
        cols_s=st.columns(3)
        for i,s in enumerate(sugestoes):
            with cols_s[i%3]:
                if st.button(s,use_container_width=True,key=f"sug_{i}"):
                    st.session_state["ia_p"]=s.split(" ",1)[1]

        st.markdown("---")
        if "ia_hist" not in st.session_state: st.session_state["ia_hist"]=[]
        if "ia_p"    not in st.session_state: st.session_state["ia_p"]=""

        for msg in st.session_state["ia_hist"]:
            if msg["role"]=="user":
                st.markdown(f"""<div style='background:#21283a;border-radius:8px;
                  padding:10px 14px;margin-bottom:8px;font-size:.83rem;color:#c9d1d9;'>
                  👤 {msg["content"]}</div>""",unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="ia-box">
                  <div class="ia-header">✦ Análise IA · Facilities Intelligence</div>
                  <div class="ia-content">{msg["content"]}</div></div>""",
                  unsafe_allow_html=True)

        pergunta=st.text_area("Pergunta",value=st.session_state.get("ia_p",""),
            placeholder="Ex: Quais fornecedores têm maior potencial de negociação?",
            height=90,label_visibility="collapsed",key="ia_in")

        bc1,bc2,bc3=st.columns([1.5,1,1])
        with bc1: analisar=st.button("✦ Analisar com IA",use_container_width=True,type="primary")
        with bc2:
            if st.button("🗑️ Limpar",use_container_width=True):
                st.session_state["ia_hist"]=[]; st.session_state["ia_p"]=""; st.rerun()
        with bc3: auto=st.button("⚡ Análise completa",use_container_width=True)

        if auto:
            pergunta=("Faça uma análise executiva completa: principais desvios de budget, "
                      "fornecedores críticos, concentração de risco, tendências e 5 ações "
                      "prioritárias de redução de custos para este semestre.")

        if (analisar or auto) and str(pergunta).strip():
            ctx=construir_contexto(fl,fb,df_bi,
                                   {"ano":ano,"mes":mes,"cc":cc_sel,"conta":conta_sel})
            with st.spinner("✦ Analisando dados…"):
                resp=chamar_ia(ctx,str(pergunta).strip(),st.session_state["ia_hist"])
            st.session_state["ia_hist"].append({"role":"user","content":str(pergunta).strip()})
            st.session_state["ia_hist"].append({"role":"assistant","content":resp})
            st.session_state["ia_p"]=""
            st.rerun()

        if not st.session_state["ia_hist"]:
            st.markdown("""<div style='text-align:center;padding:40px;
              color:#7d8590;font-size:.82rem;'>
              ✦ Selecione uma análise rápida ou faça uma pergunta para começar.<br>
              <span style='font-size:.75rem;opacity:.7;'>
                O assistente usa os dados do período filtrado.</span></div>""",
              unsafe_allow_html=True)

if __name__=="__main__":
    main()
