# Агентская разработка на Delphi (Codex / Claude Code)

Задача: агент не просто «пишет Object Pascal», а правит код в проекте на 1500 юнитов и проверяет себя компилятором.
Без навигации и сборки он галлюцинирует: синтаксис выглядит правильным, проект не собирается.

## Что должно быть подключено

| Слой | Зачем | Без него |
|---|---|---|
| Language Server (`delphi-lsp`) | определения, ссылки, состав класса, ошибки по ходу | агент ищет символ grep'ом по 1500 файлам и путает омонимы |
| Сборка (`dcc32` / `msbuild`) | реальные ошибки компиляции | «готово» без доказательства |
| Тесты (DUnit/DUnitX) | проверка поведения, а не синтаксиса | правки проходят компилятор и ломают логику |

Правило: **сначала сборка, потом diff.** Агент, который не видел вывода компилятора, работу не сдал.

## Проверенные пути (WORKST, Windows)

Проверять перед использованием — версии ставятся рядом и не удаляются:

- RAD Studio: `C:\Program Files (x86)\Embarcadero\Studio\20.0`, `…\37.0` (две версии одновременно).
- `dcc32` 37.0: `…\Studio\37.0\bin\dcc32.exe` и `…\Studio\37.0\bin64\dcc32.exe`;
  `dcc32.exe` без аргументов печатает `Embarcadero Delphi for Win32 compiler version 37.0` — быстрая проверка версии.
- Окружение сборки: `…\Studio\37.0\bin\rsvars.bat` (задаёт BDS, FrameworkDir, PATH для MSBuild-сборки).
- **MSBuild в комплекте Studio НЕ лежит** — брать `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe`
  (проверять наличие: в `…\Studio\37.0\bin` его нет).
- Delphi LSP MCP: `C:\Users\boss\.mcp\src\delphi-lsp-mcp\DelphiLSPMCPServer.exe`
  (`--lsp-path "…\Studio\37.0\bin64\DelphiLSP.exe" --workspace <корень проекта>`).
- Проект МГ: `H:\OLD\medicalgenomics` — `MG.dproj`, `MGSystem.dproj`, `Project2.dproj`, `CEF4Delphi.dproj`, ~1492 `.pas`.

## Подключение

Codex (`~/.codex/config.toml`, бэкап перед правкой):

```toml
[mcp_servers.delphi-lsp]
command = "C:\\Users\\boss\\.mcp\\src\\delphi-lsp-mcp\\DelphiLSPMCPServer.exe"
args = ["--lsp-path", "C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0\\bin64\\DelphiLSP.exe",
        "--workspace", "H:\\OLD\\medicalgenomics"]
```

Claude Code — отдельный профиль, а не постоянный набор: файл `mcp-delphi.json` (`{"mcpServers": {…}}`)
с `delphi-lsp`, сборкой, `git` и доступом к БД, запуск
`claude --mcp-config mcp-delphi.json --strict-mcp-config`. Профиль стоит ~12K токенов контекста на старте,
поэтому держать его вне базового набора и включать только на Delphi-задачах.

## Цикл работы

```cmd
rem 1. быстрая проверка одного юнита (секунды)
"C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc32.exe" -B -U"…\Common" -N"…\dcu" Unit1.pas

rem 2. проект целиком (через rsvars, иначе нет путей к VCL)
call "C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\rsvars.bat"
"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe" MG.dproj /p:Config=Debug /p:Platform=Win32
```

`EXITCODE 0` — единственное доказательство сборки; вывод компилятора отдавать агенту целиком (файл:строка + код ошибки).

## Ловушки

- **Кодировки в одном дереве разные.** Часть `.pas` — ANSI (байты 0xC0–0xFF, cp1251), `.dproj` — UTF-8 с BOM
  (`EF BB BF`). Агент по умолчанию пишет UTF-8 и превращает русские литералы в мусор; ошибка видна только в рантайме.
  Перед правкой смотреть байты файла и сохранять в его кодировке.
- **`.dfm` не переписывать текстом** — формы регенерирует IDE; агент правит `.pas`, разметку формы не трогает.
- **Версия компилятора и LSP должна совпадать с версией проекта.** 20.0 и 37.0 стоят рядом; чужой компилятор даёт
  ошибки, которых в проекте нет.
- **Sandbox агента блокирует сборку.** Codex по умолчанию без права записи/сети — сборка падает на правах, а не на коде;
  для сборочных прогонов давать workspace-write (или явный bypass) и не держать это включённым постоянно.
- **Знание языка у модели вторично.** Даже сильная модель пишет VCL/FireDAC/CEF4Delphi правдоподобно и неверно;
  компилятор и тесты — единственный фильтр. Задачи формулировать так, чтобы результат был проверяемым (собралось, тест зелёный).
