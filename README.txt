Здесь хранятся скрипты обновлений проектов K3A при несовместимых изменениях в библиотеке TXSST.

make_upgrader.bat создает исполняемый файл upgrader.exe, который является самодостаточным.
Для его создания необходим модуль PyInstaller (http://www.pyinstaller.org/), которому, в
свою очередь, требуется PyWin32 (http://sourceforge.net/projects/pywin32/files/pywin32/).

upgrader.spec - файл конфигурации для скрипта сборки.