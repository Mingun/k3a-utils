# -*- encoding: utf-8 -*-
# -*- mode: python -*-
# Скрипт сборки updater-а для PyInstaller.
from glob import glob
a = Analysis([# Список основных файлов апгрейдера.
             'k3a.py',
             'Parser.py',
             'upgrade.py',
             ],
             pathex=['C:\\Tools\\pyinstaller-2.0'],
             # Список неявно импортируемых модулей-плагинов апгрейдера.
             hiddenimports=map(lambda x: '.'.join(x.split('.')[:-1]), glob('upgrade-*.py')),
             hookspath=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('upgrader.exe'),
          debug=False,
          strip=None,
          upx=True,
          console=True )
