"""Chỉ cho chạy một bản LiveTrans. Mở lại app (shortcut) → bản đang chạy hiện cửa sổ chính."""

import ctypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\LiveTransSingleton"  # bộ cài (AppMutex) dùng tên này để biết app đang chạy
SERVER_NAME = "LiveTransActivate"


def acquire(name: str = MUTEX_NAME):
    """Trả về handle mutex (giữ đến khi thoát) hoặc ``None`` nếu đã có bản đang chạy."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return handle


def activate_running_instance(timeout_ms: int = 1000) -> bool:
    """Gọi từ bản thứ hai (cần QCoreApplication): nhờ bản đang chạy hiện cửa sổ chính."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(b"show\n")
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


class ActivationServer(QObject):
    activated = Signal()

    def __init__(self) -> None:
        super().__init__()
        QLocalServer.removeServer(SERVER_NAME)  # dọn server cũ nếu lần trước bị tắt ngang
        self._server = QLocalServer(self)
        self._server.listen(SERVER_NAME)
        self._server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.readyRead.connect(lambda c=conn: self._on_ready(c))
            conn.disconnected.connect(conn.deleteLater)

    def _on_ready(self, conn) -> None:
        if b"show" in bytes(conn.readAll()):
            self.activated.emit()
