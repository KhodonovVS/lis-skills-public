# Восстановление файлов Delphi после порчи кодировки

Реальный случай: сессия CR00028049. Агент отредактировал .pas и .dfm,
прочитав их как UTF-8 и сохранив обратно. Вся cp1251-кириллица в .pas
превратилась в U+FFFD.

## Шаг 1: диагностика

```bash
# Какие файлы изменены в проблемном коммите
git show --stat <broken_commit>

# Проверка file
file Inclusion/fuPortfolio.pas Inclusion/fuPortfolio.dfm
# Ожидаем: ASCII text / ISO-8859
# Если: Unicode text, UTF-8 text — проблема

# Проверка U+FFFD в PAS
python3 -c "
with open('Inclusion/fuPortfolio.pas', 'rb') as f:
    data = f.read()
print('U+FFFD:', data.count(b'\xef\xbf\xbd'))
"

# Проверка UTF-8 кириллицы в DFM
python3 -c "
with open('Inclusion/fuPortfolio.dfm', 'rb') as f:
    data = f.read()
utf8 = 0
for i in range(len(data)-1):
    if 0xD0 <= data[i] <= 0xD4 and 0x80 <= data[i+1] <= 0xBF:
        utf8 += 1
print('UTF-8 cyrillic:', utf8)
"
```

## Шаг 2: восстановление PAS

Для PAS: восстановить оригинал из родительского коммита и заново
применить только ASCII/latin-изменения (без кириллицы).

```bash
# Восстановить оригинал
git checkout <parent_commit> -- Inclusion/fuPortfolio.pas

# Получить diff для анализа
git diff <parent_commit>..<broken_commit> -- Inclusion/fuPortfolio.pas > /tmp/diff.pas
```

Затем через Python:
- Прочитать восстановленный файл в cp1251
- Найти в diff'е строки, добавленные БЕЗ кириллицы (только латиница/цифры)
- Вставить их в нужные места
- Сохранить в cp1251

```python
with open('file.pas', 'r', encoding='cp1251') as f:
    lines = f.readlines()

# Вставка: lines.insert(position, new_line)
# Например:
for i, line in enumerate(lines):
    if line.rstrip() == '    cbxUsePeriod: TMalCheckBox;':
        lines.insert(i+1, '    cbxNotShippedFromFactory: TMalCheckBox;\n')
        break

with open('file.pas', 'w', encoding='cp1251') as f:
    f.writelines(lines)
```

## Шаг 3: восстановление DFM

Для DFM: два подхода.

### Подход A — прямой русский текст только в SQL-комментариях

Если русский текст в DFM только в SQL-комментариях (не в #-нотации),
можно взять битый файл и заменить UTF-8 → cp1251:

```bash
git show <broken_commit>:Inclusion/fuPortfolio.dfm > /tmp/broken.dfm
```

```python
with open('/tmp/broken.dfm', 'rb') as f:
    data = f.read()

# Замена UTF-8 → cp1251 для каждого комментария
old = ' -- transit (Транзитный ...)'.encode('utf-8')
new = ' -- transit (Транзитный ...)'.encode('cp1251')
data = data.replace(old, new)
```

### Подход B — #-нотация не повреждена

Если русский текст в DFM только в #-нотации (без прямых символов),
файл можно использовать как есть — #-нотация бинарно-безопасна.

Проверка: `grep -P '[А-Яа-яЁё]' file.dfm` (прямые русские символы)
или `python3 -c "..."` (UTF-8 кириллица).

## Шаг 4: финальная проверка

```bash
# PAS: 0 кракозябр
python3 -c "
with open('file.pas', 'rb') as f:
    d = f.read()
print('U+FFFD:', d.count(b'\xef\xbf\xbd'))
"

# PAS: cp1251 кириллица на месте
python3 -c "
with open('file.pas', 'rb') as f:
    d = f.read()
# 'Обратитесь' в cp1251
target = bytes([0xce, 0xe1, 0xf0, 0xe0, 0xf2, 0xe8, 0xf2, 0xe5, 0xf1, 0xfc])
print('OK' if target in d else 'MISSING')
"

# DFM: 0 UTF-8 кириллицы
python3 -c "
with open('file.dfm', 'rb') as f:
    d = f.read()
n = 0
for i in range(len(d)-1):
    if 0xD0 <= d[i] <= 0xD4 and 0x80 <= d[i+1] <= 0xBF:
        n += 1
print('UTF-8 cyrillic:', n, '(should be 0)')
"

# Наши добавления присутствуют
grep -c 'transit_tns' file.pas file.dfm
grep -c 'cbxNotShippedFromFactory' file.pas file.dfm
```

## Результат

После исправления: коммит с amend + force push:
```bash
git commit --amend -m "..."   # новый коммит взамен битого
git push --force-with-lease origin <branch>
```
