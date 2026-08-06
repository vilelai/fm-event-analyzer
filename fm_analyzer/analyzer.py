"""
Motor de analise de eventos ShipTrack First Mile (modo objetivo).

Le o export do OBLT e, por tracking_id, responde 4 coisas:
    1. Tracking ID
    2. Possui os eventos completos de First Mile? (103>216>201>202)
    3. Onde foi a ultima movimentacao (node + evento)
    4. Conclusao: narrativa de onde o pacote parou + evento paralisador
       (re-slamm, cancelado, danificado, missort, etc.)

Colunas esperadas (nomes flexiveis): tracking_id, status_event, status,
reason, status_node_id, status_date, sender_id, shiptrack_event
"""
from __future__ import annotations

import csv
import os

import pandas as pd

from .event_codes import describe_event

# ---------------------------------------------------------------------------
# Deteccao de colunas (tolerante a variacoes de nome)
# ---------------------------------------------------------------------------
_COLUMN_ALIASES = {
    "tracking_id": ["tracking_id", "tracking", "trackingid", "tbr", "tracking id"],
    "status_event": ["status_event", "event", "evento", "status event"],
    "shiptrack_event": ["shiptrack_event", "shiptrack event"],
    "status": ["status"],
    "reason": ["reason", "motivo"],
    "status_node_id": ["status_node_id", "node", "node_id", "station", "status node id"],
    "status_date": ["status_date", "date", "data", "status date", "event_date"],
    "sender_id": ["sender_id", "sender", "origem_sistema"],
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
# Classificacao de nodes: First Mile vs Outra Milha (via nodes.csv)
# ---------------------------------------------------------------------------
FM_NODES = {"ELP8", "ELP7", "ESA8", "ESP8", "EUA8", "ESG8", "ESC8", "ERJ1"}


def _load_nodes_csv():
    path = os.path.join(os.path.dirname(__file__), "nodes.csv")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                node = str(row.get("node", "")).strip().upper()
                tipo = str(row.get("tipo", "")).strip().upper()
                if node and tipo in ("FM", "PN", "SPC", "SORT"):
                    FM_NODES.add(node)
    except Exception:  # noqa: BLE001
        pass


_load_nodes_csv()


def is_fm_node(node: str) -> bool:
    return str(node).strip().upper() in FM_NODES


# ---------------------------------------------------------------------------
# Eventos de referencia
# ---------------------------------------------------------------------------
# Eventos padrao do fluxo First Mile (na ordem)
FM_FLOW = ["103", "216", "201", "202"]
FM_FLOW_NOME = {
    "103": "Coleta (pickup)",
    "216": "Receive (recebido na base)",
    "201": "Stow (processado)",
    "202": "Depart (despachado)",
}
# Eventos de dano
DAMAGE_STRONG = {"407", "408", "423", "432", "485"}
DAMAGE_CONTEXT = {"108", "301", "416"}


# ---------------------------------------------------------------------------
# Analise de um unico tracking
# ---------------------------------------------------------------------------
def analyze_single_tracking(g: pd.DataFrame, cols: dict) -> dict:
    date_col = cols.get("status_date")
    node_col = cols.get("status_node_id")
    ev_col = cols["status_event"]

    if date_col:
        g = g.sort_values(date_col, kind="stable")

    codes = _codes(g[ev_col])
    codes_set = set(codes)

    def has(code):
        return code in codes_set

    # ---- presenca dos eventos padrao FM ----
    has_103 = has("103")
    has_216 = has("216")
    has_201 = has("201")
    has_202 = has("202")
    has_301 = has("301")  # entregue
    has_302 = has("302")  # em rota
    eventos_completos = has_103 and has_216 and has_201 and has_202

    # ---- evento paralisador (interrompe o fluxo) ----
    dano_codes = sorted(codes_set & DAMAGE_STRONG)
    if "shiptrack_event" in cols:
        stc = cols["shiptrack_event"]
        vals = {str(x).strip().upper() for x in g[stc].tolist()
                if pd.notna(x) and str(x).strip() not in ("", "nan")}
        if "DAMAGE" in vals:
            dano_codes += sorted(codes_set & DAMAGE_CONTEXT)
    danificado = bool(dano_codes)
    cancelado = has("104")
    missort = has("414")
    reslam = has("238")

    if danificado:
        paralisador = "Danificado"
    elif cancelado:
        paralisador = "Cancelado"
    elif missort:
        paralisador = "Missort (node errado)"
    elif reslam:
        paralisador = "Re-slamm"
    else:
        paralisador = "Nenhum"

    # ---- ultima movimentacao (node + evento) ----
    ult_code = codes[-1] if codes else ""
    ult_node = ""
    if node_col is not None and len(g):
        v = g.iloc[-1][node_col]
        ult_node = "" if pd.isna(v) or str(v).strip() in ("", "nan") else str(v).strip()
    ult_nome = describe_event(ult_code).get("nome", "") if ult_code else ""
    ultima_mov = (f"{ult_node or '?'} - EVENT_{ult_code} ({ult_nome})"
                  if ult_code else "-")

    # ---- ate onde chegou no funil FM ----
    if not has_103:
        etapa = "sem_coleta"
    elif not has_216:
        etapa = "sem_receive"
    elif not has_201:
        etapa = "sem_stow"
    elif not has_202:
        etapa = "sem_depart"
    else:
        etapa = "completo"

    # ---- desfecho apos FM completo ----
    ult_is_fm = is_fm_node(ult_node) if ult_node else False

    # ---- CONCLUSAO (narrativa) ----
    if etapa == "sem_coleta":
        base = "Pacote NAO foi coletado pelo DA (sem evento 103)."
    elif etapa == "sem_receive":
        base = "Pacote coletado pelo DA, mas NAO foi recebido na base (sem 216)."
    elif etapa == "sem_stow":
        base = "Pacote coletado e recebido na base, mas a base NAO processou/estufou o pacote (sem 201)."
    elif etapa == "sem_depart":
        base = "Pacote recebido e processado na base, mas NAO foi despachado para a proxima milha (sem 202)."
    else:  # completo
        if has_301:
            base = "Pacote processado corretamente em First Mile e ENTREGUE ao cliente."
        elif has_302:
            base = "Pacote processado corretamente em First Mile, saiu em rota mas NAO foi entregue na outra milha."
        elif not ult_is_fm and ult_node:
            base = "Pacote processado corretamente em First Mile e seguiu para outra milha (ainda nao entregue)."
        else:
            base = "Pacote processado corretamente em First Mile (aguardando proxima etapa)."

    # incorporar evento paralisador na conclusao
    if danificado:
        if "423" in dano_codes:
            extra = (" Foi marcado como DANIFICADO na reimpressao de etiqueta (PRISM/423) - "
                     "evento indevido; nao segue o fluxo completo, deve ir para RTO.")
        else:
            extra = f" Foi DANIFICADO no processo (evento {','.join(dano_codes)})."
        conclusao = base + extra
    elif cancelado:
        conclusao = base + f" Pacote CANCELADO (evento 104{', ' + reason_first(g, cols, '104') if reason_first(g, cols, '104') else ''}) - gerou RTO/retorno."
    elif missort:
        conclusao = base + " Sofreu MISSORT: a transportadora enviou para o node ERRADO (414)."
    elif reslam:
        conclusao = base + " Passou por RE-SLAMM (re-etiquetagem/238)."
    else:
        conclusao = base

    return {
        "eventos_completos_fm": "Sim" if eventos_completos else "Nao",
        "ultima_movimentacao": ultima_mov,
        "conclusao": conclusao,
        "evento_paralisador": paralisador,
        "sequencia_eventos": "-".join(codes),
    }


def reason_first(g, cols, code):
    if "reason" not in cols:
        return ""
    sub = g[g[cols["status_event"]] == "EVENT_" + code][cols["reason"]].tolist()
    sub = [str(x) for x in sub if pd.notna(x) and str(x).strip() not in ("", "nan")]
    return sub[0] if sub else ""


# ---------------------------------------------------------------------------
# Analise do arquivo inteiro
# ---------------------------------------------------------------------------
def analyze_events(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Analisa o DataFrame de eventos. Retorna (resultado, resumo)."""
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
        res = {"tracking_id": str(tid)}
        res.update(analyze_single_tracking(g, cols))
        linhas.append(res)

    resultado = pd.DataFrame(linhas)

    resumo = {
        "total_tracking_ids": len(resultado),
        "completos_sim": int((resultado["eventos_completos_fm"] == "Sim").sum()),
        "completos_nao": int((resultado["eventos_completos_fm"] == "Nao").sum()),
        "por_paralisador": resultado["evento_paralisador"].value_counts().to_dict(),
    }

    try:
        pivot = pd.crosstab(
            resultado["eventos_completos_fm"], resultado["evento_paralisador"],
            margins=True, margins_name="Total",
        )
        resumo["pivot"] = pivot
    except Exception:  # noqa: BLE001
        resumo["pivot"] = None

    return resultado, resumo


def build_pivot(resultado: pd.DataFrame, linhas: str = "eventos_completos_fm",
                colunas: str = "evento_paralisador") -> pd.DataFrame:
    """Tabela dinamica (contagem) entre duas colunas do resultado."""
    return pd.crosstab(resultado[linhas], resultado[colunas],
                       margins=True, margins_name="Total")
