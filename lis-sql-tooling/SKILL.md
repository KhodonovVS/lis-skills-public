---
name: lis-sql-tooling
description: Use when SQL для Oracle/MSSQL/PostgreSQL — sqls, pythia.
---

# SQL/PL-SQL/T-SQL — инструменты для агентов

Установлено на hermes 25.09.2026. Два независимых инструмента: `sqls` (LSP для
SQL: PostgreSQL/MSSQL/MySQL/SQLite/H2/Vertica) и `pythia-plsql` (Oracle PL/SQL:
CLI + Agent Skills).

## sqls — SQL Language Server

- Бинарник: `/home/boss/.hermes/bin/sqls` (v0.2.48, Go, linux-amd64).
  Обновление: GitHub releases `sqls-server/sqls` → `sqls-linux-<ver>.zip` (внутри один бинарник).
- ✅ Конфиг: `~/.config/sqls/config.yml` (600) — живой коннект `talks` (<адрес из окружения>, PostgreSQL 16.15, проверен psql и LSP-хендшейком), закомментированный шаблон для MSSQL. Секция `connections:` —
  список `alias`/`driver`/`dataSourceName` (+ sshConfig). `dataSourceName` приоритетнее
  отдельных полей (user/passwd/host/port/dbName).
  - PG: `dataSourceName: "host=адрес из окружения port=5432 user=USER password=PASS dbname=DB sslmode=disable"`
  - MSSQL: `dataSourceName: "sqlserver://USER:PASS@host:1433?database=DB"`
  - drivers: `postgresql`, `mssql`, `mysql`, `sqlite3`, `h2`
- Режим работы: LSP-сервер по stdio (`sqls` без аргументов).
  Использовать из редакторов (VS Code / code-server CT171) или LSP-клиентов;
  агентам — через клиент/обёртку (прямого CLI-режима нет).
- Для T-SQL есть специализированный форк: `aleTornesi/mssql-lsp` (`tsql-ls`, `go install`).
- Source-first альтернативы БЕЗ коннекта к БД (парсят .sql-файлы каталога):
  `sqllens-language-server` (диалекты tsql/postgres/duckdb/sqlite/mysql/...),
  SaralSQL (T-SQL, понимает .sqlproj/SSDT).

## tsql-ls — T-SQL (MS SQL Server) LSP

- `/home/boss/.hermes/bin/tsql-ls` — форк sqls, специализирован под MSSQL
  (github.com/aleTornesi/mssql-lsp; собран из исходников `go build`; Go 1.26 поставлен `apt install golang-go`).
- Читает тот же `~/.config/sqls/config.yml` (флаг `-config`). LSP-хендшейк проверен.
- MSSQL-коннект: `driver: mssql`, `dataSourceName: "sqlserver://USER:PASS@host:1433?database=DB"`.

## postgres-language-server (supabase)

- `/home/boss/.hermes/bin/postgres-language-server` (v0.25.7) + `/home/boss/.hermes/bin/postgrestools`.
- CLI: `check` / `dblint` / `format` + LSP; диагностика .sql по файлам, без БД.

## sqllens-language-server — мульти-диалектный LSP

- `~/.local/bin/sqllens-language-server` (v0.5.0, npm). Транспорт: `--stdio` (или `--node-ipc`/`--socket`/`--pipe`).
- 10 диалектов: tsql, postgres, duckdb, bigquery, snowflake, redshift, trino, sqlite, mysql, databricks.
  Source-first (парсит файлы без БД), схема опционально подпихивается файлами.

## pythia-plsql — Oracle PL/SQL для AI-агентов

- venv: `/home/boss/.hermes/venvs/pythia/`; CLI: `/home/boss/.hermes/venvs/pythia/bin/pythia`.
  Тонкий режим python-oracledb — Oracle Instant Client НЕ нужен.
- Список команд: `pythia --help` (check/ls/src/args/ddl/cols/grep/sql/invalid/errors/deps/
  impact/similar/plscope/policy/journal/apply/approve/connections/guide/install/...).
- Подключение: `.pythia/connections.json` (ищется вверх от cwd; `--conn NAME`;
  env `PYTHIA_USER`/`PYTHIA_PASSWORD`/`PYTHIA_DSN`; путь файла — `PYTHIA_CONFIG`).
- Запись — ТОЛЬКО через `apply` (snapshot → impact → preview → apply → verify → report),
  нет флага `--write`. Чтение: `sql` — только SELECT/WITH.
- Любой вывод капнут с пометкой усечения (`truncated`) — контекст агента не зальётся.
- `pythia install` — ставит Agent Skills в Claude Code/Codex и др.
  ✅ Выполнено (`-g`): в `~/.claude/skills/` лежат `pythia-apply`…`pythia-write` (10 шт),
  в `~/.claude/settings.json` добавлены хуки (PostToolUse, permissions.deny).

## Питфоллы

- pip на hermes: в `~/.config/pip/pip.conf` стоит `user = true` → установка в venv падает
  с «Can not perform a '--user' install». Обход: `PIP_USER=0 <venv>/bin/pip install ...`.
- Боевые DSN/креды баз спрашивать у BOSS перед подключением; пароли — только pass/Vaultwarden.
- Oracle у BOSS'а — на WORKST (`C:\oracle`, Instant Client).

## Связанные материалы

- Раскатано на агент-контейнеры (CT167/168/169/170/173/212/214): /usr/local/bin + /root/.config/sqls/config.yml; шпаргалка /srv/dev/share/agent-tools/README.md; детали в скилле `agent-helper-fleet` (§ «Инструменты разработки на CT»).
- Демо-проект Delphi: `/home/boss/.hermes/state/delphi-demo` (скилл `delphi-development`).
