@echo off

set PI="C:\\Tools\\pyinstaller-2.0\\pyinstaller.py"
REM Записываем версию утилиты из ревизии
copy /Y upgrade.py upgrade.py.dev
SubWCRev . upgrade.py.dev upgrade.py
REM Пакуем утилиту в самодостаточный файл.
python.exe %PI% upgrader.spec
copy /Y upgrade.py.dev upgrade.py
rd /Q /S build