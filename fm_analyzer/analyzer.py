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
# Classificacao de nodes: First Mile vs Hub/Middle Mile vs downstream
# (listas ajustaveis - baseadas no contexto FM Brasil)
# ---------------------------------------------------------------------------
# Fallback minimo (a lista completa e autoritativa vem de nodes.csv).
# Todos os nodes FM oficiais tem prefixo "E" (SPC = Seller Pickup Center, PN = Partner Node).
FM_NODES = {
    "ELP8", "ELP7", "ESA8", "ESP8", "EUA8", "ESG8", "ESC8", "ERJ1",
}
HUB_NODES = {
    "CGH7", "CGH3", "GIG7", "TBAV", "DBH5", "CNF7", "DPR2", "RIDQ", "TMOA",
    "TRIO", "IXNN", "ZZEJ", "ZUTD", "YBN6", "PTOP", "MMIF",
}


# Carrega/mescla nodes de um CSV externo (fm_analyzer/nodes.csv) se existir.
# Colunas: node,tipo(,regional,cidade). tipo FM/PN/SPC -> First Mile; HUB -> hub.
def _load_nodes_csv():
    import csv
    import os
    path = os.path.join(os.path.dirname(__file__), "nodes.csv")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                node = str(row.get("node", "")).strip().upper()
                tipo = str(row.get("tipo", "")).strip().upper()
                if not node:
                    continue
                if tipo in ("FM", "PN", "SPC", "SORT"):
                    FM_NODES.add(node)
                elif tipo == "HUB":
                    HUB_NODES.add(node)
    except Exception:  # noqa: BLE001
        pass


_load_nodes_csv()


def classify_node(node: str) -> str:
    """Retorna 'FM' se o node esta na lista oficial de First Mile, senao 'OTHER_MILE'.
    Qualquer node fora da lista FM e considerado outra milha (middle/last mile)."""
    node = str(node).strip().upper()
    if node in FM_NODES:
        return "FM"
    return "OTHER_MILE"


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

    # --- helper: primeiro registro de um evento como "NODE dd/mm HH:MM" ---
    date_col = cols.get("status_date")
    node_col = cols.get("status_node_id")

    def marco(code: str) -> str:
        sub = g[g[cols["status_event"]] == "EVENT_" + code]
        if len(sub) == 0:
            return ""
        row = sub.iloc[0]
        node = str(row[node_col]) if node_col and pd.notna(row[node_col]) else ""
        node = "" if node in ("nan", "None") else node
        dt = ""
        if date_col and pd.notna(row[date_col]):
            try:
                dt = pd.to_datetime(row[date_col]).strftime("%d/%m %H:%M")
            except Exception:  # noqa: BLE001
                dt = str(row[date_col])
        partes = [p for p in (node, dt) if p]
        return " ".join(partes) if partes else "sim"

    # --- DANO: detectado por EVENT codes de dano (oficial) ou shiptrack_event=DAMAGE ---
    # Codigos de dano dedicados (sempre indicam dano):
    DAMAGE_EVENTS_STRONG = {"407", "408", "423", "432", "485"}
    # Codigos que so significam dano no contexto DAMAGE (uso duplo): 108, 301, 416
    DAMAGE_EVENTS_CONTEXT = {"108", "301", "416"}

    codes_set = set(codes)
    dano_codes = sorted(codes_set & DAMAGE_EVENTS_STRONG)

    # coluna shiptrack_event (2a coluna do export) confirma dano
    shiptrack_damage = False
    if "shiptrack_event" in {str(c).strip().lower() for c in g.columns}:
        st_col = [c for c in g.columns if str(c).strip().lower() == "shiptrack_event"][0]
        vals = {str(x).strip().upper() for x in g[st_col].tolist()
                if pd.notna(x) and str(x).strip() not in ("", "nan")}
        shiptrack_damage = "DAMAGE" in vals
        if shiptrack_damage:
            dano_codes += sorted(codes_set & DAMAGE_EVENTS_CONTEXT)

    danificado = bool(dano_codes) or shiptrack_damage

    first_201 = next((i for i, c in enumerate(codes) if c == "201"), None)

    # --- marcos operacionais ---
    has_503 = "503" in codes
    has_103 = "103" in codes
    n_216 = codes.count("216")
    n_201 = codes.count("201")
    has_201 = n_201 >= 1
    has_202 = "202" in codes
    n_checkin = codes.count("253")
    n_checkout = codes.count("254")
    has_104 = "104" in codes
    has_238 = "238" in codes
    has_301 = "301" in codes
    has_302 = "302" in codes
    has_228 = "228" in codes
    n_cpt_miss = codes.count("661")
    n_cpt_warn = codes.count("660")
    encerramento = "259" in codes
    tem_423 = "423" in codes
    excecao = any(c in ("370", "404", "636", "651", "699") for c in codes)

    late_reinject = any(
        c in ("101", "503") and first_201 is not None and i > first_201
        for i, c in enumerate(codes)
    )

    # ---- Regra de classificacao (ordem de prioridade) ----
    categoria = ""
    flags = []

    if danificado:
        categoria = "PACOTE DANIFICADO"
        if dano_codes:
            flags.append(f"eventos de dano: {','.join(dano_codes)}")
        if encerramento:
            flags.append("baixado apos dano (259)")
        if has_301:
            flags.append("entregue danificado (301)")
    elif encerramento and not has_301:
        categoria = "ENCERRADO / BAIXA (259)"
        if tem_423:
            flags.append("dano (423) antes da baixa")
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
    elif n_216 >= 1 and has_201 and has_202 and has_301:
        categoria = "RECEBIDO - fluxo normal (entregue)"
    elif n_216 >= 1 and has_201 and has_202:
        categoria = "RECEBIDO - fluxo normal (em transito)"
    elif n_216 >= 1 and has_201 and not has_202:
        categoria = "RECEBIDO + stow, SEM despacho (202)"
    elif n_216 >= 1:
        categoria = "RECEBIDO - parcial (sem stow)"
    else:
        categoria = "INDEFINIDO (verificar eventos)"

    # ---- flags adicionais ----
    if danificado and "dano" not in "".join(flags):
        flags.append(f"DANIFICADO ({','.join(dano_codes) if dano_codes else 'shiptrack=DAMAGE'})")
    if has_228:
        flags.append("cross-dock (XD)")
    if n_cpt_miss >= 1:
        flags.append(f"CPT miss {n_cpt_miss}x (661)")
    if excecao:
        flags.append("evento de excecao/hold")
    if has_301:
        flags.append("entregue (301)")
    if encerramento:
        flags.append("encerrado/baixa (259)")

    rota = ">".join(dict.fromkeys(nodes)) if nodes else "-"
    origem = nodes[0] if nodes else ""
    destino = nodes[-1] if nodes else ""

    # ---- LOCALIZACAO: onde o pacote esta / onde travou ----
    ultimo_node = destino
    tipo_ultimo = classify_node(ultimo_node) if ultimo_node else ""
    node_base = ultimo_node if ultimo_node else "?"

    if has_301:
        localizacao = f"ENTREGUE ao cliente (last mile concluido) - base: {node_base}"
    elif has_302:
        localizacao = f"EM ROTA DE ENTREGA (last mile) - base: {node_base}"
    elif encerramento:
        localizacao = "ENCERRADO / BAIXA - saiu do fluxo (259)"
    elif tipo_ultimo == "FM":
        if has_202:
            localizacao = f"PARADO NA MILHA DE FM - base: {node_base} (despachado mas nao saiu)"
        else:
            localizacao = f"PARADO NA MILHA DE FM - base: {node_base} (SEM despacho 202)"
    else:
        # qualquer node fora da lista FM = outra milha
        localizacao = f"OTHER MILE - base: {node_base}"

    if n_cpt_miss >= 1 and not has_301:
        localizacao += f" | ATRASADO ({n_cpt_miss}x CPT miss)"

    # localizacao simplificada (para tabela dinamica)
    if "MILHA DE FM" in localizacao:
        local_simples = "PARADO NA FM"
    elif "OTHER MILE" in localizacao:
        local_simples = "OTHER MILE"
    elif "ENTREGUE" in localizacao:
        local_simples = "ENTREGUE"
    elif "ROTA DE ENTREGA" in localizacao:
        local_simples = "EM ROTA (last mile)"
    elif "BAIXA" in localizacao:
        local_simples = "BAIXA/ENCERRADO"
    else:
        local_simples = "OUTRO"

    # ---- linha do tempo legivel (so os marcos que existem) ----
    marcos_def = [
        ("Label(503)", "503"), ("Coleta(103)", "103"), ("Receive(216)", "216"),
        ("Stow(201)", "201"), ("Check-in(253)", "253"), ("Check-out(254)", "254"),
        ("Dispatch(202)", "202"), ("Redirect/XD(228)", "228"), ("OFD(302)", "302"),
        ("Entregue(301)", "301"), ("Cancel(104)", "104"), ("Re-slamm(238)", "238"),
        ("Dano(423)", "423"), ("Dano(408)", "408"), ("Dano(416)", "416"),
        ("Dano(432)", "432"), ("Dano(485)", "485"), ("Dano(407)", "407"),
        ("PickupFail-dano(108)", "108"), ("Baixa(259)", "259"),
    ]
    linha = [f"{nome}: {marco(code)}" for nome, code in marcos_def if code in codes]
    linha_do_tempo = " | ".join(linha)

    # diagnostico objetivo (1 linha curta)
    flag_principal = flags[0] if flags else ""
    diagnostico = f"{categoria} @ {local_simples} ({node_base})"
    if flag_principal:
        diagnostico += f" - {flag_principal}"

    # analise curta
    analise = diagnostico

    return {
        "diagnostico": diagnostico,
        "categoria": categoria,
        "local_simples": local_simples,
        "localizacao_atual": localizacao,
        "origem": origem,
        "destino": destino,
        "rota": rota,
        "coleta_103": marco("103") or "NAO",
        "receive_216": n_216,
        "stow_201": n_201,
        "checkin_veiculo_253": n_checkin,
        "checkout_veiculo_254": n_checkout,
        "dispatch_202": "SIM" if has_202 else "NAO",
        "cross_dock_228": "SIM" if has_228 else "NAO",
        "cancelado_104": "SIM" if has_104 else "NAO",
        "reslamm_238": "SIM" if has_238 else "NAO",
        "danificado": "SIM" if danificado else "NAO",
        "cpt_warn_660": n_cpt_warn,
        "cpt_miss_661": n_cpt_miss,
        "ofd_302": "SIM" if has_302 else "NAO",
        "entregue_301": "SIM" if has_301 else "NAO",
        "encerrado_259": "SIM" if encerramento else "NAO",
        "flags": "; ".join(flags),
        "linha_do_tempo": linha_do_tempo,
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
        "danificados": int((resultado["danificado"] == "SIM").sum()),
        "parados_na_fm": int(resultado["localizacao_atual"].str.contains("MILHA DE FM").sum()),
        "outras_milhas": int(resultado["localizacao_atual"].str.contains("OTHER MILE").sum()),
        "entregues": int((resultado["entregue_301"] == "SIM").sum()),
    }

    # tabela dinamica: Categoria (linhas) x Localizacao (colunas)
    try:
        pivot = pd.crosstab(
            resultado["categoria"], resultado["local_simples"],
            margins=True, margins_name="Total",
        )
        resumo["pivot_categoria_local"] = pivot
    except Exception:  # noqa: BLE001
        resumo["pivot_categoria_local"] = None

    return resultado, resumo


def build_pivot(resultado: pd.DataFrame, linhas: str = "categoria", colunas: str = "local_simples") -> pd.DataFrame:
    """Gera uma tabela dinamica (contagem) com quaisquer duas colunas do resultado."""
    return pd.crosstab(resultado[linhas], resultado[colunas], margins=True, margins_name="Total")
