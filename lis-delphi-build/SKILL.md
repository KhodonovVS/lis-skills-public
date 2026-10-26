---
name: lis-delphi-build
description: "Use when работа с Delphi/RAD Studio: код, сборка, кодировки, агенты."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [delphi, rad-studio, object-pascal, dcc32, msbuild, lsp, coding-agents]
---

# Delphi Development

Работа с Delphi-проектами: кодировки, формат файлов, структура проектов,
Win32 API (shared memory, синхронизация), редактирование, типовые ошибки.

## When to Use

- Правишь/читаешь `.pas`/`.dfm`, нужно не испортить кодировку и восстановить после порчи.
- Надо собрать проект из командной строки (`dcc32`, `msbuild`, `rsvars`) и разобрать ошибки компилятора.
- Настраиваешь Codex / Claude Code на Delphi-задачу (LSP + сборка в MCP) — см. `references/agent-driven-delphi.md`.
- Нужен разбор ошибок времени выполнения и внешних DLL (pdfium, libpq).

## Файлы и кодировки

Правило кодировки зависит от версии Delphi:

| Версия Delphi | Кодировка файлов | Особенности |
|---------------|------------------|-------------|
| **7–2007** (ANSI) | **cp1251 (Windows-1251)** | String = AnsiString; UTF-8 ломает русские символы |
| **XE2+ / 10.x+ / 11.x / 12.x** (Unicode) | **UTF-8 (предпочтительно) или cp1251** | String = UnicodeString; Delphi читает BOM и без BOM |
| | | |

### Legacy Delphi (7–2007) — только cp1251

Сохранение в UTF-8 ломает:
- Русские символы в строковых литералах (превращаются в `?`)
- Комментарии на русском языке
- Сообщения об ошибках и пользовательский интерфейс

### Modern Delphi (XE2+)

UTF-8 без BOM работает корректно. Delphi XE2+ определяет кодировку автоматически
по содержимому. Для проектов без кириллицы в коде можно смело использовать UTF-8.
DFM-файлы хранят локальные строки в #-нотации (см. ниже) — они не зависят от
кодировки файла.

### Формат DFM: #-нотация

DFM-файлы Delphi хранят русские/unicode символы как **Unicode codepoint в десятичной #-нотации**:

```
Caption = #1055#1086#1088#1090#1092#1077#1083#1100' '#1079#1072#1082#1072#1079#1086#1072
```

Это бинарно-безопасный формат, независимый от кодировки файла. SQL-комментарии
и другие строковые литералы внутри DFM могут содержать прямой текст.

## Структура проекта

Рекомендуемая организация Delphi-проекта (особенно многомодульного):

```
ProjectRoot/
├── Common/             — общие модули (протоколы, утилиты, логгеры)
│   ├── ProtocolDefs.pas
│   ├── SharedMemoryManager.pas
│   └── Logger.pas
├── Server/             — серверное приложение
│   ├── ServerApp.dpr
│   ├── ServerForm.pas + .dfm
│   └── WorkerThread.pas
├── Client/             — клиентское приложение
│   ├── ClientApp.dpr
│   ├── ClientForm.pas + .dfm
│   └── FileTransferThread.pas
├── Tests/              — юнит-тесты (DUnit)
│   ├── TestRunner.dpr
│   ├── TestProtocolDefs.pas
│   └── TestSharedMemory.pas
├── client.ini          — конфигурация
└── README.md
```

Принципы:
- **Common/** — модули без формы, переиспользуемые между проектами
- **Server/, Client/** — по одному .dpr на точку входа
- **Tests/** — отдельный проект-раннер, ссылается на модули через `..\Common\`
- Пути в .dpr указывать относительно: `in '..\Common\Logger.pas'`

## Win32 API patterns

### Shared Memory (File Mapping)

```pascal
uses Winapi.Windows;

const
  SHMEM_NAME = '{GUID}';
  SHMEM_SIZE = 256 * 1024;  // 256 КБ

var
  MappingHandle: THandle;
  BufferPtr: PByte;

// Сервер: создаёт
MappingHandle := CreateFileMapping(
  INVALID_HANDLE_VALUE, nil, PAGE_READWRITE,
  0, SHMEM_SIZE, PChar(SHMEM_NAME));

// Клиент: открывает
MappingHandle := OpenFileMapping(
  FILE_MAP_ALL_ACCESS, False, PChar(SHMEM_NAME));

// Маппинг в адресное пространство
BufferPtr := MapViewOfFile(
  MappingHandle, FILE_MAP_ALL_ACCESS, 0, 0, SHMEM_SIZE);

// Освобождение
UnmapViewOfFile(BufferPtr);
CloseHandle(MappingHandle);
```

### Синхронизация (Mutex + Events)

```pascal
// Mutex — эксклюзивный доступ к shared memory
FMutexHandle := CreateMutex(nil, False, PChar('Global\SM_GUID_Mutex'));

// Auto-reset events — сигнализация
FEventServer := CreateEvent(nil, False, False, PChar('Global\SM_GUID_EventServer'));
FEventClient := CreateEvent(nil, False, False, PChar('Global\SM_GUID_EventClient'));

// Client → Server: записать данные в SHM, сигналить серверу
WaitForSingleObject(FMutexHandle, Timeout);
try
  Move(Data, BufferPtr^, DataSize);
  SetEvent(FEventServer);        // сигнал серверу
  WaitForSingleObject(FEventClient, Timeout);  // ждать ответа
finally
  ReleaseMutex(FMutexHandle);
end;

// Server: ждать сигнала, прочитать, ответить
WaitForSingleObject(FEventServer, Timeout);
WaitForSingleObject(FMutexHandle, Timeout);
try
  Move(BufferPtr^, Dest, DataSize);
finally
  SetEvent(FEventClient);       // сигнал клиенту: данные прочитаны
  ReleaseMutex(FMutexHandle);
end;
```

Важно:
- Префикс `Global\` для cross-session доступа (терминальные серверы)
- Always `CloseHandle` в обратном порядке создания
- Auto-reset event (False) — сигнал гасится после одного WaitForSingleObject

## Shared Memory IPC — протокол

Типовой протокол передачи данных через shared memory (256 КБ):

```
[Header: 64 байта] + [Data: до 262,080 байт]

TPacketHeader = packed record
  Command     : Integer;    // команда
  ClientID    : Integer;    // ID клиента
  PacketSize  : Integer;    // размер данных в этом пакете
  SequenceNo  : Integer;    // порядковый номер
  TotalSize   : Int64;      // полный размер (для файлов)
  ChunkOffset : Int64;      // смещение чанка
  CRC32       : Cardinal;   // CRC данных
  Flags       : Integer;    // флаги (FLAG_FIRST/LAST/RETRY/COMPRESSED)
  StatusCode  : Integer;    // код ошибки
end;
```

Команды протокола:
- Heartbeat (0), Connect (1), Disconnect (3)
- StartFile (4), Data (5), EndFile (6)
- Ack (7), Nak (8), Error (9), Abort (10)

### CRC32 для верификации данных

```pascal
function CalculateCRC32(const Buffer; Size: Integer): Cardinal;
const
  CRC32Table: array [0..255] of Cardinal = ( ... );
var
  I: Integer;
  P: PByte;
begin
  Result := $FFFFFFFF;
  P := @Buffer;
  for I := 0 to Size - 1 do
  begin
    Result := CRC32Table[(Result xor P^) and $FF] xor (Result shr 8);
    Inc(P);
  end;
  Result := not Result;
end;
```

## Unit-тестирование (DUnit)

DUnit поставляется с Delphi (GUI и Console runner).

```pascal
unit TestMyUnit;

interface
uses TestFramework;

type
  TTestMyUnit = class(TTestCase)
  published
    procedure TestSomething;
  end;

implementation

procedure TTestMyUnit.TestSomething;
begin
  CheckEquals(42, GetAnswer(), 'Meaning of life');
  CheckTrue(IsValid, 'Should be valid');
  CheckFalse(IsEmpty, 'Should not be empty');
end;

initialization
  RegisterTest(TTestMyUnit.Suite);
end.
```

TestRunner.dpr:
```pascal
program TestRunner;
uses
  TestFramework,
  GUIRunner,  // или TextRunner для консоли
  TestMyUnit in 'TestMyUnit.pas';
begin
  GUIRunner.RunRegisteredTests;
end.
```

Правила:
- `SetUp`/`TearDown` для подготовки/очистки
- Threaded тесты: CreateThread + WaitForSingleObject
- Для тестов SHM: сервер создаёт память, клиент открывает, обмен в отдельных потоках

## Кодировка: всё новое — UTF-8 с BOM (требование BOSS, 26.10.2026)

| Файлы | Кодировка |
|---|---|
| `.pas`, `.dpr`, `.dpk`, `.inc` | **UTF-8 с BOM** (без BOM Delphi читает как ANSI → кракозябры) |
| `.dfm`, `.lfm` | ANSI (CP1251), кириллица как `#1040#1072` — в UTF-8 НЕ переводить |
| `.sql`, `.json`, `.md`, `.yml`, `.py`, `.sh`, `.txt` | UTF-8 без BOM |

Скрипт массового перевода: `C:\Tools\utf8_convert.ps1` (на WORKST, копия в `~/.hermes/cache/scratch/utf8_convert.ps1`).
Логика: BOM → пропуск; чистый ASCII → пропуск; строго декодируется как UTF-8 → добавить BOM;
иначе CP1251 → UTF-8+BOM. Бэкапы `<file>.bak-ansi`. Запуск:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Tools\utf8_convert.ps1 [-DryRun]
```

Проверено 26.10.2026 на `H:\OLD\medicalgenomics`: 488 файлов CP1251→UTF-8, 35 получили BOM;
сборка `TestBuild` после перевода — **0 ошибок**. То есть Delphi 10.3 (Studio 20.0) читает UTF-8 с BOM корректно.

## MCP на WORKST: формы в DFM + отладка (26.10.2026)

Два HTTP MCP-сервера на `<адрес из окружения>`, подключены в Hermes как `delphi` и `pascal`:

| Имя | URL | Роль |
|---|---|---|
| `delphi` | `http://<адрес из окружения>/mcp` | Delphi IDE Remote MCP v1.22.1: `delphi_designer` (insert/set/delete/lint/check-binding для `.dfm`), `delphi_create` (форма/фрейм/дата-модуль), `delphi_edit` (ANSI-safe правка `.pas`), `delphi_build`, `delphi_search`, `delphi_docs` |
| `pascal` | `http://<адрес из окружения>/mcp` | pascal-dev v1.17.0 — отладка: `launch_app`, `screenshot_app`, `app_click`, `read_ide_errors`, `observe_ide`, `parse_form`, `build_dproj`, `check_syntax` |

Авторизация `delphi`: `Authorization: Bearer <токен>` + `X-Workspace: Main`; токен — `/home/boss/.hermes/secrets/delphi_mcp.env`.
Сервер лежит в `C:\Tools\DelphiLspMcp`, запускается задачей планировщика `DelphiLspMcp` (от `учётка домена`, -gui).
**Только RAD Studio 13.2 (37.0)**: у 10.3 нет `DelphiLSP.exe`, сервер с ней не стартует — сборка 10.3 идёт через MSBuild/TestBuild.

Правило BOSS: **формы, фреймы и data-модули — только в `.dfm`**, динамическое создание компонентов в коде запрещено.
Правку `.dfm` делать через `delphi_designer`, а не руками (проверка свойств и связки с классом).

### Запуск сервера вручную (если упал)

```powershell
Start-ScheduledTask -TaskName 'DelphiLspMcp'   # предпочтительно
# или: Start-Process C:\Tools\DelphiLspMcp\DelphiLspMcp.exe -ArgumentList '-gui'
```

`Start-Process` из WinRM-сессии умирает вместе с сессией — поэтому только через планировщик.
Порт 8765 требует правила firewall (`DelphiLspMcp 8765`), BindIP задаётся в `settings.ini`.

## IDE виснет (10.3): открытие проекта, Project Options, правый клик — это git-интеграция

Порядок проверки — именно такой. IDE перед чисткой закрыть, живость проверять фактом
(`Get-Process bds | Select Id,Responding`), а не на глаз.

1. **Путь к `git.exe` в настройках IDE** — `Tools → Options → Version Control → Git`.
   Путь от старой установки (`…\Git\mingw64\bin\git.exe`, `Program Files (x86)\Git\…`) заставляет IDE
   ждать бинарник, которого нет: виснет на **любом** проекте, независимо от репозитория. Рабочий путь на
   WORKST — `C:\Program Files\Git\cmd\git.exe`. Это проверять первым: настроек у git-интеграции в Delphi
   почти нет (путь к exe, имя/почта, цвета в Log Pane), отключить опрос репозитория из IDE нельзя —
   скорость задаётся со стороны git, а не Delphi.
2. **Рабочий `.git` в каталоге проекта или выше.** `gitide260.bpl` при открытии проекта и контекстного меню
   опрашивает `git status`; на репозитории в гигабайт это минуты, окно пишет «(Не отвечает)».

```
H:\medicalgenomics\.git    615 файлов, 1369,7 МБ   ← рабочий репозиторий, IDE опрашивает статус
H:\OLD\.git_                 38 файлов,  138,2 МБ   ← переименован, IDE не видит — не виснет
```

   Лечение: `.git` → `.git_` в каталоге, который открывает Delphi (git продолжает работать через
   `git --git-dir=.git_ --work-tree=.`), либо отключить пакет:
   `HKCU\Software\Embarcadero\BDS\<версия>\Known Packages` → `$(BDSBIN)\gitide260.bpl = 0` и
   `svnide260.bpl = 0` (перед правкой — `reg export` бэкап ключа).
   Ускорение git, если `.git` остаётся:
   `git config core.fscache true; core.preloadIndex true; core.untrackedCache true; core.fsmonitor true;
   feature.manyFiles true; gc.auto 0` — замер `git status --porcelain` 0,6 → 0,21 с на 1,37 ГБ.
   `core.ignoreStat=true` **не включать**: ускоряет сильнее, но `git status` перестаёт видеть изменения.
3. **Кэши и история в каталоге проекта.** Переместить (не удалять) `.dsk`, `.~dsk`, `.identcache`, `.otares`,
   `.dproj.local`, каталоги `__history` и `__recovery` — всё пересоздаётся.
4. **Мёртвые пути — два слоя.** (а) `DCC_UnitSearchPath` в `.dproj` по каждой конфигурации;
   (б) IDE Library Path: `HKCU\Software\Embarcadero\BDS\<версия>\Library\Win32` → `Search Path`, где пути
   собраны через переменные из `HKCU\…\Environment Variables` (`COMPONENTS`, `SOURCEMG`, `DXVCL`). Мёртвая
   переменная тянет десяток несуществующих каталогов; лечить `Set-ItemProperty` + вычистить отсутствующие
   элементы из `Search Path`, с `reg export` бэкапом обоих ключей.
5. **Плагины и тема.** `bds.exe -ns` (без экспертов) и `-notheme` отсекают сторонние плагины и отрисовку.
   CnPack/GExperts проверять по факту: если их нет в `Known Packages` и в `…\Studio\<N>\Bpl`, пункт меню идёт
   от другого пакета и «отключить CnPack» ничего не даст — искать реальный `.bpl`.

**Что НЕ помогает:** удаление `.dproj`, чистка `.dsk`/`.identcache` при живом `.git`, `-notheme` —
зависание возвращается. Если IDE отвечает, а залипает только диалог — начинать с пп. 1, 2 и 5, а не с путей:
мёртвые пути тормозят Project Options, но не вешают IDE насмерть.

## Бизнес-логика — компонент на датасетах (требование BOSS)

Расчёт, генерация документа, любая операция над данными оформляется **невизуальным компонентом**
(`TComponent`, published-свойства, настройки в Object Inspector и в DFM), а не набором классов,
которые форма создаёт в `Init`.

- **Вход и выход — датасеты.** `Order, Participants, Samples, Locuses, Frequencies : TDataSource` на входе,
  `ResultDataSet : TDataSet` на выходе (компонент его наполняет), плюс `ResultText : string`,
  `PI : Double` и событие `OnCalculated`. Форма вызывает `Calculate` и читает результат — три строки.
- **Всё, что пришло из БД, — уже готовый объект.** Данные берутся запросами в `TFDQuery`, текст запроса
  живёт в DFM датамодуля. Не строить параллельную объектную модель (`TConclData`, `TParticipant`, …) поверх
  датасета и не выносить SQL в `.sql`-файлы или в классы-репозитории: это дублирование и расхождение имён
  в рантайме вместо ошибки компиляции.
- **Тестируемость даёт `TFDMemTable`, а не интерфейс-провайдер.** Синтетический набор в памяти покрывает
  расчёт без БД; слой `IConclDataProvider`/`Repository`/`SqlCatalog` для этого не нужен.
- **Классы-помощники внутри компонента разрешены** (формулы, частоты, сборка текста) — они реализация,
  публичным API не являются. Компонент-фасад без внутренних классов превращается в файл на тысячи строк.
- **Если набор запросов меняется** — рядом отдельный компонент-провайдер (`Connection`, `SqlDir`,
  `LoadOrder(Id)`), чтобы форма вообще не знала про SQL.
- **Признак неправильного решения:** форма создаёт в `Init` пять и более объектов и знает про каталог
  SQL-файлов; классы называются `Model`/`Repository`/`Service` поверх данных, которые уже лежат в датасете.
  Такой слой переделывать, а не «дорабатывать».

## Сборка агентами Bernstein (CT114 → WORKST по WinRM, под учёткой BOSS)

Решение BOSS (26.10.2026): сборку и проверку агенты делают **под его учётной записью**.

```bash
# в CT114:
cd /opt/bernstein/workspaces/lis
python3 tools/build_win.py --project 'H:\OLD\medicalgenomics\Registr\registr.dproj' \
  --config TestBuild --exe 'H:\OLD\medicalgenomics\Registr\Win32\TestBuild\registr.exe'
```

Устроиство: `tools/build_win.py` пишет `.bat` (`rsvars.bat` + `MSBuild`) в base64 → раскодирует на WORKST →
запускает через `cmd /c` → читает лог → печатает `EXIT=`, `ERRORS=`, `WARNINGS=`, ошибки, проверку exe.
Креды: `/etc/bernstein/winrm.env` (600, bernstein). pywinrm стоит в CT114 (apt python3-winrm).
Проверено 26.10.2026: `EXIT=0 ERRORS=0 WARNINGS=345`, exe 99,1 МБ.

**Грабли, которые уже пройдены:**
- **`python3` из PATH на хосте Hermes — не тот интерпретатор.** У встроенного python Hermes нет `pywinrm`
  (`ModuleNotFoundError: No module named 'winrm'`), а у `/usr/bin/python3` есть. Скрипты сборки и WinRM-вызовы
  (`workst_build_any.py`, `workst_ps.py`) запускать ТОЛЬКО через `/usr/bin/python3 …` — иначе сборка падает до старта,
  а в отчёте субагента это выглядит как «сломалась сборка». Проверка: `/usr/bin/python3 -c "import winrm; print('ok')"`.
  То же правило отдавать субагентам в контексте задачи — они берут `python3` из PATH по привычке.
- Вложенные кавычки в `cmd /c ""rsvars.bat" && "MSBuild.exe" …"` через WinRM ломаются — PowerShell не возвращает EXIT.
  Только отдельный `.bat` и `cmd /c "<bat>"`.
- Here-string `@"…"@` в одной строке PowerShell тоже ломается — писать bat через base64 + `WriteAllBytes`.
- Локальную учётку `agentbuild` завести не удалось: создаётся, входит в Remote Management Users, права на `H:\OLD`
  выданы, но WinRM и SMB дают `InvalidCredentialsError` / `NT_STATUS_LOGON_FAILURE` (доменная политика для
  локальных учёток, `Minimum password age 1 день` не даёт даже сменить пароль в тот же день). Учётка удалена.

## Соглашение по именованию (требование BOSS, 26.10.2026)

Полный текст — `/home/boss/.hermes/templates/delphi-naming-conventions.md` (копии в `H:\OLD\medicalgenomics\docs\`,
`H:\medicalgenomics\docs\`, `/opt/bernstein/workspaces/lis/docs/`).

- **Никаких `TForm1`, `Form1`, `Button1`, `Edit1`, `Query1`, `Grid1`** — имя = роль.
- Форма: `T<Имя>Form` / экземпляр `<Имя>Form` (`TConclForm`/`ConclForm`, `TMainSystemForm`/`MainSystemForm`).
- Поле: `F`+PascalCase; параметр: `A`+PascalCase; локальная: PascalCase; константа: `c`+PascalCase.
- Компоненты: `btn`, `bb`, `grid`, `view`, `ds`, `qry`, `mt`, `cb`, `memo`, `lbl`, `ed`, `pnl`, `pc`, `tmr`, `il`, `ribbon`, `bm`.
- События: `<компонент><Событие>`.
- Перед коммитом искать `TForm[0-9]`, `Form[0-9]`, `Button[0-9]`, `FDQuery[0-9]`, `Grid[0-9]`; пусто — можно коммитить.

Переименование формы затрагивает 4 файла: `.pas` (класс, переменная, все `TFormN.Метод`), `.dfm` (`object`),
`.dpr` (`{FormN}` в списке модулей и `CreateForm`), `.dproj` (`<Form>`). Сделано для `JSONView` (было `TForm1`) и
`MG.Main` в `H:\medicalgenomics`.

**Документация API — XML-комментарии Help Insight, по-русски.** Для каждой процедуры/функции/метода/класса —
блок `/// <summary>` + `<param name="…">` на каждый параметр + `<returns>` + `<remarks>`. Только в
interface-секции, перед объявлением; в implementation не дублировать. Каждый тег закрывать — иначе подсказка
при наведении/Ctrl+Shift+H не появится. Формат-эталон — в `delphi-naming-conventions.md`, раздел
«Комментарии и документация API». Если в модуле уже есть `{ текст }` перед объявлением — Help Insight его не
показывает, такой комментарий конвертируется в `/// <summary>`.

## Два проекта на WORKST: H:\medicalgenomics (13.2) и H:\OLD\medicalgenomics (10.3)

Это РАЗНЫЕ вещи, не путать:

| | `H:\medicalgenomics` | `H:\OLD\medicalgenomics` |
|---|---|---|
| Смысл | наша новая ветка + автосборка | исходный проект конторы |
| Бандлы | `lib\*\out\dcu` внутри проекта | `H:\OLD\COMPONENTS`: `DevexpressVCL\Library\RS26`, `EhLib\Lib` |
| FastReport | `..\lib\fastreport\out\dcu` | `C:\Program Files (x86)\FastReport 6 VCL Enterprise\LibD26` |
| Собирается на | **13.2** (Studio 37.0), Release — OK | **10.3** (Studio 20.0), **TestBuild** — OK |

**Правило BOSS: на 13.2 ничего не собираем** — целевая среда 10.3, старый проект.

В старом проекте компоненты НЕ в `lib\`, а установлены в IDE 10.3 (BPL `C:\Users\Public\Documents\Embarcadero\Studio\20.0\Bpl\cxLibraryRS26.bpl`) и лежат в `H:\OLD\COMPONENTS`. Собирать ничего не нужно — уже собрано и установлено.

Рабочая конфигурация старого проекта — **TestBuild**, не Release:

```
rsvars 20.0 + MSBuild registr.dproj /t:Build /p:Config=TestBuild /p:Platform=Win32
→ EXIT=0, 0 ошибок, ~345 warning, exe H:\OLD\medicalgenomics\Registr\Win32\TestBuild\registr.exe (~104 МБ)
```

**Release падает** на `Version.rc : error : Fatal error Illegal macro definition in command line or defines page` — причина в `VerInfo_Keys`: значения с пробелами и слэшами (`FileDescription=LIS-2 main executable`, `LegalCopyright=(C) https://vk.com/yaroslav_tv`) ломают макросы brcc32 в MSBuild-пути (в IDE rc пишется файлом, поэтому там не падает). Чинится либо очисткой пробелов в `VerInfo_Keys`, либо `VerInfo_IncludeVerInfo=false` для конфигурации; оба варианта меняют свойства exe — без решения BOSS не делать.

**Сначала собрать как есть, пути править потом.** Мёртвые пути в `DCC_UnitSearchPath` (`G:\Delphi10-3 library\…`, `C:\MGWork\…`, `C:\DevExpress20\…`) сами по себе не ломают сборку: если компоненты зарегистрированы в IDE (BPL в `C:\Users\Public\Documents\Embarcadero\Studio\20.0\Bpl`) или лежат рядом в каталоге компонентов (`H:\OLD\COMPONENTS`: `DevexpressVCL\Library\RS26`, `EhLib\Lib`), компилятор берёт их оттуда. Не начинать с «починю пути»: собрать оригинальный проект без правок и смотреть на реальную ошибку — иначе правишь то, что не сломано, и затираешь конфигурацию конторы.

## `.dpr` и `.dproj`: что можно терять, а что нет

Перед удалением/пересозданием файлов проекта смотреть, что в них лежит:

- `.dpr` — список модулей (`X in 'X.pas' {FormName}`) и инициализация (`Application.CreateForm`). Восстанавливать
  нечем: теряется состав проекта и порядок создания форм. **Не удалять.**
- `.dproj` — конфигурации, `DCC_UnitSearchPath`, `VerInfo_Keys`, платформы и `DCCReference` на каждый модуль
  (у большого проекта — сотни). Delphi пересоздаёт его из `.dpr`, но с дефолтами: только Debug/Release, без
  путей, без VerInfo и без TestBuild.

Порядок «пересоздать `.dproj`, чтобы вылечить зависание»:

1. Снять слепок настроек в файл: пути по конфигурациям, `VerInfo_Keys`, флаги, полный список `DCCReference`.
2. `Copy-Item <проект>.dproj <проект>.dproj.bak-recreate`, затем удалить `.dproj` и `.dproj.local`.
3. Пользователь открывает `.dpr` в IDE — `.dproj` создаётся заново.
4. Вернуть из слепка пути/VerInfo/конфигурации, собрать MSBuild, подтвердить `EXIT=0`.

**XPath к `.dproj` требует namespace.** Корень — `<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">`,
поэтому `$doc.SelectNodes('//PropertyGroup')` молча возвращает пусто (и скрипт «чистит» ноль путей). Работать
только через менеджер: `$nsm.AddNamespace('msb','http://schemas.microsoft.com/developer/msbuild/2003')`, затем
`//msb:PropertyGroup`, `msb:DCC_UnitSearchPath`, `msb:DCCReference`, `msb:VerInfo_Keys`.

**Модуль, подключённый только через `uses`, в дереве проекта не виден** — и его форма не открывается в
дизайнере. Чтобы файл появился в проекте, добавить в ItemGroup с `DCCReference` элемент
`<DCCReference Include="MG.Concl.Form.pas"><Form>ConclForm</Form></DCCReference>`; в `<Form>` — имя
экземпляра из первой строки `.dfm` (`object ConclForm: TfrConclForm`). После правки — пересборка.

**Ссылка на компонент чужого владельца пишется полным именем.** Если `dsMethod`/`mtResult` живут в
датамодуле, то в `.dfm` формы — `DataController.DataSource = ConclDataModule.dsMethod` (короткое `dsMethod`
там не резолвится: DFM ищет компонент только среди владельцев формы), а в коде — `FDM.dsMethod`. Датамодуль
создаётся в `.dpr` через `Application.CreateForm` **до** главной формы, наборы с `StoreDefs` открываются
в `DataModuleCreate` (`if not Active then CreateDataSet`), иначе первый же `FieldByName` даёт исключение.

## Проект, который жил на старых `.dcu`: каскад ошибок при первой полной пересборке

Признак: проект «собирался годами», но после пересоздания `.dproj` / чистки DCU валится пачкой ошибок,
которых в коде «не было» — компилятор просто никогда не пересобирал эти модули, жили старые `.dcu`.

- **`E2064 Left side cannot be assigned to`** на константе (`const idxGene: integer = 0;`, которой потом
  присваивают): `const` → `var` **без инициализатора**. `var x: integer = 0;` в Delphi недопустим и даёт
  `E2029 ',' or ':' expected but '=' found` — убирать `= N` обязательно.
- **Массив-константа, который дополняется в рантайме** (`cYDNAmarkers: array of string = [...]`): объявить
  `var cYDNAmarkers: TArray<string>;`, значения — в секции `initialization` **вместо** финального `end.`.
  Вставлять перед `end.`, заменив старый `begin … end.`, иначе `E2029 Statement expected but 'INITIALIZATION'
  found`.
- **Править шаблоном пачкой, а не по одной ошибке.** Тот же `const idx…: integer = N` лежит в нескольких
  фреймах: скрипт обходит `*.pas`, убеждается, что имени где-то присваивают (`^\s*idx\w+\s*:=`), меняет
  блок, кладёт `<файл>.bak-const` / `.bak-varinit`.
- **Старые копии компонентов в путях поиска перекрывают актуальные:** `FR5\LibD24` (FastReport 5, не Unicode)
  даёт `E2010 AnsiChar and Char`, `ExcelExport\Source` — `E2003 NULL` / `VarToStr`. Добавлять в путь только
  каталоги, реально нужные проекту; сторонние SDK подключать готовыми DCU, не исходниками;
  `*\Examples\*`, `*demos*`, `CEF4\demos` — не добавлять.
- **Дубли модулей:** один юнит в нескольких каталогах (`DNACalc.pas` в корне, `Maniac`, `Maniac2`) — берётся
  первый по пути поиска. При странном поведении сначала выяснить, какой файл подключился.
- **Критерий успеха — новый exe, а не `EXIT=0`.** MSBuild возвращает 0 и когда считает цель актуальной:
  проверять `LastWriteTime` файла `Win32\<Config>\<Проект>.exe`. Если exe не обновился — смотреть
  `DCC_ExeOutput` (пустой = вывод в корень проекта).

Полный разбор — таблица ошибок, готовый список `DCC_UnitSearchPath`, проверка данных запросами —
`references/compile-cascade-triage.md`.

## Сборка registr.dproj на WORKST (F2613 MemTableDataEh)

Симптом: `H:\medicalgenomics\DModule.pas(10): error F2613: Unit 'MemTableDataEh' not found`, EXIT=1, exe не создаётся. При этом `MemTableDataEh.dcu` физически есть: `H:\medicalgenomics\lib\ehlib\out\dcu\MemTableDataEh.dcu`.

Причина: в `registr.dproj` в `DCC_UnitSearchPath` есть devexpress, fastreport, ems-export/import, graphics32 — **но нет ehlib**. Одной Base-конфигурации мало: PropertyGroup'ов несколько (Base, Release, Debug, Win64), MSBuild берёт путь из активной — добавлять во ВСЕ, где есть `DCC_UnitSearchPath`.

```powershell
$p='H:\medicalgenomics\Registr\registr.dproj'
Copy-Item $p "$p.bak-ehlib2" -Force
$xml=[xml](Get-Content $p -Raw); $add='..\lib\ehlib\out\dcu;..\lib\ehlib\Common;'; $n=0
foreach($pg in $xml.Project.PropertyGroup){ if($pg.DCC_UnitSearchPath -and $pg.DCC_UnitSearchPath -notlike '*ehlib*'){ $pg.DCC_UnitSearchPath=$add+$pg.DCC_UnitSearchPath; $n++ } }
$xml.Save($p); "изменено: $n"
```

Проверка — только полной сборкой (`rsvars.bat` + `MSBuild.exe registr.dproj /t:Build /p:Config=Release /p:Platform=Win32`), через WinRM-скрипт (pywinrm, ntlm, `учётка домена`): длинные интерактивные вызовы обрываются. Успех = `EXIT=0`, 0 ошибок, ~333 warning/hint, свежий `H:\medicalgenomics\Registr\Win32\Release\registr.exe` (~104 МБ).

## Редактирование Delphi-файлов (legacy cp1251)

### При чтении
```python
with open('file.pas', 'r', encoding='cp1251') as f:
    content = f.read()
```

### При записи
```python
with open('file.pas', 'w', encoding='cp1251') as f:
    f.write(content)
```

### Через patch-инструмент
patch-инструмент работает на уровне байтов. При вставке русского текста
ВСЕГДА указывать байты в cp1251, не в UTF-8.

## Компиляция из командной строки (DCC32)

### Итеративный цикл исправления ошибок компиляции

При работе с новым или незнакомым проектом используй цикл:

### Адреса WORKST

- Активный интерфейс — **<адрес из окружения>** (Ethernet 2): WinRM 5985 (после `Enable-PSRemoting`), RDP 3389 и SMB 445
  (`C$`/`H$` рабочие: `smbclient //<адрес из окружения>/C$ -U "организация/заказчик%<pass pdc>"` — put/get файлов). **<адрес из окружения>** —
  второй порт (плата MSI, WoL-MAC `D8:43:AE:4E:5B:A3`), может быть не подключён — не считать машину офлайн по нему.
  Машина: MSI MS-7C94, Windows 11 Enterprise 26H1 (build 28000), домен домен организации; заходит `организация\заказчик` +
  `pass pdc`; активация — MAK-ключ `pass windows/win11-enterprise-mak`. На .3 — MCP-сервер профиля `workst`
  (`http://<адрес из окружения>/mcp`, токен в `~/.hermes/profiles/workst/config.yaml`).
- **Если 5985 закрыт после включения машины** (служба не стартанула) — включить удалённо по RPC через impacket:
  `PIP_USER=false pip install impacket` (глобальный pip.conf с `user='true'` иначе валит установку в venv),
  затем `wmiexec.py 'домен организации/заказчик:<pass>@<адрес из окружения>' 'powershell -NoProfile -Command "Enable-PSRemoting -SkipNetworkProfileCheck -Force"'`;
  вывод может оборваться — проверять открытием 5985 (~1–2 мин).
- DNS-имя `workst.организация.local` → **<адрес из окружения>** — устарело (машины там нет).
- Разбудить выключенную машину: WoL (`~/.hermes/scripts/wol.py`, MAC `D8:43:AE:4E:5B:A3`; либо с MikroTik
  `/tool wol interface=BRIDGE-LAN mac=...` — изнутри её L2); MAC/адреса сверять в DHCP-lease MikroTik
  (`/ip dhcp-server lease print detail where host-name~"WORKST"`). Если за ~3–5 мин не встала — питание снято
  физически, нужен человек.
- **Выполнять PowerShell на WORKST с hermes:** `timeout -k 3 90 /usr/bin/python3 ~/.hermes/scripts/workst_ps.py "<powershell>"`
  (pywinrm + pass pdc, хост <адрес из окружения>). Пароль в командную строку НЕ писать; скрипты — ASCII-only.
  Зависимости скрипта: `pywinrm` и `requests_ntlm` (без второго — `ModuleNotFoundError: No module named 'requests_ntlm'`;
  лечение: `pip install --user requests_ntlm`). Если пароль читается из pass, а не из env — следить, чтобы скрипт
  не печатал его в вывод/логи.

1. **Pull** — `git pull` на WORKST
2. **Compile** — запустить dcc32.exe с полным захватом вывода (через PowerShell)
3. **Read ALL errors** — dcc32 выводит ошибки в stdout/stderr. Каждая ошибка содержит:
   - Имя файла и номер строки: `ServerForm.pas(123)`
   - Код ошибки: `E2010`, `F1026`, `E2003` и т.д.
   - Описание: `Incompatible types`, `Undeclared identifier`, `File not found`
4. **Fix each** — исправить ВСЕ ошибки. Компилятор Delphi останавливается на первой фатальной;
   исправляй по одной, затем перекомпилируй.
5. **Recompile** — повторять шаги 2-4 пока `EXITCODE: 0`
6. **Commit** — `git add -A && git commit -m "fix: ..." && git push`

**Важно:** Delphi компилятор может показывать не все ошибки за раз — некоторые
проявляются только после исправления предыдущих. Прокручивай цикл до полной победы.

### Полный захват вывода компиляции (PowerShell)

Простая обёртка:
```powershell
$ErrorActionPreference='Stop'
$output = & "C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe" -B -U"C:\Project\Common" -E"C:\Project" -N"C:\Project\dcu" "C:\Project\Server\ServerApp.dpr" 2>&1 | Out-String
Write-Host $output
Write-Host "EXITCODE: $LASTEXITCODE"
```

Или однострочник через `hermes -p workst`:
```bash
hermes -p workst -z "powershell -Command \"...\"" --yolo
```

EXITCODE 0 = успех. Любое другое значение = ошибки компиляции.

### Основные ключи

| Ключ | Описание | Пример |
|------|----------|--------|
| `-B` | Полная перекомпиляция (Build all) | Обязателен при первом запуске или смене путей |
| `-M` | Инкрементальная (Make) — только изменённые файлы | Экономит время при повторных сборках |
| `-U"путь"` | **Unit search path** — НЕ `-I`! Пути к .pas/.dcu модулям | `-U"C:\Project\Common"` |
| `-E"путь"` | Выходная директория для .exe | `-E"C:\Project\Bin"` |
| `-N"путь"` | Директория для .dcu файлов (object files) | `-N"C:\Project\Obj"` |
| `-D"символ"` | Условные директивы | `-DRELEASE` |
| `-R"путь"` | Resource search path | `-R"C:\Project\Res"` |
| `-LU"пакет"` | Runtime packages (VCL, etc.) | `-LU"VCL"` |

**ВАЖНО:** Для поиска файлов модулей используется `-U`, а НЕ `-I`. 
`-I` — это Include path (для `{$I file.inc}`), а не unit search path.

### Параллельная декомпозиция для многомодульных проектов

Для проекта из нескольких .dpr файлов (сервер + клиент + тесты) —
**не фиксь всё одной делегацией**. Разделяй по модулям и запускай parallel batch:

```python
delegate_task(tasks=[
    {
        "goal": "Скомпилировать и исправить СЕРВЕР (ServerApp.dpr)",
        "context": "Ключи: -B -U\"Common\" -E\".\" -N\".\\dcu\" Server\\ServerApp.dpr",
    },
    {
        "goal": "Скомпилировать и исправить КЛИЕНТ (ClientApp.dpr)",
        "context": "Ключи: -B -U\"Common\" -E\".\" -N\".\\dcu\" Client\\ClientApp.dpr",
    },
    {
        "goal": "Скомпилировать и исправить ТЕСТЫ (TestRunner.dpr)",
        "context": "Ключи: -B -U\"Common\" -E\".\" -N\".\\dcu\" Tests\\TestRunner.dpr",
    },
])
```

**Правила декомпозиции:**
- Каждый .dpr файл = свой агент (они независимы по .dcu если задан `-N`)
- Общие модули (Common/) — read-only для кодеров, правит только отдельный агент
- Каждый кодер получает полную строку компиляции и известные проблемы
- После кодеров — архитектор анализирует архитектуру проекта
- После архитектора — критик проверяет качество всех фиксов

### Пример команд для многомодульного проекта

Структура:
```
C:\Project\
├── Common\          — общие модули
├── Server\          — точка входа сервера (ServerApp.dpr)
└── Client\          — точка входа клиента (ClientApp.dpr)
```

Компиляция сервера:
```cmd
cd C:\Project
"C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe" -B -U"C:\Project\Common" -E"C:\Project" Server\ServerApp.dpr
```

Компиляция клиента:
```cmd
cd C:\Project
"C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe" -B -U"C:\Project\Common" -E"C:\Project" Client\ClientApp.dpr
```

Компиляция тестов (DUnit):
```cmd
cd C:\Project
"C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe" -B -U"C:\Project\Common" -E"C:\Project\Tests" Tests\TestRunner.dpr
```

### Поиск dcc32.exe по версиям RAD Studio

**Номер каталога `Studio\<N>` — НЕ версия Delphi, и таблица ниже может устареть.** На одной машине стоят
`20.0` (10.3 Rio) и `37.0` рядом, при этом `dcc32` из `20.0` печатает «compiler version 33.0»; отдельно
встречается `Studio\24.0`, который тоже относится к «13-й». Определять версию по факту, а не по номеру папки:

```powershell
& "C:\Program Files (x86)\Embarcadero\Studio\<N>\bin\dcc32.exe" 2>&1 | Select-Object -First 1   # баннер компилятора
(Get-Item "C:\Program Files (x86)\Embarcadero\Studio\<N>\bin\bds.exe").VersionInfo.ProductVersion     # версия IDE
```

И проверять `DelphiLSP.exe` рядом: его отсутствие в каталоге — маркер версии старше 10.4.

| Версия RAD Studio | Delphi версия | Путь к dcc32.exe |
|-------------------|---------------|-------------------|
| 10.3 Rio | 26.0 | `C:\Program Files (x86)\Embarcadero\Studio\20.0\bin\dcc32.exe` |
| 10.4 Sydney | 27.0 | `C:\Program Files (x86)\Embarcadero\Studio\21.0\bin\dcc32.exe` |
| 11 Alexandria | 28.0 | `C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\dcc32.exe` |
| 12 Athens | 36.0 | `C:\Program Files (x86)\Embarcadero\Studio\23.0\bin\dcc32.exe` |
| 14 Athens | 37.0 | `C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe` |

### Сборка проекта через msbuild и поиск потерянных путей к компонентам

Проект целиком собирается от `rsvars.bat` выбранной студии + `MSBuild.exe` из .NET Framework (отдельный msbuild в PATH обычно НЕТ):

```powershell
$rs  = 'C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\rsvars.bat'
$msb = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe'
cmd /c "`"$rs`" & `"$msb`" `"H:\<проект>\Registr\registr.dproj`" /t:Build /p:Config=Release /p:Platform=Win32 /nologo /v:minimal > C:\Users\boss\build.log 2>&1"
'EXIT=' + $LASTEXITCODE
```

**Когда падает `F2613 Unit 'X' not found`:** смотреть `<DCC_UnitSearchPath>` в `.dproj` — рабочие копии МГ тащат пути с прежней машины (`G:\Delphi10-3 library\…`, `C:\MGWork\…`). Компоненты в рабочей копии лежат в `<корень>\lib\<вендор>\` с готовыми `out\dcu`:

```
H:\medicalgenomics\lib\devexpress\out\dcu   (≈1800 dcu)
H:\medicalgenomics\lib\fastreport\out\dcu    (≈380)
H:\medicalgenomics\lib\graphics32\out\dcu    (≈100)
H:\medicalgenomics\lib\ehlib\out\dcu         (≈130)   + исходники в lib\ehlib\Common
```

Лечение — дописать в `DCC_UnitSearchPath` **относительные** пути от каталога проекта (`..\lib\ehlib\out\dcu;..\lib\ehlib\Common;`), предварительно сделав бэкап `.dproj`. Тег в файле выглядит как `<DCC_UnitSearchPath>путь;путь</DCC_UnitSearchPath>` — **без атрибутов и без кавычек**, поэтому regex вида `<DCC_UnitSearchPath>"…"` не находит ничего и молча «ничего не делает»: сборка падает с тем же `F2613`, а `Select-String 'ehlib'` по `.dproj` возвращает `False`. Править текст между `>` и `</` (или править в IDE: Project → Options → Delphi Compiler → Unit search path), а после правки **проверить, что путь реально в файле**, и только затем пересобирать — разбирать только строки `: error ` (варнинги `W1057 Implicit string cast` и `H2077` — шум, не повод останавливаться).

Собирать лучше той студией, которой проект живой: продовый стек МГ — 10.3 (`Studio\20.0`), сборка на 37.0/13.x на непереведённом проекте даёт ошибки отсутствующих юнитов, которых на 10.3 нет.

### Типовые ошибки компиляции

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `E2010 Incompatible types: 'TProc<string>' and 'Procedure'` | Анонимная функция внутри вызова метода не распознаётся | Заменить inline anonymous method на прямую передачу метода: `SetOnLog(MyMethod)` вместо `SetOnLog(procedure ... end)` |
| `E2003 Undeclared identifier: 'FormatByteSize'` | Функция удалена/переименована в этой версии Delphi | Заменить на ручное форматирование: `Format('%d bytes', [Size])` или написать свою функцию |
| `E2010 Incompatible types: 'PChar' and 'PWideChar'` | Несоответствие Ansi/Unicode | Убедиться что строки в коде используют `string` (а не `AnsiString`) для API вызовов |
| `Fatal: F1026 File not found: 'VCL.Forms.dcu'` | Не найден путь к VCL | Добавить `-R"C:\Program Files (x86)\Embarcadero\Studio\37.0\lib\win32\release"` |
| `error F2613: Unit 'MemTableDataEh' not found` (или любой сторонний юнит) | В `DCC_UnitSearchPath` проекта нет пути к компоненту — часто там прописаны пути С ДРУГОЙ машины (`G:\Delphi10-3 library\…`, `C:\MGWork\…`) | Сначала найти, где лежит юнит и готовые dcu (`Get-ChildItem <корень> -Recurse -Filter <Unit>.pas`), потом добавить в проект относительные пути — см. ниже |

### Версионные особенности RAD Studio 14 (v37.0)

- `FormatByteSize` — **удалён** из `System.SysUtils`. Использовать свою реализацию или `FormatFloat`.
- Анонимные методы (anonymous methods) работают, но прямая передача процедуры в `TProc<T>` предпочтительнее inline-синтаксиса.
- DUnit: поставляется в составе RAD Studio, обычно в `source\DUnit\src\`. Поиск: `dir /s DUnitFrame.pas`.
- Для VCL-приложений нужно явно указывать `-LU"VCL"` только если используются runtime packages.

## Агенты (Codex / Claude Code) на Delphi

Правило: **агент без компилятора и Language Server пишет Delphi вслепую** — правдоподобно и неверно.
Прежде чем отдавать агенту Delphi-задачу, у него в конфиге MCP должны быть навигация (`delphi-lsp`) и сборка
(`dcc32`/`msbuild`); иначе он не видит 1500 юнитов и не узнаёт про ошибки компиляции. Роль-профиль,
сборочный цикл, конфиги Codex/Claude Code и проверенные пути WORKST — `references/agent-driven-delphi.md`.

- **Версию Delphi фиксировать до старта.** На WORKST стоят 20.0 и 37.0 одновременно; LSP одной версии на проекте
  другой даёт ложные ошибки. Указывать `dcc32`/`DelphiLSP` конкретной версии и ту же, которой проект собирали.
  Продовый стек МГ — **10.3 Rio = `Studio\20.0`**; сборка на 37.0 даёт «всё ок» и ничего не доказывает.
- **Версия в выводе dcc32 — версия КОМПИЛЯТОРА, не IDE.** `Studio\20.0\bin\dcc32.exe` печатает
  `Delphi for Win32 compiler version 33.0`: 10.3 Rio — это IDE 26.0 / компилятор 33.0. Не принимать «33.0»
  за чужую сборку и не искать по этому числу каталог.
- **В 10.3 нет `DelphiLSP.exe`** (появился в 10.4): поиск по `Studio\20.0` пуст, ставить LSP от 37.0 на проект 10.3
  нельзя — другая версия символов и RTL. Навигацию для агента строить через `delphi-lsp-agent` (индекс/`references`,
  он же работает на Linux-хосте) или поиск по коду, а не через LSP другой версии.
- **Смоук «компилятор жив» — за 10 секунд:** `rsvars.bat` → `dcc32 -Q <unit>.pas` → строка
  `N lines, 0.00 seconds, … bytes code` и появившийся `.dcu`. Ошибки вида `E2029 ';' expected but '.' found`
  на первой строке означают, что файл — не юнит, а вырезка (см. следующий пункт), а не что компилятор сломан.
- **В репозитории есть `.pas`-фрагменты, а не юниты.** Файл может начинаться прямо с `procedure TMainForm.X(...)`
  без `unit … interface`; такой файл не собирается в принципе, и «починить ошибки компиляции» здесь нельзя.
  Перед правкой смотреть первые строки: `unit <Имя>;` — юнит, `procedure`/`begin` — фрагмент, его только читают.
- **Кодировки в одном репозитории разные.** Часть `.pas` в ANSI (байты 0xC0–0xFF), `.dproj` — UTF-8 с BOM.
  Перед правкой смотреть байты файла; UTF-8-запись поверх ANSI ломает русские литералы, и это видно только в рантайме.
- **`.dfm` руками не переписывать** — формы регенерирует IDE; агент правит `.pas`, а не разметку формы.
- **Цикл: `dcc32` на юнит → `msbuild <проект>.dproj` → тесты.** Один `dcc32` даёт быструю обратную связь,
  `msbuild` проверяет проект целиком. Агент должен видеть вывод компилятора, а не пересказ.

## «Написано» ≠ «подключено»: проверка перед выводами о готовности

Большие Delphi-проекты легко накапливают модули, которые никто не вызывает. Прежде чем говорить, что
функциональность есть (или что её надо «переделать»), проверить три вещи:

- **Ссылки из точек входа:** `Select-String -Path <проект>\*.dpr,<проект>\*Main*.pas -Pattern '<UnitName>'`.
  Ноль ссылок — модуль существует, но из UI не вызывается: это и есть настоящий объём работы.
- **Состояние VCS рабочей копии:** `Test-Path .hg`, `Test-Path .git`. Рабочая копия без версионирования
  встречается рядом с git-клоном того же проекта — правки в ней не откатываются; сообщать это до,
  а не после серии правок, и предлагать вернуть под VCS.
- **Ресурсы-шаблоны по числу вариантов:** отчетные шаблоны (`Reports\*.fr3`), словари, ini — если есть только
  один «default», мультивариантный сценарий собрать нечем, сколько бы кода ни было написано.
- **Форма без `.dfm` — техдолг, а не норма.** Требование BOSS: формы, фреймы и data-модули описываются
  в `.dfm`, динамическое создание компонентов в коде (`TcxButton.Create`, `Parent := Self`, `Left/Top` кодом)
  запрещено. Существующие экраны, собранные в конструкторе (DevExpress-контролы), переводить в DFM по задаче,
  а не «попутно» — рецепт и грабли: `references/dfm-form-migration.md`.
  Признак нарушения при чтении кода: в `private`-секции формы список `FCbMode: TcxComboBox; FBtnCalc: TcxButton;`
  и метод `BuildUI` — это и есть компоненты, которые должны быть в `.dfm`.

## PDFium (PDF-вьюер): «система не обнаружила pdfium.dll»

Симптом: при запуске exe — системная ошибка «не обнаружила pdfium.dll». Проекты с PDF-просмотром используют обёртку (в проекте МГ — `H:\medicalgenomics\Registr\DX.Pdfium4D`, вьюер на её основе); в репозитории лежат ТОЛЬКО исходники обёртки, сама DLL не хранится.
Правило из доков обёртки (`USING_DX_PDF.md`): **`pdfium.dll` кладётся РЯДОМ С EXE** (Windows 32-bit и 64-bit — один и тот же `pdfium.dll`, разрядность строго под exe: Win32-проект → x86). Источник — релизы **github.com/bblanchon/pdfium-binaries** (ассеты `pdfium-win-x86.tgz` / `pdfium-win-x64.tgz`, теги вида `chromium/NNNN`; внутри `bin/pdfium.dll`, тянет только системные DLL).
Проверка битности DLL: `file pdfium.dll` → «PE32 ... Intel i386» для x86, «PE32+ ... x86-64» для x64.
Проверено 02.10.2026 (WORKST): свежий x86-релиз подложен в `H:\medicalgenomics\Registr\Win32\Debug\` рядом с `registr.exe` — LoadLibrary из папки приложения = OK. Копия на hermes: `/home/boss/.hermes/files/pdfium-x86/`.

## FireDAC и PostgreSQL: «Cannot load vendor library [libpq.dll]»

Симптом (пример): при загрузке IDE/пакета или запуске приложения — `[FireDAC][Phys][PG]-314. Cannot load vendor library [libpq.dll]. Не найден указанный модуль... check it is in the PATH or application EXE directories, and has x86 bitness`. 
Причина: отсутствует клиентская библиотека PostgreSQL. IDE Delphi 10.3.3 и большинство их проектов — 32-битные → нужна **x86 (Intel i386)** libpq; официальные x86-инсталляторы PostgreSQL больше не публикуются (get.enterprisedb.com отдаёт 403 — не гео-блок, файлов нет).

**Готовый проверенный набор** (собран 02.10.2026, лежит и на hermes): `/home/boss/.hermes/files/pgsql-x86/` — `libpq.dll, ssleay32.dll, libeay32.dll, libintl-8.dll, libiconv-2.dll, msvcr120.dll, msvcp120.dll` (по md5-контролю + `pgx86.zip`). Источник: PostgreSQLPortable 10.4.1 (github.com/garethflowers/postgresql-portable, релиз `PostgreSQLPortable_10.4.1.zip` → `App/PgSQL/bin/`) — там x86 libpq со всеми зависимостями. Проверять битность: `file libpq.dll` → «PE32 executable ... Intel i386» (для x64 будет «PE32+ ... x86-64» — не подойдёт 32-битному Delphi).

Куда ставить: в каталог, который реально просматривается поиском DLL — для IDE: `<Studio>\20.0\bin` (app-dir процесса delphi32.exe; там же он и в PATH); для собранного приложения: **рядом с его .exe**. Зависимости класть туда же (Windows ищет зависимости по app-dir/PATH, НЕ в каталоге самой DLL).

Проверка загрузки — только из **32-битного** процесса (`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`), тест-скрипт: `scripts/test_libpq.ps1` (P/Invoke LoadLibrary + внятный отчёт об ошибке). Питфоллы: (1) 64-битный PowerShell не загрузит x86-DLL; (2) .ps1 с кириллицей в UTF-8 без BOM ломает парсер PS 5.1 — тест-скрипты держать ASCII-only; (3) если ошибка воспроизводится в собранном .exe — файлы копировать к exe, а не в bin IDE.

## Типовые ошибки и восстановление

### Ошибка: файл прочитан как UTF-8 и сохранён обратно (legacy Delphi 7-2007)

**Симптомы:**
- Русский текст превратился в `?` (U+FFFD replacement character)
- `file` показывает "UTF-8 Unicode text" (должен быть "ASCII text" или "ISO-8859 text")

**Причина:** cp1251-байты русских букв не являются валидным UTF-8.

**Восстановление PAS:**
1. `git checkout <parent_commit> -- file.pas` — восстановить оригинал
2. Найти в diff'е только ASCII/latin-изменения
3. Применить их поверх восстановленного файла
4. Сохранить в cp1251

**Восстановление DFM:**
1. Проверить, есть ли прямой русский текст (не в #-нотации)
2. Если есть — взять битый файл и заменить UTF-8 байты на cp1251
3. Если нет прямого текста — файл можно использовать как есть

## Проверка кодировки (legacy Delphi)

```bash
# Проверка через file
file file.pas file.dfm

# Проверка на U+FFFD (кракозябры) — только для legacy cp1251 файлов
python3 -c "
with open('file.pas', 'rb') as f:
    data = f.read()
print('U+FFFD count:', data.count(b'\xef\xbf\xbd'))
"
```

Для современных Delphi (XE2+) UTF-8 — это норма, проверка на cp1251 не нужна.

## LSP-инструменты для Delphi (разведка 2026-09-25)

- **python-delphi-lsp** (PyPI, MPL-2.0) — парсер Delphi/Object Pascal + семантический индекс + LSP (pygls) + агентский CLI `delphi-lsp-agent`; Windows/macOS/**Linux**. ✅ **УСТАНОВЛЕН на hermes 25.09.2026 (v3.6.0)** — venv `/home/boss/.hermes/venvs/delphi-lsp/`, CLI `/home/boss/.hermes/venvs/delphi-lsp/bin/delphi-lsp-agent`:
  - `view --root DIR --layer {overview,projects,units,unit,symbols,symbol,implementation,references,problems,metrics} [--query X] [--format markdown|json]` — ~1 с на проект (13 юнитов).
  - `references --query X` — все использования символа: файл:строка:колонка + контекст (процедура) + `Completeness: sound_partial` (честно о полноте). `symbol --query X` — состав класса; `implementation` — код декларации.
  - Ещё команды: `index/wiki/skill/opencode/worker/cache/query` (wiki — экспорт кодобазы в Markdown).
  - ВАЖНО: `delphi-lsp` (сам сервер) при `--help` висит (stdio) — работать только с `delphi-lsp-agent`, вывод перенаправлять в файл, НЕ пайпить.
  - Демо-копия реального проекта BOSS (SharedMemFileTransfer с WORKST): `/home/boss/.hermes/state/delphi-demo`.
  - В LSP-подсистему Hermes не встраивается (реестр зашит) — использовать как CLI-инструмент агентами.
- **DelphiLSP** (Embarcadero) — в составе RAD Studio 10.4+, общение по stdio; официальное расширение для VS Code; но только Windows и привязан к лицензии; нужны `.delphilsp.json` (в IDE: Code Insight → Generate LSP Config).
- **delphi-lookup** (github.com/JavierusTk) — LSP для Claude Code на .pas (go-to-def/hover/references, SQLite-индекс ~75 мс); Windows, Delphi 12+.
- **DDK «Delphi Development Kit»** (VS Code) — генерация `.delphilsp.json` без IDE + компиляция + MCP-инструменты (Windows).
- pascal-language-server (genericptr/Castle/Isopod) — на Lazarus CodeTools, заточен под FPC/Lazarus, Delphi-проекты пассивно.
- LSP-подсистема Hermes кастомные серверы не принимает (реестр зашит в `agent/lsp/servers.py`); внешние — только как CLI-инструмент через терминал.

## Журнал грабель для агентов (требование BOSS)

Каждую найденную и устранённую ошибку сборки/окружения сразу описывать — иначе агенты повторяют её заново.
Два места, оба обязательны:

- `docs/pitfalls.md` в репозитории проекта — симптом → причина → решение → чем проверить, по разделам:
  IDE/git, `.dproj`, ошибки компилятора, DFM-правила, кодировки, критерий сборки, проверка данных.
- `AGENTS.md` в рабочем каталоге агентов (`/opt/bernstein/workspaces/lis/AGENTS.md`) — короткая выжимка
  в разделе «читать ДО правок» со ссылкой на `docs/pitfalls.md`.

После `pct push` файлы принадлежат root: ставить `--perms 0644` и `chown bernstein:bernstein`, иначе агент
не сможет их править. Документ ведётся без дат и номеров задач — только правило и механизм.

## Правка исходников скриптами — не потерять файл

- Перед правкой — бэкап `<файл>.bak-<повод>`; после — сверка размера до/после.
- В Python-регэкспах **не включать `re.S`/`(?s)` вместе с `.*`**: DOTALL-точка съедает файл до конца и
  `str.replace` записывает обрезанный юнит (реальный случай: 43 Кбайт → 10 Кбайт). Строить замену по
  конкретным строкам или по блоку с явными границами, а не «от якоря до конца файла».
- Читать/писать в исходной кодировке: определять по первым байтам (`utf-8-sig` при BOM, иначе `cp1251`),
  не угадывать — слепой `cp1251` падает на файле в UTF-8.
- `.ps1` с русским текстом без BOM ломает парсер PowerShell 5.1 (`Unexpected token`): скрипты автоматизации
  писать ASCII-only или сохранять UTF-8 **с** BOM.
- Массовые правки исходников конторы делать только на копиях с бэкапами и сразу сообщать BOSS, какие файлы
  тронуты и где лежат `.bak`.

## Связанные материалы

- `references/compile-cascade-triage.md` — триаж каскада ошибок после пересоздания `.dproj`: готовый
  `DCC_UnitSearchPath`, таблица «ошибка → виновник → действие», паттерн датамодуля со статическими
  колонками, проверка данных SQL-запросами и признак «форма реально в exe».
- `references/encoding-recovery.md` — пошаговое восстановление после порчи кодировки (реальный случай CR00028049)
- `references/workst-build-environment.md` — среда сборки проекта МГ на WORKST: версии Delphi, компоненты, точки входа (Registr), FastReport, конвенция pin-файла.
- `references/lis-delphi13-migration.md` — переход ЛИС с 10.3 на RAD Studio 13.x: вынос компонентов в отдельные
  репозитории и субмодули `lib/`, порядок сборки оркестратором, регистрация пакетов в реестре, типовые блокеры
  (`E1026 *.res`, `E2003 NULL` в EMS, `F2051` от смешанных DCU) и проверка на чистой сборочной машине.
- `references/lis2-conclusion-generation.md` — подсистема генерации заключений ЛИС-II: слои `MG.Concl.*`,
  форма без `.dfm`, шаблоны отчёта, контрольные заказы и порядок работ по мультиучастниковому бланку.
- `references/dfm-form-migration.md` — перевод формы из кода в `.dfm`: снятие инвентаря, генерация текста формы,
  published-поля, `CreateNew` → `Create`, разделение `uses`, проверка сборкой и визуально.
- `references/agent-driven-delphi.md` — агентская разработка на Delphi: что должно быть подключено (MCP навигация +
  сборка), конфиги Codex и Claude Code, проверенные пути компилятора/MSBuild/LSP на WORKST, кодировки и цикл проверки.
- `references/rad-studio-ci-licensing.md` — условия Embarcadero для автосборки: CLI-компилятор на build-сервере (EULA 2.4), silent install `/SLIPFILE`, сетевые лицензии, питфолл trial-компилятора.
- `references/rad-studio-install-activation.md` — установка и активация RAD Studio из раздач RuTracker: KeyPatch рядом с дистрибутивом (+ пароль в `.txt`), пошаговая процедура патча, состав стенда, где лежит собранный комплект.
