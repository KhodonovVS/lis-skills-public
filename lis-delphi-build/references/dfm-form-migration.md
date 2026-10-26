# Перевод формы из кода в DFM

Когда применять: форма собирает компоненты в конструкторе/`BuildUI` (поля `FCbMode: TcxComboBox`,
`FBtnCalc: TcxButton`, `FTreeMethod: TcxDBTreeList`), а требование — всё описание в `.dfm`.

## 1. Снять инвентарь из кода

Из `BuildUI` (или конструктора) выписать по каждому компоненту: тип, имя, родитель (layout-группа),
подпись, размеры, события, свойства данных (`DataController.DataSource`, `FieldDefs`, `Properties.ReadOnly`).
Отдельно — layout-структуру: какие `TdxLayoutGroup` вложены, направление (`ldHorizontal`/`ldVertical`),
`CaptionOptions.Text`, `SizeOptions.Width/Height`, `AlignVert`.

## 2. Сгенерировать `.dfm` скриптом, не руками

Кириллицу писать escape-последовательностями (`#1043#1077…`) — тогда файл получается чистым ASCII и
читается любой версией Delphi независимо от кодировки. Мелкий генератор на Python с функцией
`dfm_str(s) -> "'chunk' + #NNNN …"` надёжнее ручной правки: одинаковые блоки колонок/групп
собираются циклами.

Структура, которая проходит:

```text
object ConclForm: TfrConclForm
  ...
  object layout: TdxLayoutControl
    object lblInfo: TcxLabel ... end
    object cbMode: TcxComboBox  Properties.Items.Strings = (…)  ItemIndex = 2  end
    object treeMethod: TcxDBTreeList
      object treeMethodCaption: TcxDBTreeListColumn  DataBinding.FieldName = 'Caption'  end
    end
    object gridPart: TcxGrid
      object gridPartView: TcxGridDBTableView  DataController.DataSource = dsPart  end
      object gridPartLevel: TcxGridLevel  GridView = gridPartView  end
    end
    object layoutGroup_Root: TdxLayoutGroup  Index = -1  end
    object grpTop: TdxLayoutGroup  Parent = layoutGroup_Root  LayoutDirection = ldHorizontal  Index = 0  end
    object layoutItemTree: TdxLayoutItem  Parent = grpLeft  Control = treeMethod  Index = 0  end
  end
  object mtPart: TFDMemTable  FieldDefs = < item Name = 'No' DataType = ftInteger end >  StoreDefs = True  end
  object dsPart: TDataSource  DataSet = mtPart  end
end
```

Грид-вью и уровень — **подобъекты** грида, таблица и датасорс — соседи верхнего уровня.
`TFDMemTable` с `StoreDefs = True` избавляет от `FieldDefs.Add` в коде.

## 3. Переписать `.pas`

- Компоненты становятся published-полями класса формы (первая секция без модификатора) и называются по
  соглашению: `cbMode`, `btnCalc`, `gridPart`, `memoResult`, `mtPart`, `dsPart`.
- Удалить `BuildUI`, `CreateNew`-override и все `Create`/`Parent :=`/`Left/Top`.
- Настройка данных (`FillMethodData`, привязка `DataController.DataSource`, `KeyField`/`ParentField`)
  остаётся в коде — это логика, а не описание компонентов.
- `uses` держать раздельно: базовые VCL/cx/dx/FireDAC и `MG.Concl.*` — в interface;
  `System.Math`, `System.IOUtils`, `frxClass`, `MG.Concl.Text.Results`, `*.Report*`, `*.Export.FR`, `MG.Log` —
  в implementation. Дублировать `System.Variants` в двух `uses` нельзя — `E2004 Identifier redeclared`.

## 4. Точка вызова: `CreateNew` → `Create`

`TForm.CreateNew` **не загружает ресурс формы** — с ним `.dfm` просто игнорируется, и форма откроется
пустой или упадёт. В месте создания писать `Form := TfrConclForm.Create(Self)` (или `Create(Application)`).
Это самая частая причина «форма есть в DFM, а в программе её нет».

## 5. Допустимое исключение

Колонки, число которых задаёт модель (локусы в результате, произвольный набор полей), остаются
генерируемыми в рантайме (`CreateAllItems`). В коде это отмечается комментарием, что состав колонок
определяется данными, а не DFM, — иначе следующая проверка «почему здесь динамика» снова поднимет вопрос.

## 6. Проверка

1. `MSBuild <проект>.dproj /p:Config=TestBuild|Debug` → `EXIT=0`, ошибок 0.
2. В `.dproj` есть `DCCReference` на модуль формы с `<Form>Имя</Form>` — иначе формы не видно в дереве.
3. Открыть форму в программе (кнопкой, которая её вызывает) — визуальная проверка обязательна:
   layout-группы, высоты дерева/memo. Правки пропорций — правка `.dfm`, не кода.

## Грабли

- Забытый `System.Variants` в implementation → `E2004`.
- Класс вроде `TConclResultFormulasFormatter` лежит в `*.Text.Results`, а не в `*.Text` → `E2003 Undeclared identifier`
  и каскад `F2063 Could not compile used unit`.
- Если exe запущен, сборка падает `F2039 Could not create output file` — не ошибка кода, закрыть приложение.
- После переименования формы/компонентов синхронизировать четыре места: `.pas` (класс, переменная, все
  `TFormN.Метод`), `.dfm` (`object`), `.dpr` (`{FormN}` и `CreateForm`), `.dproj` (`<Form>`).
