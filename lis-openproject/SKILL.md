---
name: lis-openproject
description: "Use when работа с OpenProject (<домен из окружения>)."
---

# OpenProject (<домен из окружения>) — ведение проектов BOSS × заказчик

Community Edition 17.x в LXC на pve; снаружи — https://<домен из окружения> (NPM + Let's Encrypt).
Проекты: **MARK MAIN** (разработка голосового управления: задачи/исследования/предложения) и далее другие.

## Доступы и токены

- Аккаунты: `boss`, `заказчик` (оба администраторы), `admin` (встроенный, force-change снят). Пароли: pass `op/openproject/{boss,заказчик,admin}` + Vaultwarden «Создано Hermes».
- **APIv3 НЕ принимает basic-auth с логином/паролем** (даже при включённых токенах) — только `curl -u apikey:<токен>`. В скриптах: `OP_LOGIN=apikey OP_PASSWORD=<токен>`.
- Токены: pass `op/openproject/api-token-{заказчик,boss}` + Vaultwarden; первоисточник для моста — `/root/op-apitokens.txt` на CT170 (chmod 600, строки `login=opapi-...`).
- Создание токена — только rails в контейнере (прямого ssh root→CT174 нет; ходить через PVE: `pct exec 174 -- docker exec openproject bash -lc 'cd /app && bundle exec rails runner "..."'`): `Token::API.create_and_return_value(User.find_by(login: %q{заказчик}))` — печатает значение один раз.
- `api_tokens_enabled` в settings = true по умолчанию; админ-страница: Administration → API and webhooks.

## MCP-мост (управление из Hermes)

- Пакет `openproject-ce-mcp` (uv tool install; бинарь `~/.local/bin/openproject-ce-mcp`; CE, включается 16 тулов по флагам OPENPROJECT_ENABLE_*).
- Регистрация скриптом `/home/boss/.hermes/scripts/op_mcp_setup.sh` (берёт токен, пишет ~/.hermes/config.yaml, тест `hermes mcp test openproject`).
- Env-флаги: OPENPROJECT_BASE_URL, OPENPROJECT_API_TOKEN, OPENPROJECT_ENABLE_* (READ/WRITE по цепочкам; нам: WORK_PACKAGE_R/W, PROJECT_R/W, VERSION/BOARD/MEMBERSHIP_READ, METADATA_TOOLS, PERSONAL_READ).
- Тулы видны как `mcp__openproject__*` (deferred-каталог; проверено в кроне: get_current_user → «заказчик Ops»). После подключения нужен внешний рестарт шлюза, чтобы тулы подхватили рабочие сессии (через сисадмина CT170, гвард запрещает изнутри; цепочка op-mcp-chain).
- `hermes mcp add --env` — ОДНА опция и список пар `KEY=VALUE` (не повторы `--env=`).
- `hermes mcp add` в неинтерактиве спрашивает «Enable all N tools? [Y/n/select]»; без ответа = Cancelled (мост не создаётся) → подавать `printf 'Y\n' |` (учтено в op_mcp_setup.sh).

## API-конвенции

- Создание = POST, обновление = PATCH (`/api/v3/work_packages/{id}`), удаление = DELETE.
- **PATCH требует `lockVersion` целым числом**: GET задачи → `lockVersion.version` (в API это просто `int`) → положить в тело как `"lockVersion": N`. Иначе `409 UpdateConflict`. Тот же приём обязателен при втором PATCH подряд (например, сначала описание, потом вложения → снова правка описания).
- **Исполнитель назначается только участнику проекта**: без membership POST задачи с `_links.assignee` отдаёт `422 PropertyConstraintViolation` («выбранный пользователь не может быть назначен»). Сначала `POST /api/v3/memberships` с `_links: {project, principal, roles[]}` — именно на `/api/v3/memberships`, а не `/api/v3/projects/{id}/memberships` (там 404). Роли: `/api/v3/roles` (3 = Member, 5 = Project admin).
- **Вложения**: `POST /api/v3/work_packages/{id}/attachments` multipart с двумя частями — `metadata` (JSON `{fileName, description:{raw}}`) и `file` (бинарник). В ответе `id`; в описании картинка вставляется как `![имя](/api/v3/attachments/{id}/content)`.
- Проект: `POST /api/v3/projects` {name, identifier}; задачи — POST /api/v3/projects/{id}/work_packages {subject, description{raw}, _links: project/type/status}.
- **Приоритеты — числовые id**: `GET /api/v3/priorities` → 7 Low, 8 Normal, 9 High, 10 Immediate. Ставить в `_links.priority` как `/api/v3/priorities/9`; строковое имя (`high`) даёт 422.
- **Комментарий к задаче** (история изменений): `POST /api/v3/work_packages/{id}/activities` с `{"comment": {"raw": "…"}}`. Это единственный способ вести историю, не перезаписывая описание.
- Типы/статусы резолвить динамически: GET /api/v3/types (1 Task, 4 Feature, 6 User story), /api/v3/statuses (1 New, 2 In specification, 7 In progress, 9 In testing, 12 Closed, 13 On hold, 14 Rejected); «Task».
- **Статус, которого нет в workflow типа, отдаёт `422 PropertyConstraintViolation` («Статус недопустим…»), а не 400.** В дефолтном workflow типа Task принимаются только 1/7/12/13/14 — `2 In specification` и `9 In testing` отбиваются, хотя в справочнике `/api/v3/statuses` они есть. В проекте `b24-tasks` цепочка расширена до полного цикла (1→2→3→4→6→7→8→9→10→12 + ветки 11/13/14 для Task и Bug, см. `references/lifecycle.md`), но в остальных проектах дефолт сохраняется. Перед связыванием внешней системы со статусами прогнать пробу по одному статусу (GET задачи → `lockVersion` → PATCH `_links.status`) и оставить в коде только принятые: иначе первый же апдейт падает и задача молча остаётся в старом статусе.
- **Типы и workflow через REST не создаются**: `POST /api/v3/types` и `GET /api/v3/workflows` отдают **404**. Типы, которых нет в проекте, дают `422 «Тип не задано ни одно из допустимых значений»` при PATCH `_links.type`. Подключать только rails:

  ```ruby
  p = Project.find_by(identifier: "b24-tasks")
  p.types << Type.find(4) unless p.types.exists?(4)   # Feature
  p.types << Type.find(7) unless p.types.exists?(7)   # Bug
  ```

  После этого смена типа идёт обычным PATCH.
- Формат задачи (стандарт BOSS): «📐 Постановка · ✅ Статус · 🧪 Тесты · 🟡 Осталось»; имена — `[область] суть`; в задачах — ссылки на репы/Обсидиан.
- Скрипты: `~/.hermes/scripts/op_markmain.py` (создание проекта+задач, идемпотентно), `op_finalize.sh`, `op_mcp_setup.sh`.

## Почта (SMTP) — параметры в БД, не в ENV

- Настройки лежат в модели `Setting` (`smtp_address`, `smtp_port`, `smtp_domain`, `smtp_authentication`, `smtp_user_name`, `email_delivery_method`), поэтому `ActionMailer::Base.smtp_settings` может показывать `localhost:25` даже при рабочей почте — это не признак «не настроено», оно инициализируется из `Setting` в момент отправки.
- ENV `OPENPROJECT_SMTP__*` (двойное подчёркивание = вложенность) применяется только при СОЗДАНИИ контейнера: после правки `docker-compose.yml` нужен `docker compose up -d --force-recreate`, иначе `docker exec openproject env` покажет ноль SMTP-переменных.
- Единственная честная проверка — реальная отправка: `UserMailer.test_mail(User.find_by(login: %q(boss))).deliver_now` → `SENT-OK`. Перед этим отдельно проверить сам релей изнутри контейнера (`smtplib` + STARTTLS + login на `<адрес из окружения>`), чтобы не искать ошибку не там.

## Вход через Authentik (SSO)

Лицензия проверяется одной командой: `docker exec openproject env | grep OPENPROJECT_EDITION` → `standard`.

- На `standard` (Community) **OpenID Connect — платный аддон**: ENV-переменные `OPENPROJECT_OPENID__CONNECT_*` контейнер принимает (видны в `env`), но `db:seed` не создаёт ни одного провайдера, кнопки на `/login` не появляются, `OpenProject::OpenIDConnect` как модуль отсутствует. Не тратить время на OIDC — идти через LDAP, он в бесплатной версии.
- LDAP Authentik (outpost на `<адрес из окружения>`, LDAPS 6636): базовый DN `dc=организация,dc=home`, bind `cn=ldap-bind,ou=users,dc=организация,dc=home`. Проверка до входа: `ldapsearch -x -H ldap://<адрес из окружения> -D "cn=BOSS,ou=users,dc=организация,dc=home" -w <пароль> -b dc=организация,dc=home "(cn=BOSS)"` → `result: 0 Success` значит пароль и фильтр верные; `ldap_bind: Insufficient access (50)` — неверный bind DN (частая ошибка: подставлять `dc=ldap,dc=goauthentik,dc=io`), при неверном пароле было бы 49.
- Источник в БД: `LdapAuthSource` через rails runner (`name, host, port, account, account_password, base_dn, attr_login: cn, attr_firstname: givenName, attr_lastname: sn, attr_mail: mail, onthefly_register: false`). `onthefly_register: false` — чтобы вход шёл в существующую учётку, а не создавал дубли. Затем привязать: `User.find_by(login: "boss").update_columns(ldap_auth_source_id: <id>)`.

## Профиль пользователя

Имя/фамилия/почта/язык живут в модели `User`: `firstname, lastname, mail, language, admin`. Заполнять только из файла (`docker cp profile.rb openproject:/tmp/ && docker exec openproject bundle exec rails runner /tmp/profile.rb`) — длинный `rails runner "..."` через `pct exec` рвётся на кавычках и падает в трейсбек Ruby.

## Декомпозиция задачи конторы (дерево работ)

Задача, пришедшая из Битрикса, — это не одна работа: внутри неё анализ, правка кривой логики, реализация и проверка. Дерево строится сразу при создании карточки:

```
Feature  — задача конторы (родитель)
 ├─ Task kind=research_local     «что уже есть в нашей ЛИС» — ВСЕГДА
 ├─ Task kind=research_medical   корректность требования: ISFG/PubMed/РФ — только «медицинские по смыслу»
 ├─ Task kind=research_market    как решают аналогичные системы/библиотеки — только медицинские
 ├─ Task kind=analysis / refactor / feature / verify
 └─ Bug  kind=fix                 найденный дефект отдельной карточкой, не «попутно»
```

- **Gate:** код-подзадачи не берутся в работу, пока research открыт. Правило вшивается в текст подзадачи, а не только в голову: карточка реализации должна сама содержать «research не закрыты — задание только на исследование».
- **Идемпотентность:** в описании каждой подзадачи маркер `<!-- kind:<вид>; parent_wp:<id> -->`; перед созданием искать маркер среди `_links.children` родителя. Повторный прогон не должен плодить дубли.
- **Медицинская по смыслу** — определяется по ключевым словам (днк, родств, сиблинг, бланк, заключение, экспертиза, str, локус, аллель, генотип, пробанд, образец). Не угадывать по названию задачи.
- **Проверяемый критерий приёмки обязателен.** «Разобраться» — не критерий; «файлы и номера строк, где зашито ограничение» — критерий.
- Скрипты: `~/.hermes/scripts/lis_decompose.py <WP-id…>` (дерево), `lis_tasks_spec.py` (переписать описания подзадач в формат задания), `wp_to_card.py <WP-id…>` (карточка агенту → `/home/boss/work/lis-cards/`).
- Формат карточки агенту: роль → контекст родителя (что за заказ, примеры) → обоснование из закрытых research (подставляется автоматически, у закрытых берётся раздел «Заключение/Вывод») → задание → критерий приёмки → границы (что нельзя трогать/запускать).
- В Битрикс пишем **только читаем**: источник истины — Б24, пишет туда BOSS. Расхождение с постановкой оформляется карточкой `dispute` со ссылками, вопрос постановщику задаёт BOSS.

Полная матрица статусов, смысл этапов и API-факты — `references/lifecycle.md`.

## Конвейер «Битрикс24 → техпроект в OpenProject»

- Движок: `~/.hermes/scripts/bitrix_to_openproject.py` (состояние `~/.hermes/state/bitrix_to_op.json`, проект `b24-tasks`).
- Расписание и ручной запуск через n8n или cron дергают HTTP-хук `~/.hermes/scripts/b24_op_hook.py` (systemd `b24-op-hook`, порт 8099, секрет `~/.hermes/secrets/b24_op_secret`): `GET /check` (что изменилось) и `POST /run?mode=incremental|all-open`.
- Хук живёт на хосте Hermes (там pass и bw), n8n в другом контейнере — стучаться только по адресу, который реально виден из CT n8n (`<адрес из окружения>`), остальные интерфейсы хоста из VLAN LAN закрыты.
- Эндпоинты хука: `GET /check?secret=`, `POST /run?secret=&task=<id>|mode=all-open`, `GET /rebuild?task=<id>` — последний служит кнопкой «Пересобрать техпроект» из карточки (секрета нет, пускает только loopback и 10/8, 192.168/16).
- Расписание в n8n: workflow `Bitrix24 → OpenProject: наблюдатель`, две cron-ветки `0 9,12,15,18 * * 1-5` и `30 10,13,16 * * 1-5` (пн–пт, 09:00–18:00 MSK, раз в 1,5 ч), таймзона `Europe/Moscow`. Ночью и в выходные не проверяет — не добавлять туда круглосуточные триггеры.
- Дайджест: `~/.hermes/scripts/b24_digest.py`, cron 09:05 пн–пт, шлёт в @организацияHomeBOT (`chat_id` 219004331).
- Поиск по чатам и дедуп: `~/.hermes/scripts/b24_index_chats.py` → Qdrant `b24_chats` (1024, Cosine), эмбеддинги `text-embedding-3-small` (`<адрес из окружения>/v1/embeddings`; модель `bge-m3` там НЕ живёт). Перед созданием новой задачи движок ищет похожие с порогом 0.93 и ставит ссылку «похожая задача #…».
- RAW и OCR: `/home/boss/bitrix-raw/<task>/` (`task.json`, `chat.txt`, `ocr.txt`), tesseract `rus+eng` для картинок и `pdftotext` для PDF — текст уточнений из вложений идёт в промпт, не игнорируется.
- Ветка задачи в Forgejo создаётся до разбора (`b24/<id>-<slug>`), репозиторий выбирается по ключевым словам (ehlib, graphics32, devexpress, fastreport, ems → соответствующие, иначе `MedicalGenomics/medicalgenomics`); слаг обрезать с `rstrip('-')`.
- **Статус синхронизируется в обе стороны по маппингу** Битрикс→OP: 1 новый → 1 New, 2 ждёт выполнения → 1, 3 выполняется → 7 In progress, 4 ждёт контроля → 7, 5 завершена → 12 Closed, 6 отложена → 13 On hold, 7 отклонена → 14 Rejected (см. ограничение workflow выше — 2 и 9 не использовать). Для закрытых задач не пересобирать техпроект и не создавать ветку: только PATCH статуса (отдельный метод `set_status` с `lockVersion`), и брать их в выборку лишь если они уже есть в state — иначе синхронизация заведёт WP на весь архив конторы.
- В описании задачи ссылку на репозиторий строить от константы `GIT_BASE`; в тексте она не должна вести в чужую организацию (типовая ошибка — оставить дефолт вида `.../agents`, и тогда ветка в карточке ведёт в никуда).
- Структура описания и правила промпта — `references/bitrix-pipeline.md`.

## Мобильное приложение

- OpenProject Mobile (бета; iOS 17+/Android 12+): требует OP ≥17.0, валидный HTTPS, включённые built-in OAuth applications (Administration → OAuth applications) + API — всё предусмотрено в установке.

## Питфоллы

- **«Ваша учётная запись не была активирована»**: `self_registration=2` (активация вручную админом). BOSS в такой ситуации почти всегда сам зарегистрировал ДУБЛЬ (типично с несуществующим адресом `boss@<домен из окружения>`) вместо входа в свою учётку `boss`. Действия: удалить дубль (`User.find_by(login: %q{...}).destroy`), проверить пару основной учётки `User.try_to_login` (пароль в rails runner передавать через `Base64.decode64(%q{...})` — иначе воюют кавычки), направить BOSS'а в Vaultwarden: организация организация → «op — openproject — boss».
- Секреты не печатать; креды генерирует сисадмин, заказчик кладёт в pass+Vaultwarden (secret_to_bw.sh) и удаляет исходный файл.
- Пароли могут содержать «/»: креды-файлы парсить только по пробелам (`awk '{print $1}'` / `'{print $NF}'`); проверка пары — `User.try_to_login`. (op_finalize.sh раньше резал пароль по «/» — исправлено.)
- op_finalize.sh идемпотентен: если файла кредов на CT170 уже нет, а pass `op/openproject/` заполнен — шаг 3 мягко пропускается («забраны ранее»), дальше идут проверки MARK MAIN/токенов/внешняя. Повторный прогон даёт «создано 0, пропущено 33» и FINALIZE: DONE.
- API-списки work_packages (проектный и глобальный) по умолчанию НЕ отдают Closed — полный счёт смотреть по БД, GET /work_packages/{id} или доп. фильтром `filters=[{"status":{"operator":"c","values":[]}}]` (URL-encoded). Любой дедуп/повторный прогон обязан учитывать Closed, иначе дублирует закрытые задачи (op_markmain.py исправлен: тянет и закрытые). Даты API (createdAt) — UTC (MSK = +3).
- Внешняя проверка доступности — check-host.net API (check-http); локальный curl к <домен из окружения> работает; r.jina.ai для .ru бывает 451.
- Серт/прокси: рецепты — skill nginx-proxy-manager (meta у certificates — ПУСТАЯ).
