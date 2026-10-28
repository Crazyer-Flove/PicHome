$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path .venv\Scripts\python.exe)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe -m unittest -v test_core
if ($LASTEXITCODE) { throw 'Tests failed' }
& .\.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; from app import make_icon,init_fonts; a=QApplication([]); init_fonts(); make_icon().pixmap(128,128).save('luma.ico')"
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
$lumaSslData = & .\.venv\Scripts\python.exe -c "import ssl; from pathlib import Path; p=Path(ssl.__file__).with_name('codex-rejected-cas.pem'); print(str(p) if p.exists() else '')"
$lumaDataArgs = @()
if ($lumaSslData) { $lumaDataArgs = @('--add-data', "$lumaSslData;.") }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name Luma --icon luma.ico @lumaDataArgs app.py
if ($LASTEXITCODE) { throw 'Build failed' }
