import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QBuffer, QIODevice, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QKeySequence, QShortcut, QPixmap, QIcon, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QLineEdit, QDialog, QFormLayout, QMessageBox, QProgressBar, QLayout,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from core import load_config, save_config, read_json, write_json, upload_with_backup, check_connection, validate_config, MAX_BYTES

STYLE = '''
QWidget { background:#f7f8fa; color:#202b35; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:14px; }
QLabel#brand {font-size:28px; font-weight:600; letter-spacing:3px;}
QLabel#title {font-size:29px; font-weight:600;}
QLabel#muted {color:#657583; font-size:13px;}
QFrame#drop {border:1px dashed #c2d4cc; border-radius:18px; background:#ffffff;}
QFrame#drop QLabel {background:transparent;}
QFrame#card {background:#ffffff; border:1px solid #e1e7eb; border-radius:12px;}
QFrame#card QLabel {background:transparent;}
QPushButton {background:#ffffff; border:1px solid #dce3e7; border-radius:8px; padding:10px 17px;}
QPushButton:hover {background:#eef5f1; border-color:#9cbfaf;}
QPushButton:pressed {background:#e0ece5;}
QPushButton:focus {border:1px solid #34795d;}
QPushButton:disabled {color:#8b969e; background:#f0f2f4; border-color:#e5e9ec;}
QPushButton#primary {background:#246b50; color:#ffffff; border:1px solid #246b50; font-weight:600;}
QPushButton#primary:hover {background:#1a573f;}
QLineEdit {background:#ffffff; border:1px solid #dce3e7; border-radius:7px; padding:10px; selection-background-color:#d4e8dc; selection-color:#183c2b;}
QLineEdit:focus {border-color:#34795d;}
QScrollArea {border:0;}
QProgressBar {border:0; background:#e4ebe7; height:3px; border-radius:1px;}
QProgressBar::chunk {background:#34795d;}
QScrollBar:vertical {background:#f7f8fa; width:8px;}
QScrollBar::handle:vertical {background:#c6d1cd; min-height:30px; border-radius:4px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QTableWidget {background:#ffffff; gridline-color:#edf0f2; border:1px solid #e1e7eb; selection-background-color:#dfede5; selection-color:#183c2b;}
QTableWidget::item {padding:8px;}
QHeaderView::section {background:#eef3f0; color:#40594c; border:0; padding:10px; font-weight:600;}
QCheckBox {spacing:8px;}
QCheckBox::indicator {width:16px; height:16px; border:1px solid #a8b8af; border-radius:4px; background:#ffffff;}
QCheckBox::indicator:checked {background:#246b50; border-color:#246b50;}
QToolTip {background:#ffffff; color:#202b35; border:1px solid #dce3e7; padding:5px;}
'''

def label(text, role=None):
    item = QLabel(text)
    if role: item.setObjectName(role)
    return item

def button(text, callback, primary=False):
    b = QPushButton(text)
    if primary: b.setObjectName('primary')
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(callback)
    return b

def make_icon():
    pix = QPixmap(128, 128)
    pix.fill(QColor('#246b50'))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#ffffff'))
    p.setFont(QFont('Segoe UI', 70, QFont.Light))
    p.drawText(pix.rect(), Qt.AlignCenter, 'L')
    p.end()
    return QIcon(pix)

def init_fonts():
    # Explicit loading also supports Windows sessions with unavailable font enumeration.
    fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    for name in ('segoeui.ttf', 'segoeuil.ttf', 'msyh.ttc', 'msyhbd.ttc'):
        if (fonts / name).exists(): QFontDatabase.addApplicationFont(str(fonts / name))

class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    def run(self):
        try: self.result.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))

class Settings(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Luma · 连接设置')
        self.setMinimumWidth(540)
        self.cfg = parent.cfg.copy()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.addWidget(label('连接你的图片空间', 'title'))
        hint = label('Token 仅由 Windows 加密保存在本机。请勿把 Token 发到聊天中。', 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.fields = {}
        for key, title in [('repo', 'GitHub 仓库'), ('branch', '上传分支'), ('folder', '保存目录'), ('token', '访问 Token')]:
            field = QLineEdit(self.cfg[key])
            if key == 'token': field.setEchoMode(QLineEdit.Password)
            form.addRow(title, field)
            self.fields[key] = field
        layout.addLayout(form)
        help_text = label('创建 Fine-grained Token：只选择 PicHome 仓库，\nRepository permissions → Contents → Read and write。', 'muted')
        layout.addWidget(help_text)
        layout.addWidget(button('前往 GitHub 创建 Token ↗', lambda: QDesktopServices.openUrl(QUrl('https://github.com/settings/personal-access-tokens/new'))))
        self.status = label('', 'muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.test = button('测试连接', self.test_connection)
        self.save = button('保存设置', self.save_settings, True)
        row.addWidget(self.test)
        row.addWidget(self.save)
        layout.addLayout(row)
        self.worker = None
    def values(self): return {k: v.text().strip() for k, v in self.fields.items()}
    def save_settings(self):
        try:
            cfg = self.values()
            validate_config(cfg)
            save_config(cfg)
            self.cfg = cfg
            self.accept()
        except Exception as e: self.status.setText(str(e))
    def test_connection(self):
        cfg = self.values()
        self.test.setEnabled(False)
        self.save.setEnabled(False)
        self.status.setText('正在连接 GitHub…')
        self.worker = Worker(lambda: check_connection(cfg))
        self.worker.result.connect(lambda _: self.status.setText('连接成功 · 公开仓库与分支可访问。上传仍需 Contents 写入权限。'))
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(lambda: (self.test.setEnabled(True), self.save.setEnabled(True)))
        self.worker.start()
    def reject(self):
        if self.worker and self.worker.isRunning(): return
        super().reject()
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning(): event.ignore()
        else: super().closeEvent(event)

class DropZone(QFrame):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setObjectName('drop')
        self.setAcceptDrops(True)
        self.setMinimumHeight(225)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        arrow = label('↑')
        arrow.setStyleSheet('font-size:38px; color:#34795d;')
        arrow.setAlignment(Qt.AlignCenter)
        layout.addWidget(arrow)
        title = label('让每张图片，都有一个归处')
        title.setStyleSheet('font-size:20px;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        sub = label('拖拽图片到此处，或按 Ctrl + V 粘贴截图', 'muted')
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button('选择图片', owner.choose_files, True))
        row.addWidget(button('粘贴截图', owner.paste))
        row.addStretch()
        layout.addLayout(row)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage(): e.acceptProposedAction()
    def dropEvent(self, e):
        if e.mimeData().hasUrls(): self.owner.add_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        elif e.mimeData().hasImage(): self.owner.add_image(e.mimeData().imageData())

class LinkLibrary(QDialog):
    PAGE_SIZE = 100

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.page = 0
        self.visible = []
        self.filtered = []
        self.setWindowTitle('Luma · 图片链接库')
        self.resize(1080, 660)
        self.setMinimumSize(820, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label('每一张图片，都有迹可循。', 'title'))
        layout.addWidget(label('保留本机上传记录 · 支持多选复制 · 双击记录打开图片', 'muted'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索图片名称、链接或上传时间…')
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['图片名称', '上传时间', '图片直链', '本地备份'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(3, 100)
        self.table.cellDoubleClicked.connect(lambda row, _: QDesktopServices.openUrl(QUrl(self.visible[row]['url'])))
        layout.addWidget(self.table, 1)
        navigation = QHBoxLayout()
        self.count = label('', 'muted')
        navigation.addWidget(self.count)
        navigation.addStretch()
        self.previous = button('上一页', lambda: self.change_page(-1))
        self.next = button('下一页', lambda: self.change_page(1))
        navigation.addWidget(self.previous)
        navigation.addWidget(self.next)
        layout.addLayout(navigation)
        actions = QHBoxLayout()
        actions.addWidget(button('复制选中直链', lambda: self.copy_selected('url'), True))
        actions.addWidget(button('复制选中 Markdown', lambda: self.copy_selected('markdown')))
        actions.addWidget(button('复制筛选结果', self.copy_filtered))
        actions.addStretch()
        actions.addWidget(button('导出链接 CSV', self.export_links))
        layout.addLayout(actions)
        self.message = label('按住 Ctrl 或 Shift 可选择多条记录。', 'muted')
        layout.addWidget(self.message)
        self.refresh()

    def refresh(self, *_):
        self.page = 0
        query = self.search.text().strip().casefold()
        self.filtered = [r for r in self.owner.history if query in ' '.join(str(r.get(k, '')) for k in ('name', 'url', 'time')).casefold()]
        self.render_page()

    def render_page(self):
        self.visible = self.filtered[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        self.table.setRowCount(len(self.visible))
        for row, record in enumerate(self.visible):
            for column, value in enumerate((record['name'], record['time'], record['url'],
                                           '备份异常' if record.get('backup_error') else ('已备份' if record.get('backup_path') else '未备份'))):
                item = QTableWidgetItem(value)
                item.setToolTip(record.get('backup_path', '') if column == 3 else value)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 42)
        total_pages = max(1, (len(self.filtered) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.count.setText(f'共 {len(self.owner.history)} 条 · 匹配 {len(self.filtered)} 条 · 第 {self.page + 1} / {total_pages} 页')
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < total_pages)

    def change_page(self, delta):
        self.page += delta
        self.render_page()

    def copy_selected(self, key):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows:
            self.message.setText('请先选中要复制的图片记录。')
            return
        self.owner.copy('\n'.join(self.visible[row][key] for row in rows))
        self.message.setText(f'已复制 {len(rows)} 条链接。')

    def copy_filtered(self):
        self.owner.copy('\n'.join(record['url'] for record in self.filtered))
        self.message.setText(f'已复制全部 {len(self.filtered)} 条筛选结果的直链。')

    def export_links(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出当前筛选结果', 'Luma-links.csv', 'CSV 文件 (*.csv)')
        if not path: return
        import csv
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['图片名称', '上传时间', '图片直链', 'Markdown', '本地备份'])
                for record in self.filtered:
                    # Keep user-controlled file names from becoming spreadsheet formulas.
                    values = [record.get(key, '') for key in ('name', 'time', 'url', 'markdown', 'backup_path')]
                    writer.writerow(["'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value for value in values])
            self.message.setText(f'已导出 {len(self.filtered)} 条链接。')
        except OSError:
            self.message.setText('导出失败，请检查目标文件是否被占用或目录是否可写。')

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Luma · 流光')
        self.setWindowIcon(make_icon())
        self.resize(960, 780)
        self.setMinimumSize(760, 620)
        warning = ''
        try: self.cfg = load_config()
        except Exception:
            from core import DEFAULTS
            self.cfg = DEFAULTS.copy()
            warning = '无法读取原凭据，请在连接设置中重新填写 Token。'
        history = read_json('history.json', [])
        self.history = history if isinstance(history, list) else []
        self.queue = []
        self.worker = None
        self.busy = False
        preferences = read_json('preferences.json', {})
        self.backup_folder = preferences.get('backup_folder', '')
        self.library = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 27, 36, 22)
        layout.setSpacing(18)
        top = QHBoxLayout()
        top.addWidget(label('LUMA', 'brand'))
        top.addWidget(label('流光 / IMAGE HOME', 'muted'))
        top.addStretch()
        self.settings_button = button('连接设置', self.settings)
        top.addWidget(self.settings_button)
        layout.addLayout(top)
        layout.addWidget(label('轻轻一放，即刻分享。', 'title'))
        self.destination = label('', 'muted')
        layout.addWidget(self.destination)
        layout.addWidget(DropZone(self))
        backup_row = QHBoxLayout()
        self.backup_toggle = QCheckBox('本次上传同时备份原图到本机')
        self.backup_toggle.toggled.connect(self.backup_toggled)
        backup_row.addWidget(self.backup_toggle)
        backup_row.addStretch()
        backup_row.addWidget(button('选择备份目录', self.choose_backup_folder))
        layout.addLayout(backup_row)
        self.backup_label = label(self.backup_folder or '未选择备份目录 · 备份包含原图与对应链接信息', 'muted')
        self.backup_label.setWordWrap(True)
        layout.addWidget(self.backup_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        recent = QHBoxLayout()
        recent.addWidget(label('最近上传'))
        recent.addStretch()
        recent.addWidget(button('图片链接库', self.show_library, True))
        recent.addWidget(button('复制全部 Markdown', self.copy_all))
        layout.addLayout(recent)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.cards = QWidget()
        self.card_layout = QVBoxLayout(self.cards)
        self.card_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.card_layout.setContentsMargins(0, 0, 8, 0)
        self.card_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.cards)
        layout.addWidget(scroll, 1)
        self.status = label(warning or '就绪 · 图片公开可访问 · 单张最大 20 MB', 'muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        shortcut = QShortcut(QKeySequence.Paste, self)
        shortcut.activated.connect(self.paste)
        self.update_destination()
        self.render_history()
    def update_destination(self): self.destination.setText(f"{self.cfg['repo']}  /  {self.cfg['folder']}  ·  {self.cfg['branch']}")
    def choose_backup_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择本地图片备份目录', self.backup_folder)
        if folder:
            self.backup_folder = folder
            self.backup_label.setText(folder)
            try: write_json('preferences.json', {'backup_folder': folder})
            except OSError: self.status.setText('目录本次可用，但无法保存目录偏好。')
        return bool(folder)
    def backup_toggled(self, enabled):
        if enabled and not self.backup_folder and not self.choose_backup_folder():
            self.backup_toggle.setChecked(False)
    def backup_options(self):
        return self.backup_folder if self.backup_toggle.isChecked() else ''
    def show_library(self):
        if self.library is None: self.library = LinkLibrary(self)
        self.library.refresh()
        self.library.show()
        self.library.raise_()
        self.library.activateWindow()
    def settings(self):
        dlg = Settings(self)
        if dlg.exec():
            self.cfg = dlg.cfg
            self.update_destination()
    def ready(self):
        if not self.cfg['token']:
            self.settings()
        return bool(self.cfg['token'])
    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, '选择图片', '', '图片 (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff *.avif)')
        self.add_files(files)
    def add_files(self, files):
        if not files or not self.ready(): return
        self.queue.extend(('file', f, self.backup_options()) for f in files)
        self.next_upload()
    def paste(self):
        # Preserve normal editing/paste behavior inside settings and text fields.
        if QApplication.activeModalWidget(): return
        mime = QApplication.clipboard().mimeData()
        if mime.hasUrls(): self.add_files([u.toLocalFile() for u in mime.urls() if u.isLocalFile()])
        elif mime.hasImage(): self.add_image(QApplication.clipboard().image())
        else: self.status.setText('剪贴板中没有图片或本地图片文件。')
    def add_image(self, image):
        if image.isNull() or not self.ready(): return
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'PNG')
        self.queue.append(('bytes', ('截图.png', bytes(buffer.data())), self.backup_options()))
        self.next_upload()
    def next_upload(self):
        if self.busy or not self.queue: return
        kind, item, backup_folder = self.queue.pop(0)
        cfg = self.cfg.copy()
        def task():
            if kind == 'file':
                path = Path(item)
                if path.stat().st_size > MAX_BYTES: raise ValueError('图片超过 20 MB，请缩小后重试。')
                name, data = path.name, path.read_bytes()
            else: name, data = item
            check_connection(cfg)
            return upload_with_backup(cfg, name, data, backup_folder)
        self.busy = True
        self.settings_button.setEnabled(False)
        self.progress.show()
        self.status.setText(f'正在上传 {Path(item).name if kind == "file" else "截图"} … 待上传 {len(self.queue)} 张')
        self.worker = Worker(task)
        self.worker.result.connect(self.uploaded)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished_upload)
        self.worker.start()
    def failed(self, message):
        self.status.setText('上传失败 · ' + message)
        QMessageBox.warning(self, 'Luma · 上传失败', message + '\n请修正问题后重新选择或粘贴该图片。')
    def uploaded(self, record):
        self.history.insert(0, record)
        try: write_json('history.json', self.history)
        except OSError: self.status.setText('上传成功，但本地历史保存失败；请立即复制链接。')
        else:
            self.status.setText(record.get('backup_error') or ('上传成功 · 原图与链接已备份到本机' if record.get('backup_path') else '上传成功 · 链接已保存到图片链接库'))
        self.render_history()
        if self.library is not None: self.library.refresh()
    def finished_upload(self):
        self.busy = False
        self.settings_button.setEnabled(True)
        self.progress.hide()
        self.next_upload()
    def copy(self, value):
        QApplication.clipboard().setText(value)
        self.status.setText('已复制到剪贴板')
    def copy_all(self):
        self.copy('\n'.join(r['markdown'] for r in self.history))
    def render_history(self):
        while self.card_layout.count():
            w = self.card_layout.takeAt(0).widget()
            if w: w.deleteLater()
        if not self.history:
            self.card_layout.addWidget(label('还没有上传记录。你的第一张图片，从这里开始。', 'muted'))
        for r in self.history[:20]:
            card = QFrame()
            card.setObjectName('card')
            card.setFixedHeight(160)
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 13, 16, 13)
            row = QHBoxLayout()
            name = label(r['name'])
            name.setTextFormat(Qt.PlainText)
            row.addWidget(name, 1)
            row.addWidget(label(r['time'], 'muted'))
            box.addLayout(row)
            link = QLineEdit(r['url'])
            link.setReadOnly(True)
            box.addWidget(link)
            actions = QHBoxLayout()
            actions.addWidget(button('复制直链', lambda checked=False, r=r: self.copy(r['url'])))
            actions.addWidget(button('复制 Markdown', lambda checked=False, r=r: self.copy(r['markdown'])))
            actions.addStretch()
            actions.addWidget(button('打开图片 ↗', lambda checked=False, r=r: QDesktopServices.openUrl(QUrl(r['url']))))
            box.addLayout(actions)
            self.card_layout.addWidget(card)
    def closeEvent(self, event):
        if self.busy or self.queue:
            QMessageBox.information(self, 'Luma', '正在上传图片，请等待上传完成后关闭。')
            event.ignore()
        else: event.accept()

if __name__ == '__main__':
    if '--network-test' in sys.argv:
        import json
        from diagnose_network import run_checks
        results = run_checks()
        Path('network-check.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        sys.exit(0 if all(r.get('status') == 200 for r in results) else 1)
    app = QApplication(sys.argv)
    init_fonts()
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setWindowIcon(make_icon())
    window = Window()
    window.show()
    if '--smoke-test' in sys.argv:
        def finish_smoke():
            window.grab().save('exe-preview.png')
            app.quit()
        QTimer.singleShot(1500, finish_smoke)
    sys.exit(app.exec())
