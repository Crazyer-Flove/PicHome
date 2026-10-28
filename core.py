"""Luma storage, Windows credential protection and GitHub upload."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import socket
import ssl
import uuid
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

APP_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Luma'
MAX_BYTES = 20 * 1024 * 1024
DEFAULTS = dict(repo='Crazyer-Flove/PicHome', branch='main', folder='images', token='')

class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

def protect(value, decrypt=False):
    data = base64.b64decode(value) if decrypt else value.encode('utf-8')
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), 'Luma GitHub', None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise OSError('Windows 凭据加密失败，请重新设置 Token。')
    try:
        result = ctypes.string_at(target.pbData, target.cbData)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)

def read_json(name, default):
    try:
        return json.loads((APP_DIR / name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def write_json(name, value):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    path = APP_DIR / name
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def load_config():
    cfg = DEFAULTS | read_json('settings.json', {})
    encrypted = cfg.pop('encrypted_token', '')
    cfg['token'] = protect(encrypted, True) if encrypted else ''
    return cfg

def save_config(cfg):
    data = {k: v for k, v in cfg.items() if k != 'token'}
    data['encrypted_token'] = protect(cfg['token']) if cfg['token'] else ''
    write_json('settings.json', data)

def validate_config(cfg):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', cfg['repo']):
        raise ValueError('仓库格式应为 用户名/仓库名。')
    if not cfg['branch'].strip():
        raise ValueError('请填写分支名称。')
    parts = cfg['folder'].replace('\\', '/').strip('/').split('/')
    if any(p in ('.', '..') for p in parts):
        raise ValueError('保存目录不能包含 . 或 ..。')
    if not cfg['token'].strip():
        raise ValueError('请先在设置中填写 GitHub Token。')

def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')): return '.gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return '.webp'
    if data.startswith(b'BM'): return '.bmp'
    if data.startswith((b'II*\x00', b'MM\x00*')): return '.tiff'
    if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'): return '.avif'
    raise ValueError('支持 PNG、JPEG、GIF、WebP、BMP、TIFF 和 AVIF 图片。')

def api(cfg, path, payload=None):
    req = Request('https://api.github.com/' + path, data=json.dumps(payload).encode() if payload else None,
                  method='PUT' if payload else 'GET', headers={
                      'Authorization': 'Bearer ' + cfg['token'], 'Accept': 'application/vnd.github+json',
                      'Content-Type': 'application/json', 'User-Agent': 'Luma-Image-Home/1.0',
                      'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urlopen(req, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        messages = {401: 'Token 无效或已过期，请更新设置。', 403: '权限不足或请求受限，请检查 Token 的 Contents 读写权限及 GitHub 限流。',
                    404: '仓库或分支不存在，或 Token 无权访问此仓库。', 409: '仓库发生并发修改，请重试。',
                    422: 'GitHub 未接受此上传，请检查分支和目录设置。'}
        raise ValueError(messages.get(error.code, f'GitHub 返回错误 {error.code}，请稍后重试。')) from None
    except (URLError, TimeoutError, OSError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(reason, FileNotFoundError):
            message = 'HTTPS 组件文件缺失，请使用修复后的新版 Luma。无需重新申请 Token。'
        elif isinstance(reason, ssl.SSLCertVerificationError):
            message = 'HTTPS 证书验证失败，请检查系统时间、系统证书或代理的证书配置。'
        elif isinstance(reason, ssl.SSLError):
            message = 'HTTPS 握手失败，请检查代理连接后重试。'
        elif isinstance(reason, (TimeoutError, socket.timeout)):
            message = '连接 GitHub 超时，请检查网络和系统代理后重试。'
        elif isinstance(reason, socket.gaierror):
            message = '无法解析 api.github.com，请检查 DNS 和网络连接。'
        elif isinstance(reason, ConnectionRefusedError):
            message = '连接被拒绝，请确认网络或系统代理服务正在运行。'
        else:
            message = '无法连接 GitHub，请检查网络和系统代理后重试。'
        raise ValueError(message) from None

def check_connection(cfg):
    validate_config(cfg)
    repo = api(cfg, 'repos/' + cfg['repo'])
    if repo.get('private'):
        raise ValueError('请选择公开仓库，否则图片直链不能供所有人访问。')
    api(cfg, 'repos/' + cfg['repo'] + '/branches/' + quote(cfg['branch'], safe=''))
    return repo

def upload(cfg, name, data):
    validate_config(cfg)
    if not data or len(data) > MAX_BYTES:
        raise ValueError('单张图片需大于 0 字节且不超过 20 MB。')
    ext = image_extension(data)
    path = '/'.join(filter(None, [cfg['folder'].replace('\\', '/').strip('/'), datetime.now().strftime('%Y/%m'), uuid.uuid4().hex + ext]))
    result = api(cfg, 'repos/' + cfg['repo'] + '/contents/' + quote(path, safe='/'),
                 dict(message='Upload image via Luma', content=base64.b64encode(data).decode(), branch=cfg['branch']))
    sha = result['commit']['sha']
    url = 'https://raw.githubusercontent.com/' + cfg['repo'] + '/' + sha + '/' + quote(path, safe='/')
    alt = Path(name).stem.replace('[', '').replace(']', '').replace('\n', ' ')
    return dict(name=name, url=url, markdown=f'![{alt}]({url})', path=path, time=datetime.now().strftime('%Y-%m-%d %H:%M'), sha=sha)
