"""
Base de conhecimento dos EVENT CODES (ShipTrack) do First Mile.

Cada entrada descreve o evento, o significado operacional e o pilar afetado.
Codigos marcados como confirmed=False ainda precisam de validacao.
"""

EVENT_CODES = {
    "101": {"nome": "Enqueue SPS", "desc": "Pacote entra na fila do SPS (SPSQueue).", "confirmed": True},
    "102": {"nome": "Carrier Update", "desc": "Atualizacao de status enviada pelo carrier (AZLBR/TEXBR).", "confirmed": True},
    "103": {"nome": "Pickup / Coleta", "desc": "DA coletou o pacote no seller.", "confirmed": True},
    "104": {"nome": "Cancelamento / Void", "desc": "Pedido cancelado/void. Reason RE gera RTO (retorno).", "confirmed": True},
    "105": {"nome": "Transfer", "desc": "Movimentacao entre nodes.", "confirmed": True},
    "108": {"nome": "Processamento inicial", "desc": "Evento de fila/processamento inicial.", "confirmed": False},
    "201": {"nome": "Stow", "desc": "Estufagem/separacao do pacote no shuttle (SSP).", "confirmed": True},
    "202": {"nome": "Dispatch / Depart", "desc": "Despacho/saida do container do node.", "confirmed": True},
    "212": {"nome": "Sortation complete", "desc": "Sortimento concluido.", "confirmed": True},
    "216": {"nome": "Receive", "desc": "Recebimento. 1o=DA finaliza no app; 2o=associado bipa no Dolphin. Precisa dos 2.", "confirmed": True},
    "228": {"nome": "Redirect / Cross-dock", "desc": "Redirecionamento (XD). Stow acontece no destino.", "confirmed": True},
    "238": {"nome": "Re-slamm / Re-inducao", "desc": "Re-etiquetagem (sender GMP_TransPETS). Pacote reprocessado.", "confirmed": True},
    "241": {"nome": "Movimentacao (stow)", "desc": "Evento de movimentacao ligado a stow.", "confirmed": False},
    "253": {"nome": "Container arrival", "desc": "Check-in de container no node.", "confirmed": True},
    "254": {"nome": "Container loaded", "desc": "Check-out/carregamento de container.", "confirmed": True},
    "259": {"nome": "Encerramento / baixa", "desc": "Provavel encerramento/baixa por perda (sender TCPS). A confirmar.", "confirmed": False},
    "301": {"nome": "Delivered", "desc": "Entregue ao cliente.", "confirmed": True},
    "302": {"nome": "Out for Delivery", "desc": "Saiu para entrega (OFD).", "confirmed": True},
    "370": {"nome": "Excecao / Hold", "desc": "Pacote em excecao/espera (OI/UN).", "confirmed": False},
    "404": {"nome": "Excecao / reversao", "desc": "Excecao ou reversao de sortimento.", "confirmed": False},
    "414": {"nome": "Ciclo de entrega (a confirmar)", "desc": "Provavel evento de tentativa/chegada. Nao confirmado.", "confirmed": False},
    "416": {"nome": "Tentativa de entrega", "desc": "Tentativa de entrega sem sucesso.", "confirmed": True},
    "503": {"nome": "Label Created", "desc": "Etiqueta/pedido criado. Primeiro evento do ciclo.", "confirmed": True},
    "630": {"nome": "Deviation Alert", "desc": "Alerta de desvio (DeviationAlertsPublisher).", "confirmed": True},
    "631": {"nome": "Deviation Alert 2", "desc": "Alerta de desvio secundario.", "confirmed": False},
    "636": {"nome": "Excecao/hold", "desc": "Evento de excecao intermediario.", "confirmed": False},
    "651": {"nome": "Desvio", "desc": "Alerta de desvio.", "confirmed": False},
    "660": {"nome": "CPT Miss Warning (M2)", "desc": "Risco de perder o CPT.", "confirmed": True},
    "661": {"nome": "CPT Miss Confirmed (M3)", "desc": "Perdeu o CPT.", "confirmed": True},
    "699": {"nome": "Excecao/hold", "desc": "Evento de excecao intermediario.", "confirmed": False},
}


def describe_event(code: str) -> dict:
    """Retorna o dicionario de descricao de um event code (sem o prefixo EVENT_)."""
    code = str(code).replace("EVENT_", "").strip()
    return EVENT_CODES.get(code, {"nome": "Desconhecido", "desc": "Codigo nao mapeado.", "confirmed": False})
