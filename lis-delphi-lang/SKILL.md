---
name: lis-delphi-lang
description: "Use when writing, reviewing or fixing Delphi/Object Pascal в нашем контуре: Delphi 10.3 (Studio 20.0), VCL + DevExpress, FireDAC, DFM-only. Проверка API по исходникам 20.0, стиль, память, строки, исключения, generics/RTTI, потоки."
---

# Delphi / Object Pascal в нашем контуре — правила и проверка API

Источник базы: открытые скиллы Daniele Teti `daniele-teti/delphi-ai-skills` (Apache-2.0), адаптированы под наш проект.

## Наш таргет — жёстко

| Что | Значение |
|---|---|
| Компилятор | **Delphi 10.3 Rio, Studio 20.0** (product version 20). Ничего новее 10.3 не использовать |
| Исходники RTL/VCL для сверки | `C:\Program Files (x86)\Embarcadero\Studio\20.0\source\rtl\sys|common`, `...\source\vcl` |
| UI | VCL + DevExpress; компоненты — **только в DFM**, никакой динамики, если можно положить в форму |
| Данные | FireDAC: `TFDQuery`/`TFDMemTable`/`TDataSource` на датамодуле; SQL — параметризованный, LocalSQL запрещён |
| Кодировки | `.pas/.dpr/.dpk/.inc` — UTF-8 **с BOM**; `.dfm/.lfm` — ANSI CP1251 с escape-кириллицей |
| Комментарии | по-русски; для процедур/функций — XML-документация `/// <summary>` |

## Когда сомневаешься в API — проверяй, не угадывай

Плаузибельно-неверный идентификатор RTL стоит компиляционной ошибки и доверия. Не отвечай по памяти. Порядок:

1. **Исходники нужной версии** (`...\Studio\20.0\source\...`). Дерево 20.0 — единственное, по которому проверяем:
   `System.pas`, `System.SysUtils.pas`, `System.Classes.pas`, `System.Generics.*`, `System.Rtti.pas`,
   `System.Threading.pas`, `System.JSON.pas`, `Vcl.Forms.pas`, `Vcl.Controls.pas`.
2. **DocWiki именно 10.3**: `https://docwiki.embarcadero.com/RADStudio/Rio/en/...`
   (не Florence/Athens — там API новее, чем у нас).
3. **Реальный call site**: объявление даёт арность и типы, а владение, время жизни и порядок вызовов —
   только место вызова. Смотри свой код проекта, потом исходники RTL (там всё используется), потом примеры DocWiki.
4. **Не смог проверить — так и скажи.** «Не уверен, что `TFoo.Bar` есть в 10.3 — проверь System.Classes.pas» — полезный ответ.

## Что категорически нельзя

- Возможности Delphi 11/12/13 (inline var там, где 10.3 не умеет, новые RTL-типы, `TObject`-хелперы из новых версий).
- Динамическое создание компонентов, если компонент можно положить в DFM.
- Строки SQL, склеенные конкатенацией со значениями (только параметры).
- Сборка более одной за раз (`/opt/work/build.sh`, flock) и сборка в обход WORKST.

## Reference (локально, читать по теме)

- `references/style.md` — стиль и именование
- `references/memory.md` — владение, Free, try/finally, интерфейсы, managed records
- `references/strings.md` — строки и кодировки
- `references/exceptions.md` — исключения
- `references/generics-and-rtti.md` — дженерики и RTTI
- `references/concurrency.md` — потоки
