# 📦 FM Event Analyzer — First Mile

Ferramenta que analisa automaticamente arquivos de eventos **ShipTrack** do First Mile (Amazon) e gera um diagnóstico por `tracking_id`: identifica **gap de recebimento, re-slamm, cancelamentos/RTO, cross-dock, CPT miss, pacotes perdidos e órfãos**.

Toda a inteligência de análise (event codes + regras de classificação) vem das análises de ELP8/ESA8.

---

## ✨ O que ela faz

- Lê um export de eventos (**CSV ou Excel**)
- Agrupa por `tracking_id` e ordena por data
- Classifica cada pacote numa categoria:
  | Categoria | O que significa |
  |-----------|-----------------|
  | `RECEBIDO - fluxo normal` | Teve 216 + stow + dispatch |
  | `GAP DE RECEBIMENTO` | Coletado (103) mas **sem** receive (216) — "pulou o Dolphin" |
  | `RE-SLAMM` | Re-etiquetado (238). Flag de "FORÇADO" se reinjetado no SPS |
  | `RECEBIDO porem CANCELADO/RTO` | Recebeu mas depois teve 104 (cancel/RE) |
  | `ORFAO` | Stow/dispatch sem coleta nem receive |
  | `PACOTE PERDIDO / TRAVADO` | Coletado, nunca recebido/estufado, só CPT miss |
- Mostra resumo, gráfico por categoria e tabela detalhada
- Permite **baixar o resultado em Excel**

---

## 🚀 Como rodar (local)

```bash
# 1. clonar o repositorio
git clone https://github.com/<seu-usuario>/fm-event-analyzer.git
cd fm-event-analyzer

# 2. instalar dependencias
pip install -r requirements.txt

# 3. rodar o app
streamlit run app.py
```

Abre no navegador (geralmente `http://localhost:8501`). Suba o arquivo e pronto.

> Teste rápido: use o `sample_events.csv` incluído no repositório.

---

## ☁️ Publicar online (grátis)

1. Suba este repositório no GitHub.
2. Acesse [share.streamlit.io](https://share.streamlit.io), conecte sua conta GitHub.
3. Aponte para `app.py` → deploy. Pronto, link compartilhável.

---

## 📁 Estrutura

```
fm-event-analyzer/
├── app.py                  # interface web (Streamlit)
├── fm_analyzer/
│   ├── __init__.py
│   ├── event_codes.py      # base de conhecimento dos event codes
│   └── analyzer.py         # motor de classificacao
├── sample_events.csv       # dados de exemplo
├── requirements.txt
└── README.md
```

---

## 🧩 Colunas esperadas no arquivo

Detecção flexível (aceita variações de nome). Mínimo obrigatório: `tracking_id` e `status_event`.

`tracking_id, status_event, status, reason, status_node_id, status_date, sender_id, city, state`

---

## 🔧 Usar só o motor (sem interface)

```python
import pandas as pd
from fm_analyzer import analyze_events

df = pd.read_csv("meus_eventos.csv")
resultado, resumo = analyze_events(df)
print(resumo)
resultado.to_excel("analise.xlsx", index=False)
```

---

## ⚠️ Codes a confirmar

Alguns event codes ainda não estão 100% validados (`259`, `414`, `636`, `651`, `699`). Estão marcados como `confirmed=False` em `event_codes.py`. Para confirmar: pegar um tracking com o evento e analisar status + reason + node + timeline.

---

## 📝 Licença / uso

Uso interno First Mile. Não versionar dados reais de pacotes (o `.gitignore` já bloqueia `.xlsx/.csv`, exceto o sample).
