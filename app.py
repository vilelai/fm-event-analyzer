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
    with st.expander("📐 Conceitos e SLA (premissas FM)"):
        st.markdown(
            "**Funil sequencial** (a perda e a 1a etapa que falha):\n\n"
            "1. **Pickup** — recebeu 103 (coleta)\n"
            "2. **Receive success** — 216 ate **D+1 5:59am** do 103, senao MISS\n"
            "3. **Stow success** — 201 ate **D+1 5:59am** do 216, senao MISS\n"
            "4. **Depart success** — 202 ate **D+1 5:59am** da data-ref do 201 "
            "(regra D-1/D0: 201 entre 0:00-5:59 conta D-1), senao MISS\n\n"
            "**Outros conceitos:**\n"
            "- **Aging** — dias desde o nascimento (503) ate o ultimo evento\n"
            "- **Backlog 3+ dias** — 103 parado 3+ dias sem chegar next mile\n"
            "- **Wrong node (414)** — mis-sort na rede da transportadora\n"
            "- **Re-slamm (238)** — re-etiquetagem\n"
            "- **CED Missed (259)** — estouro do prazo de entrega\n\n"
            "**Eventos:** 103 pickup | 216 arrival/receive | 201 stow/processed | "
            "202 departure | 414 wrong node"
        )
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
    st.subheader("Resumo do funil (Pickup > Receive > Stow > Depart)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracking IDs", resumo["total_tracking_ids"])
    c2.metric("Gap RECEIVE", resumo["gap_receive"])
    c3.metric("Gap STOW", resumo["gap_stow"])
    c4.metric("Gap DEPART", resumo["gap_depart"])
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Sem coleta (103)", resumo["sem_coleta"])
    c6.metric("Wrong node (414)", resumo["wrong_node_414"])
    c7.metric("Re-slamm (238)", resumo["reslam_238"])
    c8.metric("Backlog 3+ dias", resumo["backlog_3d"])
    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Parados na FM", resumo["parados_na_fm"])
    c10.metric("Danificados", resumo["danificados"])
    c11.metric("CED Missed", resumo["ced_missed"])
    c12.metric("Aging medio (dias)", resumo["aging_medio_dias"])

    # ---- Tabela dinamica ----
    st.subheader("Tabela dinamica")
    opcoes = {
        "Onde falhou": "onde_falhou", "Categoria": "categoria",
        "Localizacao": "local_simples", "Origem": "origem",
        "Destino (base)": "destino", "Etapa Receive": "etapa_receive",
        "Etapa Stow": "etapa_stow", "Etapa Depart": "etapa_depart",
    }
    colf1, colf2 = st.columns(2)
    linha_sel = colf1.selectbox("Linhas", list(opcoes.keys()), index=0)
    col_sel = colf2.selectbox("Colunas", list(opcoes.keys()), index=2)
    pivot = build_pivot(resultado, opcoes[linha_sel], opcoes[col_sel])
    st.dataframe(pivot, use_container_width=True)

    st.subheader("Distribuicao por categoria")
    cat = pd.DataFrame(
        [{"Categoria": k, "Qtd": v} for k, v in resumo["por_categoria"].items()]
    ).sort_values("Qtd", ascending=False)
    st.bar_chart(cat.set_index("Categoria"))

    # ---- Tabela objetiva (colunas principais primeiro) ----
    st.subheader("Analise por tracking ID")
    cols_obj = ["tracking_id", "aging_dias", "localizacao_atual",
                "conclusao", "tratativa"]
    cols_obj = [c for c in cols_obj if c in resultado.columns]
    modo = st.radio("Exibir", ["Objetivo", "Completo"], horizontal=True)
    if modo == "Objetivo":
        tabela = resultado[cols_obj].rename(columns={
            "tracking_id": "Tracking ID",
            "aging_dias": "Aging (dias)",
            "localizacao_atual": "Local atual",
            "conclusao": "Problema / O que aconteceu",
            "tratativa": "Tratativa",
        })
    else:
        tabela = resultado
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
