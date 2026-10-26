# Жизненный цикл задачи в OpenProject (проект 7 «b24-tasks»)

## Дерево работ

```
Feature  — задача конторы из Б24 (родитель)
 ├─ Task  kind=research_local     «что уже есть в нашей ЛИС» — ВСЕГДА
 ├─ Task  kind=research_medical   ISFG/PubMed/РФ-документы — только «медицинские по смыслу»
 ├─ Task  kind=research_market    как в аналогичных системах/библиотеках — только медицинские
 ├─ Task  kind=analysis / refactor / feature / verify
 └─ Bug   kind=fix                 найденный дефект — отдельной карточкой, не «попутно»
```

Gate: код-подзадачи не берутся в работу, пока research-подзадачи открыты (если BOSS не снял явно).

## Статусы (цепочка разрешена для типов Task и Bug)

```
1 New → 2 In specification → 3 Specified → 4 Confirmed → 6 Scheduled
     → 7 In progress → 8 Developed → 9 In testing → 10 Tested → 12 Closed
ветки: 9→11 Test failed→7; 13 On hold и 14 Rejected — из любого незакрытого
```

Смысл этапов:
- **In specification** — разбор постановки, research идёт;
- **Specified** — требование проверено, research закрыт, спор снят;
- **Confirmed** — согласовано с BOSS;
- **Scheduled** — декомпозиция готова, подзадачи созданы;
- **Developed** — код готов, собрано (TestBuild 10.3);
- **In testing / Tested** — сверка результата;
- **Closed** — готово (патч ушёл в контору).

## API-факты (проверено 26.10.2026)

- `POST /api/v3/types` → **404**, `GET /api/v3/workflows` → **404**: типы и workflow через REST не создаются и не читаются.
- Типы проекта включаются только в rails: `project.types << Type.find(4)` (Feature), `Type.find(7)` (Bug). После этого `PATCH work_packages/{id}` с `_links.type` даёт 200.
- `lockVersion` в ответе — **int**, не вложенный объект; передавать как есть.
- `PATCH` статуса: `{"lockVersion": N, "_links": {"status": {"href": "/api/v3/statuses/2"}}}`.
- Дети: `_links.children` у родителя; связь задаётся `_links.parent` при создании WP.

## Скрипты

- `/home/boss/.hermes/scripts/lis_decompose.py <WP-id…>` — создаёт дерево (идемпотентно, ищет маркер `kind:…; parent_wp:N` в описании).
- `/home/boss/.hermes/scripts/bitrix_to_openproject.py` — синк Б24 → OP; **в Битрикс ничего не пишет** (пишет только BOSS).

## Правила от BOSS

- Постановщик-медработник может быть некомпетентен методически → медицинская корректность проверяется исследованием, а не принимается на веру.
- При расхождении с постановкой — карточка `kind=dispute` со ссылками; вопрос постановщику задаёт BOSS сам.
- В Битрикс пишет только BOSS; агенты и Hermes — только читают.
- Результаты research — в `viking://resources/lis/research/<Б24-id>`, чтобы не искать заново.
