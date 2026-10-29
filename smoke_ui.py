"""Offline UI integration verification; all GitHub responses are simulated."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import io
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QMimeData, QUrl, QPointF, Qt, QEvent
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
    w.backup_folder = str(Path(folder).resolve() / 'backups')
    w.backup_toggle.setChecked(True)
    with patch.object(app.QFileDialog, 'getOpenFileNames', return_value=([image_path], '')):
        w.choose_files()
    w.backup_toggle.setChecked(False)
    a.clipboard().setImage(image)
    w.paste()
    w.backup_toggle.setChecked(True)
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
    assert sum(bool(r.get('backup_path')) for r in w.history) == 2
    for r in w.history:
        if r.get('backup_path'):
            assert Path(r['backup_path']).is_file()
            assert Path(r['backup_path'] + '.json').is_file()
    w.copy(w.history[0]['url'])
    assert a.clipboard().text() == w.history[0]['url']
    w.copy_all()
    assert a.clipboard().text().count('https://') == 3
    assert len(core.read_json('history.json', [])) == 3
    w.show_library()
    library = w.library
    library.table.selectRow(0)
    library.copy_selected('url')
    assert a.clipboard().text() == w.history[0]['url']
    library.copy_selected('markdown')
    assert a.clipboard().text() == w.history[0]['markdown']
    library.search.setText('截图')
    assert len(library.filtered) == 1
    export_path = str(Path(folder) / 'links.csv')
    with patch.object(app.QFileDialog, 'getSaveFileName', return_value=(export_path, '')):
        library.export_links()
    import csv
    with open(export_path, encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 2 and rows[1][2] == library.filtered[0]['url']
    library.search.clear()
    original_history = w.history.copy()
    w.history = [dict(original_history[0], name=f'history-{i}.png') for i in range(505)]
    w.uploaded(dict(original_history[0], name='new.png'))
    assert len(core.read_json('history.json', [])) == 506
    assert len(library.visible) == 100
    library.change_page(5)
    assert len(library.visible) == 6
    w.history = original_history
    library.refresh()
    for _ in range(8): a.processEvents()
    library.grab().save('library-preview.png')
    library.close()
    w.render_history()
    settings = app.Settings(w)
    settings.show()
    a.processEvents()
    settings.grab().save('settings-preview.png')
    settings.close()
    for _ in range(8): a.processEvents()
    cards = [w.card_layout.itemAt(i).widget() for i in range(w.card_layout.count())]
    assert all(b.y() >= a.y() + a.height() for a, b in zip(cards, cards[1:]))
    w.grab().save('history-preview.png')
    w.history = []
    w.render_history()
    w.backup_toggle.setChecked(False)
    w.backup_label.setText('未选择备份目录 · 备份包含原图与对应链接信息')
    w.status.setText('就绪 · 图片公开可访问 · 单张最大 20 MB')
    a.sendPostedEvents(None, QEvent.DeferredDelete)
    for _ in range(12): a.processEvents()
    w.grab().save('preview.png')
    w.close()
print('PASS: upload entry points, optional per-batch image/link backup, persistent unlimited history, library pagination/search/copy/CSV export; mocked GitHub')
