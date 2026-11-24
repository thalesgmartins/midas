# ADR 001: SQLite com SQLModel + Alembic para uso pessoal

## Status
Aprovado

## Contexto
O Midas é uma ferramenta de uso estritamente pessoal para acompanhamento de carteira, metas e simulação de aportes. Usar PostgreSQL desde o início exigiria subir um serviço separado e gerenciar backups/credenciais sem haver múltiplos usuários ou concorrência pesada.

## Decisão
Adotar **SQLite** como banco padrão (`data/midas.db`), acessado via **SQLModel** e versionado com **Alembic**, mantendo a `DATABASE_URL` configurável por variável de ambiente para eventual migração futura para PostgreSQL sem reescrever os modelos.

## Consequências
- **Positivas:** zero configuração local, backup trivial (copiar um arquivo), testes instantâneos em memória (`sqlite:///:memory:`).
- **Negativas:** sem concorrência pesada de escrita simultânea (irrelevante para uso individual).
