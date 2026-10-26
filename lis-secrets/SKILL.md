---
name: lis-secrets
description: "Use when storing/retrieving passwords — pass + Vaultwarden BOSS."
version: 1.0.0
author: VLAS
platforms: [linux]
metadata:
  hermes:
    tags: [passwords, secrets, pass, gpg, vault]
---

# Password Vault (pass)

Личное хранилище паролей агента. Все секреты (пароли, токены, ключи) хранить ТОЛЬКО здесь —
не в памяти, не в skills, не в plaintext-файлах.

## Доступ

- Хранилище: `~/.password-store/` (pass; каждая запись — отдельный GPG-файл).
- GPG-ключ: `VLAS <vlas@local>`, fingerprint `158E5B224EFF0D0F210ABB29D32B80C4CA232768`.
- Мастер-пароль (GPG-passphrase) = пароль учётки **VLAS**, его держит BOSS в Kaspersky
  Password Manager («VLAS Пароль для хранилища паролей учеток»). Так сделано намеренно:
  у BOSS есть доступ/контроль над хранилищем.
- Фраза для автономной работы: `~/.hermes/.gpg-passphrase` (права 600).
- Резерв секретного ключа: `~/.hermes/.gpg-secret-vlas.asc` (защищён тем же мастер-паролем).

## Команды

```bash
pass ls                                                    # список записей
pass show '<имя>'                                          # прочитать
printf '%s\n' '<пароль>' | pass insert -m '<имя>'           # сохранить
printf '%s\n%s\n' '<пароль>' 'login: <логин>' | pass insert -m '<имя>'  # с логином
pass rm -f '<имя>'                                          # удалить
pass mv '<старое>' '<новое>'                                # переименовать
```

## Правила

1. Пароль/секрет клади в pass, а в ответе/памяти пиши только «сохранено в pass: <имя>» —
   значение НЕ воспроизводить.
2. Значение секрета НИКОГДА не писать в memory-инструмент, skill-файл или plaintext
   (кроме `~/.hermes/.gpg-passphrase`).
3. Учётку от BOSS (из Kaspersky) сохраняй под понятным именем (приложение/сервис),
   логин отдельной строкой `login:`.
4. Имя записи — латиница/ASCII, без пробелов (path-безопасно).

## Учётные записи VLAS (конвенция BOSS)

VLAS работает под СВОЕЙ учёткой на каждом устройстве/сервисе/программе — чтобы в логах/аудите
было видно, кто что сделал (VLAS vs BOSS). Логин — константа **VLAS**.

Порядок при подключении к сервису:
1. Учётка VLAS есть → работать под ней.
2. Учётки нет → создать: зайти под учёткой BOSS (если есть доступ), создать пользователя
   `VLAS`, пароль — уникальный на сервис, сгенерировать по требованиям сервиса
   (`openssl rand -base64 24`), роль — admin/root/sudo.
3. Сохранить пароль в pass:
   `printf '%s\n%s\n' '<пароль>' 'login: VLAS' | pass insert -m '<сервис>'`
4. Рутинные операции под учёткой BOSS не выполнять, если есть учётка VLAS.

## Второе хранилище: Vaultwarden/Bitwarden (<домен из окружения>) — с 18.09.2026

- Сервер свой: **Vaultwarden 2026.6.0 в CT164** (<адрес из окружения>, docker, 8080→80), публично `https://<домен из окружения>`.
  Учётка агента: **vlas@teremokhome.ru**, мастер-пароль в pass → `vaultwarden/vlas` (2-я строка `login:`).
  Содержимое: папка `pass-migration` (**63 записи, зеркало pass**) + элемент `hermes-env` (10 кастомных полей = env-переменные).
- **CLI: `bw` (@bitwarden/cli) ТОЛЬКО 2025.4.0** (`~/.hermes/node/bin/bw`, ставить `npm i -g @bitwarden/cli@2025.4.0`).
  Свежие версии (проверено на 2026.9.0) с нашим сервером/аккаунтом НЕ работают: логин даёт `KeyIdBackfillError`,
  разблокировка — «The provided key is not the expected type». Не обновлять без живой проверки логина.
- Быстрый доступ: `~/.hermes/scripts/bw_get.sh <элемент> [password|username|notes|json|custom:ИМЯ_ПОЛЯ]`
  и `~/.hermes/scripts/bw_find.sh <строка>` — сами переподнимают сессию через pass и держат её в
  `~/.hermes/.bw_session` (600). Сессия живёт, пока хранилище не залокалось; при отказе хелпер переразблокирует сам.
- Плагин Hermes **`vaultwarden`** (community, hansipie/hermes-vaultwarden) стоит в `~/.hermes/plugins/vaultwarden`,
  включён в `plugins.enabled`; конфиг `secrets.vaultwarden` = {enabled, item_name: hermes-env, session_env: BW_SESSION,
  override_existing: **false**} (при false значения из .env приоритетнее — плагин только закрывает пробелы).
  Сканер при установке блокирует плагин как community/caution; установлен с `--force` ПОСЛЕ чтения кода
  (сетевых вызовов нет, только `bw` через subprocess, пишет BW_SESSION в .env — как заявлено в README).
  Плагин подхватывают процессы, стартовавшие ПОСЛЕ рестарта гейтвея; иначе `hermes vaultwarden status|sync`.

### Аккаунт hermes.bw2 (19.09.2026, для штатного пути)

- `hermes.bw2@teremokhome.ru` создан РЕГИСТРАЦИЕЙ В ВЕБ-КЛИЕНТЕ (правильные ключи, в админке виден).
  Мастер-пароль — `pass vaultwarden/bw2` + локальный сейф Hermes (origin `https://<домен из окружения>`).
- CLI: новый аккаунт проверен на бинаре 2024.9.0 (`~/.local/bin/bw`): login+sync OK. **2026.9.0 с нашим
  Vaultwarden не работает** (`KeyIdBackfillError` — у Vaultwarden нет нужного endpoint'а; воспроизведено
  и на новом аккаунте — это связка клиент↔сервер, не аккаунт).
- **Окно `vault.save_login` в панели/TUI не поддерживается** — его умеют только десктоп-приложение и
  классический CLI; панель такие запросы отклоняет автоматически (-32601, fail fast).
- **`browser_vault_fill` в нашей сборке смотрит не в тот браузер** (CDP-супервизор — headless Chrome,
  страницы — camoufox): штатное заполнение форм сейфом не работает, пока не починят связку.

### АКТУАЛЬНАЯ связка CLI (19.09.2026) — читать до любой работы с bw

- **Сервер свежий**: Vaultwarden `docker image` = `vaultwarden/server:latest` → **1.37.3** (релиз 13.09.2026) в CT164. «Старый» тут именно **CLI**, а не сервер.
- **Рабочий бинарь: `~/.local/bin/bw` версии 2025.4.0.** Бинарь `~/.hermes/node/bin/bw` оказался 2026.9.0 — с ним вход/разблокировка падают («The decryption operation failed», KeyIdBackfillError). Проверять `bw --version` ПЕРЕД диагностикой.
- **Рабочий аккаунт: `hermes.bw2@teremokhome.ru`**, мастер-пароль — `pass vaultwarden/bw2` (32 симв.). В `~/.config/Bitwarden CLI` мог остаться старый логин `hermes.bw@…` (его пароль в pass не подходит) — тогда `bw logout` и `bw login hermes.bw2@teremokhome.ru "$(pass show vaultwarden/bw2|head -n1)" --raw`.
- **Питфолл npm**: `npm install -g` в этой системе ставит в `~/.local` (prefix=`/home/boss/.local`), а НЕ в `~/.hermes/node`; чтобы положить пакет в `~/.hermes/node`, нужен `npm install --prefix ~/.hermes/node …`. npm 12 к тому же блокирует install-скрипты (argon2) и `--allow-scripts` запрещён для project-scoped установок — поэтому рабочая копия живёт в `~/.local`.
- **Обёртки** `~/.hermes/scripts/{bw_get.sh,secret_to_bw.sh}` переведены на `~/.local/bin/bw` + `pass vaultwarden/bw2` и сами делают `login`, если статус `unauthenticated`.
- **Проверять успех по формату, не по длине**: `bw unlock --raw` при успехе отдаёт сессию ~88 символов base64; текст ошибки тоже длинный (61+ симв.) — старый скрипт принимал его за успех. Считать успехом только строку, проходящую `^[A-Za-z0-9+/=]{40,}$` (или пустой stderr + рабочий `bw list items`).
- Признак, что всё в порядке: `bw sync` → «Syncing complete», `bw list items` → число элементов.

### Созданные пароли — в Vaultwarden BOSS (правило BOSS, 18.09.2026)

**Рабочий путь для одного секрета (проверено 20.09.2026):**
`~/.hermes/scripts/bw_put_key.py <pass-запись> "<имя элемента>" "<логин>" "<заметки>"` —
поднимает сессию через `pass vaultwarden/bw2`, кладёт элемент в коллекцию «Создано Hermes»
(организация TEREMOK), проверяет чтением; `--check` показывает состояние двух последних записей.
Грабли (растяжка без Extract, плоский POST, INSERT в `ciphers_collections`) — в скилле `credential-delivery`.

**Каждый пароль/учётку, который я создаю для BOSS, кладу в два места:** в `pass` (рабочая копия агента)
и в его Vaultwarden. Один вызов:

```bash
# пароль из stdin (не светится в истории команд), папка по умолчанию «Создано Hermes»
printf '%s' '<пароль>' | ~/.hermes/scripts/secret_to_bw.sh '<Имя>' '<логин>' - '<https://url>' '<заметки>'
```

- Скрипт сам поднимает сессию через `pass vaultwarden/vlas`, создаёт папку, если её нет, и либо создаёт
  элемент, либо ОБНОВЛЯЕТ одноимённый (идемпотентно — повторный запуск не плодит дубли).
- **Бытрый путь через `bw` CLI (работает всегда):** если `secret_to_bw.sh`/`bitwarden.py add` отвечает «в аккаунте нет организации» — не искать причину, а создать элемент штатным CLI: `bw list organizations` → `bw list collections --organizationid <org>` → собрать JSON `{organizationId, collectionIds, type:1, name, notes, login:{username,password,uris:[{uri}]}}` → `bw encode` → `bw create item` (JSON подавать в stdin через encode-вывод). Проверка — ответ `create rc: 0` с id и organizationId.
- Питфолл: в шаблоне нового элемента `login` = `null`, поэтому ставить не `setdefault('login', …)`,
  а `if not item.get('login'): item['login'] = {}` — иначе `TypeError: 'NoneType' object does not support
  item assignment` (уже исправлено в скрипте).
- Проверка после записи: `bw list items --search '<Имя>'` → у элемента должны быть логин, пароль (длина > 0)
  и uri. Только после этого говорить BOSS «сохранено».
- Учётку админа сервиса (VLAS) обычно не надо путать с учёткой BOSS — в Vaultwarden делаем отдельную запись
  с его логином, а про VLAS-админа пишем в notes.

### Регистрация учётки в Vaultwarden программно (клиенты Bitwarden не умеют register)

`bw`/`rbw` учётку не создают; делается POST-ом на `/identity/accounts/register` (скрипт `~/bw_register_api.py`).
Грабли, которые стоили двух заходов:
- Скрипты настройки/переноса — в `~/.hermes/scripts/vaultwarden/`: `bw_register_api.py` (регистрация учётки),
  `bw_fix2.py` (перевыпуск ключа, режимы password|keys), `bw_migrate.py` + `bw_migrate2.py` (перенос pass → Vaultwarden),
  `bw_create_env_item.py` (элемент `hermes-env`), `fix_pass_symmetric.sh` (починка симметричных записей pass).

- **stretched key = HKDF-Expand (prk = masterKey), БЕЗ Extract.** `cryptography.HKDF(salt=..., info=...)` делает
  Extract и даёт неверный ключ → клиент не может расшифровать user key («The decryption operation failed»),
  хотя логин проходит. Считать так: `HMAC-SHA256(masterKey, info + 0x01)` (info = b"enc"/b"mac"), 32 байта каждый.
- `/identity/connect/token` принимает **форму** (`application/x-www-form-urlencoded`), JSON → 415.
- Смена/перевыпуск ключа: **POST** `/api/accounts/password` (PUT → 404; пустое тело → 422). Тело
  `{masterPasswordHash, newMasterPasswordHash, key, kdf: 0, kdfIterations: 600000}`.
- **Восстановление user key без потери аккаунта:** логин по мастер-паролю → в ответе поле `Key`
  (user key, зашифрованный текущим stretched key) → расшифровать → перешифровать верным ключом → POST выше.
  Так починили сломанную регистрацию, не удаляя учётку (свежесть проверять `bw login` + `bw list items`).
- Мастер-пароль **не вводить через `rbw register`/`script`** — псевдо-tty эхоит ввод в вывод (пароль попадает в лог сессии).
  Либо API-скриптом (пароль из pass через pipe), либо менять его после.

## Питфоллы

- **Запись в pass может быть зашифрована СИММЕТРИЧНО (парольной фразой), а не на GPG-ключ** — тогда `pass show`
  падает `gpg: decryption failed: Bad session`, а `gpg --list-packets <файл>` показывает `encrypted with 1 passphrase`
  (у нормальной записи — `pubkey enc packet ... keyid`). Проверять до массовых операций: такие записи не читаются
  ни pass, ни миграцией. Лечение (пароль — тот же мастер-пароль из `~/.hermes/.gpg-passphrase`):
  `gpg --batch --pinentry-mode loopback --passphrase-file ~/.hermes/.gpg-passphrase -d <файл>` → `pass insert -m -f <имя>`
  (готовый скрипт `~/fix_pass_symmetric.sh`); после — `pass show <имя>` обязан работать.

- **`pass insert -f` (однострочный, без `-m`) в неинтерактивном режиме молча падает** (rc=1, без вывода, запись не создаётся). Использовать только `pass insert -m -f` через pipe и ПРОВЕРЯТЬ rc + `pass show` после записи. Проверено 17.09.2026.
- После рестарта gpg-agent/перезагрузки `pass` может запросить пин. Лечится preset'ом
  всех keygrip'ов:
  ```bash
  for KG in $(gpg --list-secret-keys --with-keygrip --with-colons | awk -F: '/^grp/{print $10}'); do
    printf '%s' "$(cat ~/.hermes/.gpg-passphrase)" | /usr/lib/gnupg2/gpg-preset-passphrase --preset "$KG"
  done
  ```
- Файл `~/.hermes/.gpg-passphrase` держать 600.
- Смена мастер-пароля: НЕ `gpg --passwd` в batch (падает «can't get input»). Пересоздать
  ключ `--quick-generate-key` с новой фразой + `--quick-add-key <fp> rsa4096 encr never`,
  затем `pass init <fp>` и пересохранить записи.
