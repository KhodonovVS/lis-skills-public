# RAD Studio — установка и кейпатч (материалы из раздач RuTracker)

Собрано 03.10.2026: `/soft/Delphi/RADStudio/_АКТИВАЦИЯ/` — KeyPatch для всех версий (10.3.3…13.2),
пароли к архивам в одноимённых .txt, инструкции: `instrukcia_10.4.txt`, `instrukcia_13.x.txt`, README.
Дистрибутивы: `/soft/Delphi/RADStudio/` (10.3.3: `delphicbuilder10_3_3_7899_nt.iso`; 10.4; 12.0–12.3; 13.0–13.2).

## Порядок установки (по инструкциям раздач)
1. Чистая ВМ. ДО установки: Java JRE+JDK и Windows SDK (есть в раздачах) → перезагрузка.
2. Windows Defender ОТКЛЮЧИТЬ (ругается на KeyPatch/файлы раздачи), исключения на папки.
3. KeyPatch запустить ДО установки: ПКМ в заголовке окна → «Block servers in the hosts file» (блокирует сервера активации).
4. Смонтировать ISO → установщик от администратора → дойти до страницы «Ввода лицензии» (НЕ жать Install).
5. В KeyPatch «PATCH» → в установщике «Back» → «Use Existing License» → продолжить установку.
6. Проверить сборку тестового проекта из командной строки (smoke).

## Состав установки (решение BOSS 03.10.2026)
Только Delphi (C++Builder НЕ ставить); платформы Windows 32/64 + Linux; мобильная разработка (Android/iOS) — НЕ нужна.
Диск стенда — с запасом на 4 версии IDE: 10.3.3 + 10.4 + 12 + 13.

## Питфоллы
- CLI-компилятор: если `dcc32` из «trial»-набора (mini-IDE) — командная строка падает
  («This version of the product does not support command line compiling»); заменить файл из CatalogRepository.
- EULA (п.2.4): командный компилятор на отдельной машине разрешён для unattended-сборок (Community Edition — нельзя).
- Silent install: `setup.exe /VERYSILENT /SLIPFILE=<license.slip|reg*.txt> /FEATURES=delphi;cbuilder` + `GetItCmd.exe` для платформ.
- В 10.3.3-раздаче лежит `RADStudioKeyPatch_Lite.exe`; в 10.4+/12/13 — `*KeyPatch.rar` + пароль в .txt.
