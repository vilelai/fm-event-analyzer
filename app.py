"""
FM Event Analyzer - App web (Streamlit).

Uso local:
    pip install -r requirements.txt
    streamlit run app.py

Sobe um CSV/Excel de eventos ShipTrack e gera a analise por tracking_id.
"""
import io

import pandas as pd
import streamlit as st

from fm_analyzer import analyze_events, build_pivot, EVENT_CODES

st.set_page_config(page_title="FM Event Analyzer", page_icon="📦", layout="wide")

st.title("📦 FM Event Analyzer — First Mile")
st.caption("Sobe um arquivo de eventos (ShipTrack) e gera a analise automatica por tracking ID.")

with st.sidebar:
    st.header("ℹ️ Como usar")
    st.markdown(
        "1. Exporte os eventos (CSV ou Excel) com as colunas padrao "
        "(`tracking_id`, `status_event`, `status`, `reason`, `status_node_id`, `status_date`, `sender_id`).\n"
        "2. Suba o arquivo abaixo.\n"
        "3. Veja a analise e baixe o resultado."
    )
    st.divider()
    with st.expander("📖 Base de event codes"):
        kb = pd.DataFrame([
            {"Evento": k, "Nome": v["nome"], "Confirmado": "Sim" if v["confirmed"] else "A confirmar"}
            for k, v in EVENT_CODES.items()
        ])
        st.dataframe(kb, hide_index=True, use_container_width=True)

uploaded = st.file_uploader("Arquivo de eventos", type=["csv", "xlsx", "xls"])

sheet_name = None
if uploaded is not None and uploaded.name.lower().endswith((".xlsx", ".xls")):
    try:
        xls = pd.ExcelFile(uploaded)
        sheet_name = st.selectbox("Aba (sheet) com os eventos", xls.sheet_names,
                                  index=xls.sheet_names.index("EVENTS") if "EVENTS" in xls.sheet_names else 0)
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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracking IDs", resumo["total_tracking_ids"])
    c2.metric("Gap recebimento", resumo["gap_recebimento"])
    c3.metric("Re-slamm", resumo["reslamm"])
    c4.metric("Cancelados/RTO", resumo["cancelados"])
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Parados na FM", resumo["parados_na_fm"])
    c6.metric("Other mile", resumo["outras_milhas"])
    c7.metric("Danificados", resumo["danificados"])
    c8.metric("Entregues", resumo["entregues"])
    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Perdidos", resumo["perdidos"])
    c10.metric("Encerrados/baixa", resumo["encerrados_baixa"])

    # ---- Tabela dinamica ----
    st.subheader("Tabela dinamica")
    opcoes = {
        "Categoria": "categoria", "Localizacao": "local_simples",
        "Origem": "origem", "Destino (base)": "destino",
    }
    colf1, colf2 = st.columns(2)
    linha_sel = colf1.selectbox("Linhas", list(opcoes.keys()), index=0)
    col_sel = colf2.selectbox("Colunas", list(opcoes.keys()), index=1)
    pivot = build_pivot(resultado, opcoes[linha_sel], opcoes[col_sel])
    st.dataframe(pivot, use_container_width=True)

    st.subheader("Distribuicao por categoria")
    cat = pd.DataFrame(
        [{"Categoria": k, "Qtd": v} for k, v in resumo["por_categoria"].items()]
    ).sort_values("Qtd", ascending=False)
    st.bar_chart(cat.set_index("Categoria"))

    # ---- Tabela objetiva (colunas principais primeiro) ----
    st.subheader("Analise por tracking ID")
    cols_obj = ["tracking_id", "diagnostico", "categoria", "local_simples",
                "origem", "destino", "linha_do_tempo"]
    cols_obj = [c for c in cols_obj if c in resultado.columns]
    modo = st.radio("Exibir", ["Objetivo", "Completo"], horizontal=True)
    tabela = resultado[cols_obj] if modo == "Objetivo" else resultado
    st.dataframe(tabela, hide_index=True, use_container_width=True)

    # ---- Download ----
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resultado.to_excel(writer, index=False, sheet_name="Analise")
        cat.to_excel(writer, index=False, sheet_name="Resumo")
        pivot.to_excel(writer, sheet_name="TabelaDinamica")
    st.download_button(
        "⬇️ Baixar analise (Excel)",
        data=buffer.getvalue(),
        file_name="fm_analise_eventos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Aguardando arquivo. Formatos aceitos: CSV, XLSX, XLS.")
