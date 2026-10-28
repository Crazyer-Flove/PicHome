$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path .venv\Scripts\python.exe)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe -m unittest -v test_core
if ($LASTEXITCODE) { throw 'Tests failed' }
& .\.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; from app import make_icon,init_fonts; a=QApplication([]); init_fonts(); make_icon().pixmap(128,128).save('luma.ico')"
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name Luma --icon luma.ico app.py
if ($LASTEXITCODE) { throw 'Build failed' }
