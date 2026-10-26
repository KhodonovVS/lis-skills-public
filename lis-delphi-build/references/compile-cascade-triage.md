# Триаж каскада ошибок: старый Delphi-проект после пересоздания `.dproj`

Для случая, когда проект собирался «годами» на старых `.dcu`, а после удаления `.dproj` /
смены конфигурации валится пачкой `F2613` и `E2xxx`. Порядок ниже проверен на `H:\OLD\medicalgenomics`
(Delphi 10.3, Studio 20.0, Win32).

## 1. Сначала восстановить пути поиска, а не править код

Пересозданный `.dproj` содержит только корень проекта. Симптом — каскад `F2613 Unit 'X' not found`,
по одному модулю за сборку.

Готовый набор относительных путей (в `PropertyGroup Condition="'$(Base)'!=''"`):

```xml
<DCC_UnitSearchPath>PZR\Exif;PZR\FastDib;PZR\SQL;PZR\ZxLib;
Registr;Registr\Exif;Registr\Twain;Registr\SubForms;Registr\Interfaces;
Registr\SQL;Registr\ZxLib\Classes;Registr\Dx9Capture;Registr\Dx9Capture\DirectX;
Registr\DX.Pdfium4D;Maniac;Maniac2;JPERCompress;JPERCompress\Exif;
PhotoLoad;PhotoLoad\Exif;AccessDaemon;
Telegram\telegram-bot-delphi-main\src;Telegram\telegram-bot-delphi-main\src\Common;
lib\loggerpro</DCC_UnitSearchPath>
<DCC_ExeOutput>.\$(Platform)\$(Config)</DCC_ExeOutput>
<DCC_DcuOutput>.\$(Platform)\$(Config)\dcu</DCC_DcuOutput>
```

Без `DCC_ExeOutput` exe уезжает в корень проекта: сборка успешная, просто exe не там, где ждут.

**Поиск потерянного юнита — фактом, а не догадкой:**

```powershell
Get-ChildItem 'H:\OLD' -Recurse -Filter '<Unit>.pas' -File -ErrorAction SilentlyContinue |
  ForEach-Object { $_.FullName }
```

Одинаковые имена есть в нескольких подсистемах (`Exif` — в `PZR`, `Registr`, `PhotoLoad`, `JPERCompress`),
поэтому путь выбирается по факту вхождения в `uses` того модуля, который упал.

## 2. Таблица «ошибка → виновник → действие»

| Ошибка | Виновник | Действие |
|---|---|---|
| `E2064 Left side cannot be assigned to` | типизированная константа, которой присваивают в рантайме | `const` → `var` без инициализатора |
| `E2029 ',' or ':' expected but '=' found` после этой правки | инициализатор остался в `var`-секции | убрать `= N` |
| `E2029 Statement expected but 'INITIALIZATION' found` | `initialization` вставлен после `begin` главного блока | поставить вместо финального `end.` |
| `E2010 Incompatible types: 'AnsiChar' and 'Char'` в `frxXML.pas` | в путях `FR5\LibD24` (FastReport 5) | убрать `FR5*` из путей, брать FR 6 из COMPONENTS |
| `E2003 Undeclared identifier: 'NULL'` / `'VarToStr'` | в путях `ExcelExport\Source` (исходники стороннего SDK) | убрать каталог из путей |
| `F2613 Unit 'DelphiTwain'` | нужен `Registr\Twain` | добавить путь |
| `F2613 Unit 'FormAbout'` | нужен `Registr\Dx9Capture` | добавить путь |
| `F2613 Unit 'DX.Pdf.Viewer.VCL'` | нужен `Registr\DX.Pdfium4D` | добавить путь |
| `F2613 Unit 'LoggerPro'` | нужен `lib\loggerpro` | добавить путь |
| `F2613 Unit 'uTelegramAPI'` | нужен `Telegram\telegram-bot-delphi-main\src` | добавить путь |
| `F2613 Unit 'CCR.Exif.BaseUtils'` | нужен `PZR\Exif` | добавить путь |
| `F2039 Could not create output file` | exe занят запущенным процессом | закрыть приложение перед сборкой |

## 3. `E2064`: как выглядят такие константы

Шаблон в `implementation`:

```pascal
const
       idxGene: integer = 0;
       idxDisease: integer = 1;
       idxPosition = 4;        // без типа — тоже константа
```

а ниже в методах — `idxGene := SomeColumn.Index;`. Правильный вид:

```pascal
var
  idxGene: integer;
  idxDisease: integer;
  idxPosition: integer;
```

Менять блок только если имя реально стоит слева от `:=` где-то в модуле; иначе оставить `const`.

Динамический массив — только через `initialization`:

```pascal
var
  cYDNAmarkers: TArray<string>;

initialization
  cYDNAmarkers := ['YINDEL','DYS391','DYS570','DYS576','SRY',
                   'RS2032678','RS771783753','RS199815934'];

end.
```

## 4. Формы и датамодули в проекте

Модуль, подключённый только через `uses`, в дереве проекта — просто модуль, его форма не открывается.
Запись в `.dproj` (имя в `<Form>` — объект из первой строки `.dfm`, не класс):

```xml
<DCCReference Include="MG.Concl.Form.pas">
    <Form>ConclForm</Form>
</DCCReference>
<DCCReference Include="MG.Concl.Data.pas">
    <Form>ConclDataModule</Form>
</DCCReference>
```

Датамодуль (`TDataModule` + невизуальные `TFDMemTable`/`TDataSource`) — отдельный `.pas` + `.dfm`,
создаётся в `.dpr` через `Application.CreateForm` **до** главной формы:

```pascal
Application.CreateForm(TConclDataModule, ConclDataModule);
Application.CreateForm(TMainSystemForm, MainSystemForm);
```

Наборы открывать в `DataModuleCreate` (`if not mtPart.Active then mtPart.CreateDataSet;`), поля держать
в `FieldDefs` + `StoreDefs`, чтобы `FieldByName` работал без `AddFieldDef` в рантайме.

Переменное число колонок (по числу локусов) решается статикой с запасом: описать в `.dfm` `xy1..xy30`
плюс служебные колонки, лишние скрывать (`Columns[j].Visible := j <= Columns`). Создание колонок кодом
(`CreateAllItems`, `FieldDefs.AddFieldDef`, `CreateDataSet`) правилами проекта запрещено.

## 5. Проверка данных — запросами, а не глазами в GUI

Параметры подключения ЛИС берутся из `DModule.dfm` (`object FD1: TFDConnection`, `Params.Strings`):
PostgreSQL `<адрес из окружения>`, БД `MedicalDB`, пользователь `mgoffice`.

SQL расчёта заключения — `sql\concl\*.sql`, подставляются `TConclSqlCatalog` (`DefaultConclSqlDir`):
`order`, `analize`, `participants`, `samples`, `locuses`, `frequencies`, `race`, `relationship`,
`sample_type`, `partner_options`.

Имена параметров разные — не путать: `:Id`, `:IdOrder`, `:IdSample`, `:IdParticipant`.

Порядок проверки на живом заказе (номер заказа — это `"InnerId"`, не `"Number"`):

```sql
select "Id", "InnerId", "Number", "Status", "IdAnalize"
  from public."Order" where "InnerId" = 'MG24-184294';

select count(*) from public."Participant" where "IdOrder" = '<Order.Id>';
select count(*) from public."Sample" s join public."Participant" p
  on p."Id" = s."IdParticipant" where p."IdOrder" = '<Order.Id>';
select count(*), count(distinct "ProfileName") from public."Locus"
  where "IdSample" = '<Sample.Id>';
```

Ожидаемый профиль нормального заказа: 2 участника, 3 образца, 112 локусов в 4 профилях, колонки
`X`/`Y` заполнены, `ProfileName` различает прогоны.

## 6. Что считать результатом

```
EXIT=0  И  свежий LastWriteTime у Win32\<Config>\<Проект>.exe  И  ~341 warning (нормальный фон)
```

Проверка «форма попала в exe» без запуска — поиск строк по бинарнику:

```powershell
$t = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($exe))
'TfrConclForm: ' + ([regex]::Matches($t,'TfrConclForm')).Count
'TConclDataModule: ' + ([regex]::Matches($t,'TConclDataModule')).Count
```

Ноль вхождений имени класса формы = форма не слинкована (не попала в `uses`/`.dpr`) — собирать заново.
