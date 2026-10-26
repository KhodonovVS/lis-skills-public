# Среда сборки Delphi на WORKST (проект medicalgenomics)

Машина: WORKST <адрес из окружения> (управление — `workst_ps.py`, креды `pass pdc`).

## Версии
- **RAD Studio 10.3.3 Rio (BDS 20.0)** — основная; под неё собраны все компоненты (суффиксы пакетов RS26 / *260 / *_xe103).
- **RAD Studio 13 (BDS 37.0)** — установлена дополнительно, компоненты не накатаны.
- PATH (Machine) содержит обе Studio (bin/bin64) и Public Bpl (20.0/37.0).

## Точки входа (H:\medicalgenomics, репо Mercurial; git-зеркало — agents/medicalgenomics)
- **Registr\registr.dproj** — «папка register» (словами BOSS) — точка сборки программы; рядом
  MG2Launcher\MedicalGenomics2.dproj, Dx9Capture.
- MG.dproj — в корне репы.
- Сателлиты (dproj): AccessDaemon, CEF4\packages, Doctors\DCTRS, Email\DelphiEmail, EmailDaemon,
  Eprint/ESend, ExcelExport\QExport4*, FR5\LibD24, HACOC(+svc), Invitro, JPERCompress, KdfJson и др.

## Компоненты
- Собранные bpl/dcp: `C:\Users\Public\Documents\Embarcadero\Studio\20.0\{Bpl,DCP}` (~210 bpl): DevExpress VCL
  (RS26), EhLib260, Graphics32 (GR103), HTML Component Library (xe103), EMS QExport4*/QImport3*.
- Исходники: `H:\COMPONENTS` (DevExpress VCL, DISTR, EhLIB, EMS Export/Import, graphics32-master, HTML Component
  Library) + inline в репе (CEF4, DebenuPDF, FR5, HACOC, JPERCompress, DirectXDelphiWebcamCapture, ExcelExport…).
- **FastReport**: FR5 — исходники в репе (FR5\LibD24); **FR6 VCL Enterprise 6.9.3** — установлен
  (`C:\Program Files (x86)\FastReport 6 VCL Enterprise`, LibD26 под 10.3.3, есть recompile.exe), дистрибутив+ключ —
  `H:\COMPONENTS\DISTR`; staging-копия — CT169:`/root/staging/components/FR6`.
  ⚠️ FR6.9.3 покрывает только ≤ Delphi 10.4. Для **Delphi 12/13** нужен FastReport VCL **2025.2.8+/2026.x**
  (актуальная 2026.2.4) — из личного кабинета fast-report.com (лицензия BOSS).
- «Known Packages» в хайве профиля boss не читается — список design-time пакетов снимать по bpl/dpk или из IDE.

## Конвенция автосборки (решения BOSS)
- Версия компонент фиксируется **пин-файлом** (`components.pin` — SHA коммита репы компонент): компоненты
  собираются только при смене пина; кэш bpl/dcp с ключом SHA(компоненты)+Delphi+платформа; конвейер
  «компоненты → программа»; оркестрация — Gitea Actions.
- Порядок сборки каждого компонента (пакет → install-пакет; DevExpress — строго по их порядку) и структура
  каталогов — в проектном документе архитектора в workbench (`tasks/<CMP>/`).
