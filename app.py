import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QBuffer, QIODevice, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QKeySequence, QShortcut, QPixmap, QIcon, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QLineEdit, QDialog, QFormLayout, QMessageBox, QProgressBar, QLayout)
from core import load_config, save_config, read_json, write_json, upload, check_connection, validate_config, MAX_BYTES

STYLE = '''
QWidget { background:#111516; color:#e9eeee; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:14px; }
QLabel#brand {font-size:28px; font-weight:600; letter-spacing:3px;}
QLabel#title {font-size:29px; font-weight:600;}
QLabel#muted {color:#8b9b9b; font-size:13px;}
QFrame#drop {border:1px dashed #45635c; border-radius:18px; background:#171f1e;}
QFrame#drop QLabel {background:transparent;}
QFrame#card {background:#1b2223; border:1px solid #2c3738; border-radius:12px;}
QFrame#card QLabel {background:transparent;}
QPushButton {background:#273233; border:1px solid #354344; border-radius:8px; padding:10px 17px;}
QPushButton:hover {background:#354645; border-color:#6a9b8c;}
QPushButton:disabled {color:#637373; background:#222a2a;}
QPushButton#primary {background:#b4e5cf; color:#12221c; border:0; font-weight:600;}
QPushButton#primary:hover {background:#d0f4e2;}
QLineEdit {background:#101516; border:1px solid #364747; border-radius:7px; padding:10px; selection-background-color:#467666;}
QScrollArea {border:0;}
QProgressBar {border:0; background:#253232; height:3px; border-radius:1px;}
QProgressBar::chunk {background:#b4e5cf;}
QScrollBar:vertical {background:#111516; width:8px;}
QScrollBar::handle:vertical {background:#3b4b49; min-height:30px; border-radius:4px;}
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
    pix.fill(QColor('#142521'))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#b4e5cf'))
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
        arrow.setStyleSheet('font-size:38px; color:#b4e5cf;')
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
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        recent = QHBoxLayout()
        recent.addWidget(label('最近上传'))
        recent.addStretch()
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
        self.queue.extend(('file', f) for f in files)
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
        self.queue.append(('bytes', ('截图.png', bytes(buffer.data()))))
        self.next_upload()
    def next_upload(self):
        if self.busy or not self.queue: return
        kind, item = self.queue.pop(0)
        cfg = self.cfg.copy()
        def task():
            if kind == 'file':
                path = Path(item)
                if path.stat().st_size > MAX_BYTES: raise ValueError('图片超过 20 MB，请缩小后重试。')
                name, data = path.name, path.read_bytes()
            else: name, data = item
            check_connection(cfg)
            return upload(cfg, name, data)
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
        self.history = self.history[:500]
        try: write_json('history.json', self.history)
        except OSError: self.status.setText('上传成功，但本地历史保存失败；请立即复制链接。')
        else: self.status.setText('上传成功 · 链接已保存到本地历史')
        self.render_history()
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
        for r in self.history:
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
