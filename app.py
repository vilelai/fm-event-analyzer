"""
FM Event Analyzer - App web (Streamlit).

Uso local:
    pip install -r requirements.txt
    streamlit run app.py

Sobe o export do OBLT (CSV/Excel) e gera a analise objetiva por tracking ID.
"""
import io

import pandas as pd
import streamlit as st

from fm_analyzer import analyze_events, build_pivot, EVENT_CODES

st.set_page_config(page_title="FM Event Analyzer", page_icon="📦", layout="wide")

st.title("📦 FM Event Analyzer — First Mile")
st.caption("Sobe o export de eventos (OBLT) e gera a analise objetiva por tracking ID.")

with st.sidebar:
    st.header("ℹ️ Como usar")
    st.markdown(
        "1. Baixe o export de eventos no **OBLT** (CSV ou Excel).\n"
        "2. Suba o arquivo abaixo.\n"
        "3. Veja a analise e baixe o resultado.\n\n"
        "**Colunas lidas:** `tracking_id`, `status_event`, `status_node_id`, "
        "`status_date`, `reason`, `shiptrack_event`."
    )
    st.divider()
    with st.expander("📐 Logica da analise"):
        st.markdown(
            "**Eventos padrao de First Mile:** 103 (coleta) > 216 (receive) > "
            "201 (stow) > 202 (depart).\n\n"
            "A analise verifica se o pacote teve esses eventos e se houve algum "
            "**evento paralisador** que interrompe o fluxo:\n"
            "- **Re-slamm (238)** — re-etiquetagem\n"
            "- **Cancelado (104)** — gera RTO\n"
            "- **Danificado (108/407/408/416/423/432/485)** — 423 = PRISM (erro > RTO)\n"
            "- **Missort / Wrong node (414)** — node errado\n"
        )
    with st.expander("📖 Base de event codes"):
        kb = pd.DataFrame([
            {"Evento": k, "Nome": v["nome"], "Confirmado": "Sim" if v["confirmed"] else "A confirmar"}
            for k, v in EVENT_CODES.items()
        ])
        st.dataframe(kb, hide_index=True, use_container_width=True)

uploaded = st.file_uploader("Export de eventos (OBLT)", type=["csv", "xlsx", "xls"])

sheet_name = None
if uploaded is not None and uploaded.name.lower().endswith((".xlsx", ".xls")):
    try:
        xls = pd.ExcelFile(uploaded)
        default_idx = xls.sheet_names.index("EVENTS") if "EVENTS" in xls.sheet_names else 0
        sheet_name = st.selectbox("Aba (sheet) com os eventos", xls.sheet_names, index=default_idx)
    except Exception as e:  # noqa: BLE001
        st.error(f"Nao consegui ler as abas do Excel: {e}")

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded, sheet_name=sheet_name)
    except Exception as e:  # noqa: BLE001
        st.error(f"Erro ao ler o arquivo: {e}")
        st.stop()

    st.success(f"Arquivo lido: {len(df)} linhas de eventos.")

    try:
        resultado, resumo = analyze_events(df)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    # ---- Metricas ----
    st.subheader("Resumo")
    c1, c2, c3 = st.columns(3)
    c1.metric("Tracking IDs", resumo["total_tracking_ids"])
    c2.metric("Fluxo FM completo (Sim)", resumo["completos_sim"])
    c3.metric("Fluxo FM incompleto (Nao)", resumo["completos_nao"])

    # ---- Tabela dinamica ----
    st.subheader("Tabela dinamica (Fluxo completo x Evento paralisador)")
    st.dataframe(resumo["pivot"], use_container_width=True)

    # ---- Tabela principal: as 4 colunas ----
    st.subheader("Analise por tracking ID")
    cols_4 = ["tracking_id", "eventos_completos_fm", "ultima_movimentacao", "conclusao"]
    modo = st.radio("Exibir", ["Objetivo (4 colunas)", "Completo"], horizontal=True)
    if modo.startswith("Objetivo"):
        tabela = resultado[cols_4].rename(columns={
            "tracking_id": "Tracking ID",
            "eventos_completos_fm": "Eventos completos em FM?",
            "ultima_movimentacao": "Ultima movimentacao (node + evento)",
            "conclusao": "Conclusao",
        })
    else:
        tabela = resultado
    st.dataframe(tabela, hide_index=True, use_container_width=True)

    # ---- Download ----
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resultado[cols_4].rename(columns={
            "tracking_id": "Tracking ID",
            "eventos_completos_fm": "Eventos completos em FM?",
            "ultima_movimentacao": "Ultima movimentacao",
            "conclusao": "Conclusao",
        }).to_excel(writer, index=False, sheet_name="Analise")
        resultado.to_excel(writer, index=False, sheet_name="Detalhado")
        if resumo["pivot"] is not None:
            resumo["pivot"].to_excel(writer, sheet_name="TabelaDinamica")
    st.download_button(
        "⬇️ Baixar analise (Excel)",
        data=buffer.getvalue(),
        file_name="fm_analise_eventos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Aguardando arquivo. Formatos aceitos: CSV, XLSX, XLS.")
