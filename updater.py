# -*- coding: utf-8 -*-
"""更新检测：只查询 GitHub Releases 的公开 JSON，不下载、不执行任何文件。

安全约束：
- 固定 HTTPS 主机与仓库路径，不读取用户提供的 URL；
- 限制响应体大小与超时时间；
- 只接受 GitHub 的 release 页面链接，打开前再次校验 scheme/host；
- 任何异常都转成错误码，不影响主界面。
"""
from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QByteArray
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from app_version import APP_REPO, APP_VERSION

API_URL = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
RELEASE_PREFIX = f"https://github.com/{APP_REPO}/releases/"
MAX_BODY = 512 * 1024
TIMEOUT_MS = 12000


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
        payload = {
            "ok": True,
            "update": latest > current,
            "latest": ".".join(str(x) for x in latest),
            "current": APP_VERSION,
            "url": url,
            "notes": notes,
            "published": str(info.get("published_at") or ""),
        }
        self._finish(payload)
