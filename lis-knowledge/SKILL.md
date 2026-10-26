---
name: lis-knowledge
description: "Use when ищешь, как это уже решали в проекте ЛИС: код по смыслу (Qdrant) и прошлые решения (OpenViking)."
---

# База знаний: `kb` (Qdrant + OpenViking)

Перед проектированием и перед кодом — 1–2 запроса. Не изобретать заново.

```
kb code "как считается заключение TConclCalculator"   # поиск по коду проекта (pas/dfm/sql)
kb dfm  "MG.Concl.Form"                               # только формы
kb sql  "insert в ConclResult"                        # только SQL
kb memory "как решали сборку MGSystem"                # OpenViking: прошлые решения
kb stats                                              # какие коллекции есть
```

Ключи CLI читает сам из `/opt/work/secrets/env.sh`.

## Что где лежит

| Хранилище | Что внутри |
|---|---|
| Qdrant `lis_code_1024` | код ЛИС, 42 505 точек, эмбеддинги `embed-bge-m3` (<адрес из окружения>) |
| Qdrant `delphi_memory_1024`, `oracle_memory_1024`, `b24_chats` | отдельные коллекции по темам |
| OpenViking `<адрес из окружения>` | факты, решения, события проекта |

## Требования

1. В отчёте — что нашёл (файл + фрагмент) и что из этого использовал.
2. Нашёл конфликт со своим решением — зафиксировать в карточке, а не молча писать код.
3. MCP OpenViking требует `Accept: application/json, text/event-stream` (иначе 406). Если `kb memory`
   вернул ошибку — привести её текст, а не «нет доступа».
