# Данные стенда ЛИС (MedicalDB, <адрес из окружения>)

PostgreSQL **9.4.26**, база `MedicalDB`, схема `public`, 91 таблица. Пользователь `mgoffice`
имеет INSERT/UPDATE/DELETE/CREATE. Боевую <адрес из окружения>/MedicalDB на чтение не трогать.

Таблицы, которые реально используются в задачах WP-119..123:

| Таблица | Назначение |
|---|---|
| `Order` | заказ (шапка исследования), ключ — `TGUID` |
| `OrdersMain` | основная запись заказа |
| `Locus` | локусы (набор, порядок) |
| `LocusOrder` | порядок локусов в наборе |
| `judExpCLForOrder` | экспертиза/заключение по заказу |
| `ConclMethod` (public."ConclMethod") | справочник методов расчёта, поле `treeMethodParticipants` |
| `ConclResult*` (создаётся миграцией) | сохранённый результат: шапка + версии + строки локусов |

Правила: только параметризованные запросы (FireDAC `ParamByName`, типы `ftGUID/ftFloat/ftDateTime`),
`Prepared := True`, транзакция на запись, `Rollback` в `except`; `LocalSQL` не использовать.
