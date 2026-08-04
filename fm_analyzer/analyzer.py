"""
Motor de analise de eventos ShipTrack First Mile.

Recebe um DataFrame de eventos (colunas do export padrao) e classifica cada
tracking_id, replicando a inteligencia usada nas analises de ELP8/ESA8.

Colunas esperadas (nomes flexiveis, detectados automaticamente):
    tracking_id, status_event, status, reason, status_node_id, status_date, sender_id, city
"""
from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Deteccao de colunas (tolerante a variacoes de nome)
# ---------------------------------------------------------------------------
_COLUMN_ALIASES = {
    "tracking_id": ["tracking_id", "tracking", "trackingid", "tbr", "tracking id"],
    "status_event": ["status_event", "event", "evento", "status event"],
    "status": ["status"],
    "reason": ["reason", "motivo"],
    "status_node_id": ["status_node_id", "node", "node_id", "station", "status node id"],
    "status_date": ["status_date", "date", "data", "status date", "event_date"],
    "sender_id": ["sender_id", "sender", "origem_sistema"],
    "city": ["city", "cidade"],
}


def _resolve_columns(df: pd.DataFrame) -> dict:
    lower = {str(c).strip().lower(): c for c in df.columns}
    resolved = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower:
                resolved[canonical] = lower[a]
                break
    return resolved


def _codes(series) -> list:
    return [str(e).replace("EVENT_", "").strip() for e in series.tolist()]


# ---------------------------------------------------------------------------
# Classificacao de um unico tracking
# ---------------------------------------------------------------------------
def analyze_single_tracking(g: pd.DataFrame, cols: dict) -> dict:
    """Classifica um grupo de eventos (um tracking_id). Retorna dict com o resultado."""
    if cols.get("status_date"):
        g = g.sort_values(cols["status_date"], kind="stable")

    codes = _codes(g[cols["status_event"]])
    nodes = []
    if cols.get("status_node_id"):
        nodes = [str(n) for n in g[cols["status_node_id"]].tolist()
                 if pd.notna(n) and str(n).strip() not in ("", "nan")]

    def reason_of(code: str) -> str:
        if not cols.get("reason"):
            return ""
        sub = g[g[cols["status_event"]] == "EVENT_" + code][cols["reason"]].tolist()
        sub = [str(x) for x in sub if pd.notna(x) and str(x).strip() not in ("", "nan")]
        return sub[0] if sub else ""

    first_201 = next((i for i, c in enumerate(codes) if c == "201"), None)

    has_103 = "103" in codes
    n_216 = codes.count("216")
    has_201 = "201" in codes
    has_202 = "202" in codes
    has_104 = "104" in codes
    has_238 = "238" in codes
    has_301 = "301" in codes
    has_228 = "228" in codes
    n_201 = codes.count("201")
    n_cpt_miss = codes.count("661")
    n_cpt_warn = codes.count("660")
    encerramento = "259" in codes
    tem_423 = "423" in codes

    late_reinject = any(
        c in ("101", "503") and first_201 is not None and i > first_201
        for i, c in enumerate(codes)
    )

    # ---- Regra de classificacao (ordem de prioridade) ----
    categoria = ""
    flags = []

    if encerramento and not has_301:
        categoria = "ENCERRADO / BAIXA (259)"
        if tem_423:
            flags.append("cancelamento/excecao (423) antes da baixa")
        if has_103 and n_216 == 0:
            flags.append("coletado mas nunca recebido - baixa pos-coleta")
        if n_cpt_miss >= 1:
            flags.append(f"ficou travado ({n_cpt_miss}x CPT miss) antes da baixa")
    elif has_238:
        categoria = "RE-SLAMM"
        if late_reinject:
            flags.append("FORCADO (reinjecao SPS pos-stow)")
        if n_201 >= 5:
            flags.append(f"stow repetido {n_201}x (manipulacao)")
    elif has_103 and n_216 == 0 and not has_201 and not has_301 and n_cpt_miss >= 1:
        categoria = "PACOTE PERDIDO / TRAVADO"
        flags.append("coletado mas nunca recebido/estufado")
    elif has_103 and n_216 == 0:
        categoria = "GAP DE RECEBIMENTO (coletado sem 216)"
        if has_104:
            flags.append(f"cancelado/RTO (104 {reason_of('104')})")
    elif not has_103 and n_216 == 0 and (has_201 or has_202):
        categoria = "ORFAO (sem coleta e sem receive)"
    elif n_216 >= 1 and has_104:
        categoria = "RECEBIDO porem CANCELADO/RTO"
        flags.append(f"104 reason {reason_of('104')}")
    elif n_216 >= 1 and has_201 and has_202:
        categoria = "RECEBIDO - fluxo normal"
    elif n_216 >= 1:
        categoria = "RECEBIDO - parcial"
    else:
        categoria = "INDEFINIDO (verificar eventos)"

    if tem_423 and "423" not in "".join(flags):
        flags.append("evento 423 (cancel/excecao)")
    if has_228:
        flags.append("cross-dock (XD)")
    if n_cpt_miss >= 1:
        flags.append(f"CPT miss {n_cpt_miss}x (661)")
    if has_301:
        flags.append("entregue (301)")
    if encerramento:
        flags.append("encerrado/baixa (259)")

    rota = ">".join(dict.fromkeys(nodes)) if nodes else "-"
    origem = nodes[0] if nodes else ""
    destino = nodes[-1] if nodes else ""

    analise = categoria
    if flags:
        analise += " | " + "; ".join(flags)
    analise += (f" || 216x{n_216} 103:{'S' if has_103 else 'N'}"
                f" 201:{'S' if has_201 else 'N'} 202:{'S' if has_202 else 'N'}"
                f" | Rota: {rota}")

    return {
        "categoria": categoria,
        "origem": origem,
        "destino": destino,
        "rota": rota,
        "tem_coleta_103": has_103,
        "qtd_receive_216": n_216,
        "tem_stow_201": has_201,
        "tem_dispatch_202": has_202,
        "cancelado_104": has_104,
        "reslamm_238": has_238,
        "cpt_miss_661": n_cpt_miss,
        "cpt_warn_660": n_cpt_warn,
        "entregue_301": has_301,
        "flags": "; ".join(flags),
        "sequencia_eventos": "-".join(codes),
        "analise": analise,
    }


# ---------------------------------------------------------------------------
# Analise do arquivo inteiro
# ---------------------------------------------------------------------------
def analyze_events(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Analisa um DataFrame de eventos.
    Retorna (df_resultado, resumo) onde df_resultado tem 1 linha por tracking_id.
    """
    cols = _resolve_columns(df)
    missing = [c for c in ("tracking_id", "status_event") if c not in cols]
    if missing:
        raise ValueError(
            f"Colunas obrigatorias ausentes: {missing}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    if cols.get("status_date"):
        df[cols["status_date"]] = pd.to_datetime(df[cols["status_date"]], errors="coerce")

    linhas = []
    for tid, g in df.groupby(cols["tracking_id"], sort=False):
        res = analyze_single_tracking(g, cols)
        res_row = {"tracking_id": str(tid)}
        res_row.update(res)
        linhas.append(res_row)

    resultado = pd.DataFrame(linhas)

    resumo = {
        "total_tracking_ids": len(resultado),
        "por_categoria": resultado["categoria"].value_counts().to_dict(),
        "gap_recebimento": int((resultado["categoria"].str.startswith("GAP")).sum()),
        "reslamm": int((resultado["categoria"] == "RE-SLAMM").sum()),
        "cancelados": int((resultado["categoria"].str.contains("CANCELADO")).sum()),
        "perdidos": int((resultado["categoria"].str.contains("PERDIDO")).sum()),
        "orfaos": int((resultado["categoria"].str.startswith("ORFAO")).sum()),
        "encerrados_baixa": int((resultado["categoria"].str.contains("ENCERRADO")).sum()),
        "entregues": int(resultado["entregue_301"].sum()),
    }
    return resultado, resumo
