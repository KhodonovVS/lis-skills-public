---
name: lis-db-stands
description: "Use when building database VMs (MSSQL/Oracle/PG)."
version: 1.0.0
author: Hermes Agent (curator)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [mssql, oracle, postgresql, vm, proxmox, qemu, lab, stands]
---

# Стенды СУБД на VM (MSSQL / Oracle / PostgreSQL)

Класс задачи: поднять/обслуживать стендовый или учебный сервер СУБД как QEMU-VM на парке (обычно узел dbase <адрес из окружения>). Раскладка BOSS: СИСТЕМНЫЙ диск — на SATA-пул (ctpool), ДАННЫЕ — отдельным zvol на NVMe-пуле (projects). Стенды нужны и для практики (Oracle осваивается BOSS'ом), поэтому к стенду прилагаются учебные схемы и удобный клиентский доступ.

Строит агент-сисадмин (CT170) прогонами; заказчик ставит ТЗ, принимает по следам (живые пробы портов/запросов), секреты переносит в pass + Vaultwarden сам. Формат ТЗ и серии прогонов — скилл `agent-helper-fleet`.

## Порядок (общий для любого стенда)
1. **Препроверка**: id и IP свободны на ОБОИХ узлах (`pct list`, `qm list`, ping); сторадж данных зарегистрирован (`pvesm status`; при отсутствии — `pvesm add zfspool projects -pool projects`).
2. **VM** (Windows-вариант; Linux — без tpmstate):
   ```bash
   qm create <id> --name <NAME> --ostype win11 --machine pc-q35-10.1 --bios ovmf \
     --cpu x86-64-v2-AES --cores N --sockets 1 --memory M \
     --scsihw virtio-scsi-single --net0 virtio=<MAC>,bridge=vmbr0,firewall=1 \
     --agent 1 --onboot 1
   qm set <id> --efidisk0 ctpool:1,efitype=4m,pre-enrolled-keys=1
   qm set <id> --tpmstate0 ctpool:1,version=v2.0
   qm set <id> --scsi0 ctpool:<GB>,discard=on,iothread=1
   zfs create -V <GB> projects/vm-<id>-data
   qm set <id> --scsi1 projects:vm-<id>-data,discard=on,iothread=1
   ```
   - CPU E5-2650v2 (нет avx2) → тип строго `x86-64-v2-AES`.
   - Диск данных подключать ПОСЛЕ unattended-установки ОС, если answer-файл не задаёт DiskConfiguration: с одним диском интерактивный выбор исключён.
   - zvol'ы c REFRESERV=volsize — место считать как полное.
3. **Снимки по вехам**: `qm snapshot <id> os-installed` → `db-installed` → `final`. Убедиться, что id НЕ в exclude ночного vzdump.
   Сохранение образа по запросу («сохрани образ») — тремя слоями: снапшот с осмысленным именем (`qm snapshot`, работает
   на живой VM) + полный бэкап ФОНОМ (`systemd-run --unit=vzdump-<id> vzdump <id> --storage pbs-main --mode snapshot`) +
   копия исходного установочного ISO на ISOTEMPLATE (см. «Наши носители»).
4. **Секреты** — только файлами на CT агента (0600) + в отчёт имена; заказчик переносит в pass (`stend-<сvc>/*`) и Vaultwarden (организация/«Создано Hermes»; рабочий путь — `bw` CLI: unlock → `bw encode` → `bw create item`, см. `password-vault`). При переносе пайпами сверять `pass show <имя> | wc -c` — пустой stdin у `pass insert -m -f` создаёт ПУСТУЮ запись молча (rc=0), а потом `psql`/`ssh` «зависает» на интерактивном запросе пароля; локальные временные копии секретов удалять после переноса.
5. **Приёмка**: порт СУБД открыт СНАРУЖИ (проба `/dev/tcp` с dbase), живой запрос изнутри (sqlcmd/sqlplus/psql), версия/редакция из SELECT, данные на отдельном томе, автостарт доказан ПЕРЕЗАГРУЗКОЙ VM.

## Наши носители — НЕ качать наугад
- **ISOTEMPLATE** (NFS <адрес из окружения>:/mnt/STORAGE/ISOTEMPLATE): готовый Windows `iso/WinSrv2025_ru-RU_Hermes-VM.iso` (unattend: домен домен организации, virtio, qemu-ga, WinRM/RDP, firewall off), `template/iso/ubuntu-26.04-live-server-amd64.iso`, virtio-win, Win11-образы.
  - PVE листит ISO NFS-стора только из `<path>/template/iso/`; положенное в `<path>/iso/` PVE НЕ видит.
  - Собранные локально ISO (unattend-образы) на pve лежат в `/WINPOOL/iso` (storage WINISO = dir `/WINPOOL/iso`);
    долговечная копия — на ISOTEMPLATE. Копия 8-ГБ идёт минуты: запускать ФОНОМ (`systemd-run --unit=iso-copy cp …`),
    после сверять `stat -c %s` обеих копий + `md5sum` (тоже фоном). Грабли: синхронный ssh-вызов с много-ГБ копией
    рвётся по таймауту инструмента (~7 мин) — всё дольше 2–3 минут запускать юнитом и опрашивать отдельными вызовами.
- **TrueNAS `\\truenas\soft\DEVELOPMENT`** (NFS <адрес из окружения>:/mnt/STORAGE/SOFT; виден с pve как /mnt/truenas/soft): Oracle 19c/21c/26ai — Linux free-EE RPM (без аккаунта!) + zip + Windows-zip, TOAD. SQL Server там нет.
- SQL Server: SSEI-бустрепер по Microsoft fwlink (SQL2025-EntDev); SSMS — прямой `aka.ms/ssmsfullsetup`. Eval Center с серверных IP = 403 — прямые fwlink нормально.
- SQLcl (Oracle): `https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip` (без аккаунта) + java-17-openjdk.
- Oracle Linux ISO — yum.oracle.com (boot-iso ≈1 ГБ достаточно, установка по сети).

## MSSQL-стенд (Windows)
- Готовый Hermes-образ ставится unattended. Старт: bootmgr ждёт «Press any key» — `qm reset` + серия `sendkey spc` через QMP; ход установки смотреть `screendump` + OCR.
- Управление внутри: `qm guest exec <id> --timeout N -- powershell.exe -Command "..."`.
- Тихий setup SQL Server: `/Q /IACCEPTSQLSERVERLICENSETERMS /ACTION=Install /FEATURES=SQLENGINE /INSTANCENAME=MSSQLSERVER /SECURITYMODE=SQL /SAPWD=... /SQLUSERDBDIR=D:\MSSQL\Data ... /SQLTEMPDBFILECOUNT=8 /SQLMAXMEMORY=...`; **/PID НЕ указывать** (Developer предопределён, с PID выйдет Evaluation); лог `...\170\Setup Bootstrap\Log\Summary.txt`.
- **PITFALL**: службы Stopped, старт падает с 17182/17826/17120 — в реестре `...\MSSQL17.MSSQLSERVER\MSSQLServer\SuperSocketNetLib\Tcp\IPAll` пусты TcpPort/TcpDynamicPorts; прописать `TcpPort=1433` (TcpDynamicPorts пусто) → службы поднимаются.
- **PITFALL**: букву D: может занять CD-ROM — `mountvol D: /d`.
- Службы SQL Server 2022+ = Automatic (Delayed Start): после ребута ~2 мин до Running — не паниковать на ранней проверке. GVLK без KMS = «не активирована» — норма лабы.

## Oracle-стенд (Linux)
- Установку OL автоматизировать kickstart'ом (профиль Minimal).
- RPM-путь без аккаунта: `dnf -y install oracle-database-preinstall-19c` → `dnf -y localinstall oracle-database-ee-19c-*.rpm` → пути данных (/u02: oradata+FRA) в `/etc/sysconfig/oracledb_ORCLCDB-19c.conf` ДО `/etc/init.d/oracledb_ORCLCDB-19c configure` → CDB ORCLCDB + PDB ORCLPDB1, listener 1521, EM Express 5500. /u02 — XFS, fstab по UUID, chown oracle:oinstall.
- **PITFALL**: PDB не поднимается после ребута — SAVE STATE для PDB; sysv-скрипт без LSB-заголовка показывает inactive — drop-in `RemainAfterExit=yes`. Автостарт доказывать ДВУМЯ перезагрузками.
- **PITFALL**: снаружи ORA-12154 — добавить tnsnames-запись PDB или EZConnect `host:1521/PDB`.
- Учебная схема: HR (`$ORACLE_HOME/demo/schema/human_resources/hr_main.sql`, employees≈107) — для практики BOSS'а; клиенты sqlplus/sqlcl с LAN; pythia — агент-пользователь через proxy auth (`pythia check` без %ANY%).

## PostgreSQL-стенд (Linux)
- Ubuntu LTS unattended autoinstall (seed-ISO `autoinstall ds=nocloud` + cidata).
- **PITFALL** autoinstall: direct-layout берёт самый большой диск — `match: size smallest`; `username: root` автоинсталлом запрещён — sysadmin-пользователь + root по ключу; UEFI-фаза может обрываться — достройка через chroot.
- Данные: ext4 на zvol → в /var/lib/postgresql (fstab по UUID). PG из репо дистрибутива, PGDG — свежие миноры. Тюнинг 8-ГБ VM: shared_buffers=2GB, effective_cache_size=6GB, work_mem=32MB, random_page_cost=1.1. LAN: `listen_addresses='*'`, pg_hba `host all all <адрес из окружения>/20 scram-sha-256`.

### Загрузка внешнего дампа на стенд

Чужие дампы (.backup/.dump) приходят с неизвестной стороны — версию и состав выяснять ДО рестора:
- **`pg_restore -l <файл>` работает без сервера** и печатает шапку архива: `Dumped from database version` /
  `Dumped by pg_dump version`, формат (CUSTOM/TAR/gzip), схемы, число TOC-записей. Современный pg_restore (18.x)
  читает архивы вплоть до 9.4 (формат 1.12) — сначала листинг, потом решение о площадке и версии.
- **Числа в имени файла — не версия**: дамп «… 16-15.backup» оказался снят в 16:15 с PostgreSQL 9.4.
  Не строить план по имени файла — только по шапке архива.
- Старый дамп (9.4) в современный PG заливается с предсказуемыми ошибками: OIDs, владельцы/ACL несуществующих
  ролей, SET-директивы, расширения. Штатный порядок: свежая пустая БД → заранее создать расширения из шапки
  (hstore, pg_trgm, pgcrypto…, путь к контриб-расширениям зависит от сборки) → pg_restore, при необходимости
  `--no-owner --no-acl`; не ложится в текущую мажорную чисто — отдельный контейнер близкой версии (архивные
  теги postgres на Docker Hub).
- Работать с КОПИЕЙ дампа (оригинал не трогать); копии для скриптов давать имена без пробелов. Входной файл
  ложится на CT исполнителя заранее (см. `paperclip-task-orchestration`: куратор доставляет артефакты).
- **После рестора сверять объекты с шапкой/TOC** (`pg_restore -l`: таблицы, sequences, views, функции, индексы,
  TABLE DATA — числа «N/N» в отчёт). `pg_restore` продолжается после ошибок: «прошёл без падения» — НЕ признак
  успеха, успех подтверждать подсчётами объектов и живыми выборками. И список ошибок ОДНОГО прогона не финален
  в обе стороны: часть отказов снимается повторными/до-применяющими шагами (объект мог встать позже), поэтому
  итог фиксировать фактическим пересчётом объектов в БД (таблицы/индексы/триггеры «N/N»), а не набором ошибок из лога.
- **Ошибки старого дампа**: `schema … does not exist` для объектов схемы, не вошедшей в дамп (типовой случай —
  схема аудита) — НЕ объявлять сразу невосстановимым: (1) если отсутствующий объект стандартный, его канонику
  создают на приёмнике (для аудита — типовой PostgreSQL Audit 91plus: схема `audit` + `audit.logged_actions` +
  `audit.if_modified_func`); (2) определения зависимых объектов, которые ЕСТЬ в дампе (напр. триггеры), до-применяются
  из него выборочно по TOC-ID (`pg_restore -l` → ID строк TRIGGER → `pg_restore -L <список>`). Критерий «надо всё»
  от BOSSа — пустой список невосстановленного; что объективно не снято в дамп — отдельным перечнем с причиной
  (источник запросить у владельца). `must be owner of extension` — косметика (комментарии расширений), применить
  вручную от суперюзера.

## Проверки снаружи (общие)
- Порты: `timeout 3 bash -c 'echo > /dev/tcp/<ip>/<port>'` с dbase.
- **PITFALL**: psql с ПУСТЫМ PGPASSWORD уходит в интерактивный запрос и висит до таймаута (симптом «psql завис»): пароль брать только из проверенного непустого источника (pass-запись сверять `wc -c`), ставить `PGCONNECT_TIMEOUT=8` и внешний `timeout`.

## Развёрнутые стенды парка (поддерживать актуальным)
- **Боевая ЛИС — не стенд**: `<адрес из окружения>`, база `MedicalDB`, пользователь `mgoffice`, **PostgreSQL 9.4.26**.
  Только чтение; пароля в pass НЕТ — реквизиты в конфиге проекта (`DModule.dfm`) или у BOSS.
  SQL писать под 9.4: нет `ON CONFLICT` (9.5+), `SKIP LOCKED`, `GROUPING SETS`/`CUBE`/`ROLLUP`,
  `CREATE INDEX … INCLUDE`, `ADD COLUMN IF NOT EXISTS`; есть `RETURNING`, CTE, окна, `LATERAL`, `FILTER`, `DISTINCT ON`.
  Фичи 18-го стенда на боевой не заработают — проверять на той версии, куда поедет; DDL и опыты — только на стенде <адрес из окружения>.
  Таблица «где что» + правило 9.4 идут в `AGENTS.md` агентам — без этого они пишут SQL «по памяти» и приносят 9.5+-синтаксис.
- MSSQL: VM 120, <адрес из окружения> (WinSrv + SQL Server 2025 EntDev; базы на D: = zvol projects).
- Oracle: VM 129 (ORA19C), <адрес из окружения> (OL8 + 19c EE; HR-схема; EM 5500).
- PostgreSQL: VM 117 (PGSQL) на **dbase** (<адрес из окружения>), <адрес из окружения> (Ubuntu + PG 18; база boss_db). Плюс база `medicaldb` (чужой дамп 9.4, залит полностью: 97 таблиц, 63/63 триггера, аудит 91plus работает; пароль БД — `/root/.secrets/medicaldb-password.txt` на CT220 (claude-dba); ПДн — обращаться по правилам). Роль-логин для этого пароля НЕ зафиксирован — кандидаты `postgres`/`boss`/`lkdaemon`/`medicaldb`, проверять на VM117: `sudo -u postgres psql -tAc "SELECT usename FROM pg_user"`; root-пароль VM — pass `stend-pg/boss`, файлы паролей ролей — `/root/*-password.txt` на VM117.
- Пароли — pass `stend-mssql/*`, `stend-ora/*`, `stend-pg/*` + Vaultwarden «Создано Hermes».
