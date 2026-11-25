# ADR 003: Monitoramento oficial via CVM (IPE) + B3 Fundos.NET com IA opcional

## Status
Aprovado

## Contexto
Acompanhar Fatos Relevantes, Avisos aos Acionistas (proventos) e Relatórios Gerenciais manualmente em portais de terceiros exige scraping frágil e consome tempo. Além disso, depender obrigatoriamente de uma API de IA paga para o monitor funcionar criaria fricção e custo desnecessário para uso pessoal.

## Decisão
- **Ações (CVM Dados Abertos — IPE):** download em memória do ZIP oficial diário (`dados.cvm.gov.br`), filtrando apenas os tickers da carteira e Watchlist em categorias relevantes e deduplicando por `Protocolo_Entrega`.
- **FIIs (B3 Fundos.NET):** consulta JSON direta por CNPJ oficial (`fnet.bmfbovespa.com.br`), capturando Fatos Relevantes, Relatórios Gerenciais, Comunicados e Rendimentos com deduplicação por `FNET-{id}`.
- **Armazenamento enxuto:** os PDFs nunca são salvos em disco; persistem-se apenas os metadados e o link oficial (`document_url`), mantendo o banco SQLite abaixo de 1 MB.
- **Telegram e IA (Gemini) como plugins opcionais:** ativados apenas quando `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` ou `GEMINI_API_KEY` estão presentes no `.env`, com cache permanente do resumo no banco para evitar chamadas duplicadas.

## Consequências
- **Positivas:** zero dependência de scraping HTML, zero custo fixo, footprint de disco mínimo (~20 KB para 70 documentos de FIIs).
- **Negativas:** novos tickers de ações/FIIs fora do dicionário padrão precisam de entrada no mapeamento Ticker ↔ Companhia/CNPJ (extensível futuramente via cadastro automático CVM).
