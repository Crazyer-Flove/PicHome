"""Offline UI integration verification; all GitHub responses are simulated."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import io
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QImage, QDropEvent
from PySide6.QtWidgets import QApplication
import core
import app
from test_core import PNG, CFG

def response(request, **kwargs):
    if request.method == 'PUT':
        return io.StringIO(json.dumps({'commit': {'sha': 'a' * 40}}))
    return io.StringIO(json.dumps({'private': False}))

a = QApplication([])
app.init_fonts()
a.setStyle('Fusion')
a.setStyleSheet(app.STYLE)
with tempfile.TemporaryDirectory(dir='.') as folder, patch.object(core, 'APP_DIR', Path(folder)), patch.object(core, 'urlopen', side_effect=response):
    core.save_config(CFG)
    w = app.Window()
    w.show()
    image = QImage(60, 40, QImage.Format_RGB32)
    image.fill(Qt.green)
    image_path = str(Path(folder).resolve() / 'sample.png')
    image.save(image_path)
    with patch.object(app.QFileDialog, 'getOpenFileNames', return_value=([image_path], '')):
        w.choose_files()
    a.clipboard().setImage(image)
    w.paste()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(image_path)])
    drop = QDropEvent(QPointF(30, 30), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    zone = w.findChild(app.DropZone)
    zone.dropEvent(drop)
    deadline = time.monotonic() + 15
    while (w.busy or w.queue) and time.monotonic() < deadline:
        a.processEvents()
        time.sleep(.01)
    assert len(w.history) == 3, len(w.history)
    assert len({r['path'] for r in w.history}) == 3
    w.copy(w.history[0]['url'])
    assert a.clipboard().text() == w.history[0]['url']
    w.copy_all()
    assert a.clipboard().text().count('https://') == 3
    settings = app.Settings(w)
    settings.show()
    a.processEvents()
    settings.grab().save('settings-preview.png')
    settings.close()
    w.grab().save('history-preview.png')
    w.history = []
    w.render_history()
    a.processEvents()
    w.grab().save('preview.png')
    w.close()
print('PASS: file picker, clipboard screenshot, file drop, serial upload, history, direct link and Markdown copy; mocked GitHub')
