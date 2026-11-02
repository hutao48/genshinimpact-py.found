# -*- coding: utf-8 -*-
"""更新检测：只查询 GitHub Releases 的公开 JSON，不下载、不执行任何文件。

安全约束：
- 固定 HTTPS 主机与仓库路径，不读取用户提供的 URL；
- 限制响应体大小与超时时间；
- 只接受 GitHub 的 release 页面链接，打开前再次校验 scheme/host；
- 任何异常都转成错误码，不影响主界面。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QByteArray, QFile, QIODevice
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from app_version import APP_REPO, APP_VERSION

API_URL = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
RELEASE_PREFIX = f"https://github.com/{APP_REPO}/releases/"
MAX_BODY = 512 * 1024
MAX_ASSET = 200 * 1024 * 1024
TIMEOUT_MS = 12000
ASSET_TIMEOUT_MS = 10 * 60 * 1000
ASSET_HOSTS = {"github.com", "release-assets.githubusercontent.com",
               "objects.githubusercontent.com"}


def _parse_version(text: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def valid_release_url(url: str) -> bool:
    q = QUrl(url)
    return (q.isValid() and q.scheme().lower() == "https"
            and q.host().lower() == "github.com"
            and not q.userInfo()
            and q.port() in (-1, 443)
            and q.path().startswith(f"/{APP_REPO}/releases/"))


def valid_asset_url(url: str) -> bool:
    q = QUrl(url)
    return (q.isValid() and q.scheme().lower() == "https"
            and q.host().lower() == "github.com"
            and not q.userInfo()
            and q.port() in (-1, 443)
            and q.path().startswith(f"/{APP_REPO}/releases/download/"))


class UpdateChecker(QObject):
    """一次更新检查；结果通过 done(dict) 发出。"""

    done = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._reply = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._emitted = False
        self._body = QByteArray()
        self._too_large = False

    def check(self):
        if self._reply is not None:
            return
        self._emitted = False
        self._body = QByteArray()
        self._too_large = False
        req = QNetworkRequest(QUrl(API_URL))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                      f"GenshinInstrumentDetector/{APP_VERSION}")
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        # GitHub 的 API 不需要跳转；禁用跳转，避免被重定向到任意 HTTPS 主机。
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        try:
            req.setTransferTimeout(TIMEOUT_MS)
        except AttributeError:
            pass
        self._timer.start(TIMEOUT_MS)
        self._reply = self._nam.get(req)
        self._reply.setReadBufferSize(64 * 1024)
        self._reply.readyRead.connect(self._read_body)
        self._reply.finished.connect(self._finished)

    def _finish(self, payload: dict):
        if self._emitted:
            return
        self._emitted = True
        self._timer.stop()
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.deleteLater()
        self.done.emit(payload)

    def _fail(self, error: str, **extra):
        self._finish({"ok": False, "error": error, **extra})

    def _read_body(self):
        reply = self._reply
        if reply is None or self._too_large:
            return
        chunk = reply.read(64 * 1024)
        if not chunk:
            return
        self._body.append(chunk)
        if self._body.size() > MAX_BODY:
            self._too_large = True
            reply.abort()
            self._finish({"ok": False, "error": "too_large"})

    def _on_timeout(self):
        if self._reply is not None:
            self._reply.abort()
            self._finish({"ok": False, "error": "timeout"})

    def _finished(self):
        reply = self._reply
        if reply is None or self._emitted:
            return
        if self._too_large:
            self._fail("too_large")
            return
        # 只接受固定 API 主机；不跟随跳转后也要复核实际 URL。
        u = reply.url()
        if u.scheme().lower() != "https" or u.host().lower() != "api.github.com":
            self._fail("network")
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._finish({"ok": False, "error": "network",
                          "detail": reply.errorString()})
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status != 200:
            self._finish({"ok": False, "error": "http", "code": status})
            return
        try:
            length = int(reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader) or 0)
        except (TypeError, ValueError):
            length = 0
        if length > MAX_BODY:
            self._fail("too_large")
            return
        ctype = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader) or "")
        if "json" not in ctype.lower():
            self._fail("json")
            return
        if self._body.size() == 0:
            self._body = reply.readAll()
        data = self._body
        if data.size() > MAX_BODY:
            self._fail("too_large")
            return
        try:
            info = json.loads(bytes(data).decode("utf-8", "replace"))
        except (ValueError, UnicodeError):
            self._fail("json")
            return
        if not isinstance(info, dict):
            self._fail("json")
            return
        tag = str(info.get("tag_name") or "")
        latest = _parse_version(tag)
        current = _parse_version(APP_VERSION)
        if latest is None or current is None:
            self._finish({"ok": False, "error": "version"})
            return
        url = str(info.get("html_url") or "")
        if not valid_release_url(url):
            url = f"{RELEASE_PREFIX}latest"
        notes = str(info.get("body") or "")[:8000]
        assets = []
        for a in info.get("assets") or []:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "")
            asset_url = str(a.get("browser_download_url") or "")
            if not name or not valid_asset_url(asset_url):
                continue
            try:
                size = int(a.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            digest = str(a.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            assets.append({"name": name, "url": asset_url, "size": size,
                           "sha256": sha if re.fullmatch(r"[0-9a-f]{64}", sha) else ""})
        payload = {
            "ok": True,
            "update": latest > current,
            "latest": ".".join(str(x) for x in latest),
            "current": APP_VERSION,
            "url": url,
            "notes": notes,
            "published": str(info.get("published_at") or ""),
            "assets": assets,
        }
        self._finish(payload)


class UpdateDownloader(QObject):
    """下载更新安装包：HTTPS + 大小上限 + SHA-256 校验 + PE 头检查。

    仅用于用户开启自动更新或手动确认后的安装包下载；下载成功后仍由界面决定是否执行。
    """

    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, expected_sha256: str, expected_size: int = 0, parent=None):
        super().__init__(parent)
        self.url = url
        self.expected_sha256 = (expected_sha256 or "").lower()
        self.expected_size = int(expected_size or 0)
        self._nam = QNetworkAccessManager(self)
        self._reply = None
        self._file = None
        self._path = ""
        self._bytes = 0
        self._emitted = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self):
        if self._reply is not None:
            return
        if not valid_asset_url(self.url) or not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            self._fail("invalid")
            return
        fd, self._path = tempfile.mkstemp(prefix="GID-update-", suffix=".exe")
        os.close(fd)
        self._file = QFile(self._path)
        if not self._file.open(QIODevice.OpenModeFlag.WriteOnly):
            self._fail("io")
            return
        req = QNetworkRequest(QUrl(self.url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                      f"GenshinInstrumentDetector/{APP_VERSION}")
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        try:
            req.setTransferTimeout(ASSET_TIMEOUT_MS)
        except AttributeError:
            pass
        self._timer.start(ASSET_TIMEOUT_MS)
        self._reply = self._nam.get(req)
        self._reply.setReadBufferSize(256 * 1024)
        self._reply.readyRead.connect(self._read)
        self._reply.finished.connect(self._finished)

    def cancel(self):
        self._emitted = True
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()
        self._cleanup(remove=True)

    def _cleanup(self, remove: bool):
        self._timer.stop()
        if self._file is not None:
            self._file.close()
            self._file = None
        if remove and self._path:
            try:
                os.remove(self._path)
            except OSError:
                pass
            self._path = ""

    def _fail(self, error: str):
        if self._emitted:
            return
        self._emitted = True
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.deleteLater()
        self._cleanup(remove=True)
        self.failed.emit(error)

    def _on_timeout(self):
        if self._reply is not None:
            self._reply.abort()
        self._fail("timeout")

    def _read(self):
        reply = self._reply
        if reply is None or self._emitted:
            return
        chunk = reply.read(256 * 1024)
        if not chunk:
            return
        self._bytes += chunk.size()
        if self._bytes > MAX_ASSET:
            self._reply.abort()
            self._fail("too_large")
            return
        if self._file is None or self._file.write(chunk) != chunk.size():
            self._reply.abort()
            self._fail("io")
            return
        if self.expected_size > 0:
            self.progress.emit(min(99, int(self._bytes * 100 / self.expected_size)))

    def _finished(self):
        reply = self._reply
        if reply is None or self._emitted:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._fail("network")
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status != 200:
            self._fail("http")
            return
        u = reply.url()
        if u.scheme().lower() != "https" or u.host().lower() not in ASSET_HOSTS:
            self._fail("network")
            return
        try:
            length = int(reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader) or 0)
        except (TypeError, ValueError):
            length = 0
        if length > MAX_ASSET:
            self._fail("too_large")
            return
        # 读完剩余缓冲（readyRead 可能还没消费完）
        rest = reply.readAll()
        if rest.size():
            self._bytes += rest.size()
            if self._bytes > MAX_ASSET or self._file is None or self._file.write(rest) != rest.size():
                self._fail("too_large" if self._bytes > MAX_ASSET else "io")
                return
        self._cleanup(remove=False)
        path = self._path
        try:
            if self.expected_size and os.path.getsize(path) != self.expected_size:
                self._fail("size")
                return
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
            if h.hexdigest() != self.expected_sha256:
                self._fail("checksum")
                return
            with open(path, "rb") as f:
                if f.read(2) != b"MZ":
                    self._fail("format")
                    return
        except OSError:
            self._fail("io")
            return
        self._emitted = True
        self._path = ""
        self.progress.emit(100)
        self.done.emit(path)
