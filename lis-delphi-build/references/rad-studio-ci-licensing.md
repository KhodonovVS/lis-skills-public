# RAD Studio: условия автосборки и установка на build-сервер

Собрано при проработке сервера автосборки Delphi — проверено по EULA Embarcadero и docwiki.

## Лицензионные условия (EULA, раздел 2.4 «Command Line Compiler»)

- Командный компилятор РАЗРЕШЕНО ставить на отдельной машине от продукта, если её единственная цель —
  unattended (автоматическая) сборка приложений. Build-сервер — легальный, предусмотренный сценарий
  (для профессиональных редакций и выше).
- Community Edition: перенос командного компилятора на другую машину ЗАПРЕЩЁН (раздел 2.4 к ней не применяется) —
  для автосборки Community не подходит.
- Несколько сборщиков — сетевые лицензии: Network Named / Network Concurrent через license server
  (Embarcadero License Center).
- Документация Embarcadero прямо поддерживает CI: сборка через командную строку MSBuild для «CI, build servers»
  — штатный сценарий (см. docwiki BCC64X, `--jobs=0` = все ядра).

## Тихое развёртывание на ВМ сборки

- Silent install: `setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SLIPFILE=license.slip /FEATURES=delphi;cbuilder`
  — лицензионный файл (.slip или reg*.txt) ставится до/вместе с продуктом.
- Доустановка платформ и фич — `GetItCmd.exe` (`-c=useonline|useoffline`).
- Лицензия/серийник должны быть где взять ДО установки: если в сейфах записи нет — запросить у BOSS
  и положить в Vaultwarden («RAD Studio <версия>»), чтобы стенд не встал посреди развёртывания.

## Питфолл: trial-компилятор в CLI

- Ошибка «This version of the product does not support command line compiling» при ВАЛИДНОЙ лицензии =
  в `<Studio>\bin` остался trial-dcc32 из mini-IDE (антивирус/прерванная установка помешали замене).
  Фикс: скопировать настоящий компилятор из
  `C:\Users\Public\Documents\Embarcadero\Studio\<ver>\CatalogRepository\Core_Common_Files_<Edition>-<ver>…\TARGETDIR\bin`.
- Проверять до запуска конвейера: реальная сборка маленького .dpr из командной строки.

## Практика для конвейера

- Сборка — msbuild по `.dproj` (как в IDE); CLI-компилятор версии N принимает только свои bpl:
  несовпадение версии пакетов и IDE даёт E2225 «must be recompiled».
- Кэш bpl/dcp строится по ключу «SHA компонент + версия Delphi + платформа» — установленные
  пакеты и порядок их сборки для каждой версии IDE держать в манифесте (топосорт по `requires`).
