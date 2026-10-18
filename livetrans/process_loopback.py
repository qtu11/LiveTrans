"""Bắt âm thanh hệ thống TRỪ tiếng của chính LiveTrans (WASAPI process loopback, Windows 10 2004+).

Khi bật giọng đọc, LiveTrans phát tiếng Việt ra loa; loopback thường sẽ thu lại giọng đó và trộn với tiếng
video → nhận dạng kém. Ở đây ta kích hoạt thiết bị ảo ``VAD\\Process_Loopback`` với chế độ
EXCLUDE_TARGET_PROCESS_TREE cho tiến trình hiện tại, và yêu cầu Windows trả thẳng PCM 16 kHz mono int16.
"""

from __future__ import annotations

import ctypes
import os
import threading
import uuid
from ctypes import POINTER, WINFUNCTYPE, byref, c_long, c_uint16, c_uint32, c_uint64, c_ulong, c_void_p, c_wchar_p

import numpy as np

S_OK = 0
E_NOINTERFACE = ctypes.c_long(0x80004002).value
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
VT_BLOB = 65
ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE = 1
VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
SAMPLE_RATE = 16000


class GUID(ctypes.Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> "GUID":
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)

    def __eq__(self, other) -> bool:
        return bytes(self) == bytes(other)


IID_IUnknown = GUID.of("00000000-0000-0000-C000-000000000046")
IID_IAgileObject = GUID.of("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")
IID_IActivateAudioInterfaceCompletionHandler = GUID.of("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAudioClient = GUID.of("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID.of("C8ADBD64-E71E-48A0-A4DE-185C395CD317")


class AUDIOCLIENT_ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [("ActivationType", c_uint32), ("TargetProcessId", c_uint32), ("ProcessLoopbackMode", c_uint32)]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", c_uint16), ("r1", c_uint16), ("r2", c_uint16), ("r3", c_uint16), ("blob", BLOB)]


class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("wFormatTag", c_uint16), ("nChannels", c_uint16), ("nSamplesPerSec", c_uint32),
        ("nAvgBytesPerSec", c_uint32), ("nBlockAlign", c_uint16), ("wBitsPerSample", c_uint16),
        ("cbSize", c_uint16),
    ]


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise OSError(f"{what} lỗi HRESULT 0x{hr & 0xFFFFFFFF:08X}")


def _call(ptr: int, index: int, argtypes: list, *args, restype=c_long):
    """Gọi phương thức COM thứ ``index`` trong vtable của ``ptr``."""
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
    fn = WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])
    return fn(ptr, *args)


def _release(ptr: int | None) -> None:
    if ptr:
        _call(ptr, 2, [], restype=c_ulong)


# --------------------------------------------------- completion handler (COM)
_QI = WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))
_ADDREF = WINFUNCTYPE(c_ulong, c_void_p)
_COMPLETED = WINFUNCTYPE(c_long, c_void_p, c_void_p)


class _HandlerVtbl(ctypes.Structure):
    _fields_ = [("QueryInterface", _QI), ("AddRef", _ADDREF), ("Release", _ADDREF), ("ActivateCompleted", _COMPLETED)]


class _HandlerObj(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(_HandlerVtbl))]


class _CompletionHandler:
    """IActivateAudioInterfaceCompletionHandler + IAgileObject tối thiểu, viết bằng ctypes."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.operation: int | None = None
        self._vtbl = _HandlerVtbl(_QI(self._qi), _ADDREF(lambda this: 1), _ADDREF(lambda this: 1),
                                  _COMPLETED(self._completed))
        self.obj = _HandlerObj(ctypes.pointer(self._vtbl))

    def _qi(self, this, riid, ppv) -> int:
        if riid.contents in (IID_IUnknown, IID_IAgileObject, IID_IActivateAudioInterfaceCompletionHandler):
            ppv[0] = this
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE

    def _completed(self, this, operation) -> int:
        self.operation = operation
        self.done.set()
        return S_OK


# ---------------------------------------------------------------- capture
class ProcessLoopbackCapture:
    """Bắt âm thanh mọi ứng dụng trừ cây tiến trình ``exclude_pid`` → int16 mono 16 kHz."""

    def __init__(self, exclude_pid: int | None = None) -> None:
        self.exclude_pid = exclude_pid or os.getpid()
        self._client: int | None = None
        self._capture: int | None = None
        self._block_align = 2

    def start(self) -> None:
        mmdevapi = ctypes.WinDLL("Mmdevapi.dll")
        activate = mmdevapi.ActivateAudioInterfaceAsync
        activate.argtypes = [c_wchar_p, POINTER(GUID), POINTER(PROPVARIANT), c_void_p, POINTER(c_void_p)]
        activate.restype = c_long

        params = AUDIOCLIENT_ACTIVATION_PARAMS(
            ACTIVATION_TYPE_PROCESS_LOOPBACK, self.exclude_pid, PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE
        )
        pv = PROPVARIANT(vt=VT_BLOB, blob=BLOB(ctypes.sizeof(params), ctypes.cast(byref(params), c_void_p)))
        handler = _CompletionHandler()
        op = c_void_p()
        _check(
            activate(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, byref(IID_IAudioClient), byref(pv),
                     ctypes.addressof(handler.obj), byref(op)),
            "ActivateAudioInterfaceAsync",
        )
        try:
            if not handler.done.wait(5):
                raise OSError("kích hoạt process loopback quá thời gian")
            hr_activate = c_long()
            client = c_void_p()
            _check(_call(op.value, 3, [POINTER(c_long), POINTER(c_void_p)], byref(hr_activate), byref(client)),
                   "GetActivateResult")
            _check(hr_activate.value, "kích hoạt IAudioClient")
        finally:
            _release(op.value)
        self._client = client.value

        fmt = WAVEFORMATEX(1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16, 0)
        flags = AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
        _check(
            _call(self._client, 3, [ctypes.c_int, c_uint32, ctypes.c_int64, ctypes.c_int64, POINTER(WAVEFORMATEX), c_void_p],
                  AUDCLNT_SHAREMODE_SHARED, flags, 2_000_000, 0, byref(fmt), None),
            "IAudioClient.Initialize",
        )
        capture = c_void_p()
        _check(_call(self._client, 14, [POINTER(GUID), POINTER(c_void_p)], byref(IID_IAudioCaptureClient), byref(capture)),
               "IAudioClient.GetService")
        self._capture = capture.value
        self._block_align = fmt.nBlockAlign
        _check(_call(self._client, 10, []), "IAudioClient.Start")

    def read(self) -> np.ndarray:
        """Đọc hết dữ liệu đang có (không chặn) → float32 mono 16 kHz (có thể rỗng)."""
        chunks = []
        size = c_uint32()
        while True:
            _check(_call(self._capture, 5, [POINTER(c_uint32)], byref(size)), "GetNextPacketSize")
            if size.value == 0:
                break
            data, frames, flags = c_void_p(), c_uint32(), c_uint32()
            _check(
                _call(self._capture, 3, [POINTER(c_void_p), POINTER(c_uint32), POINTER(c_uint32), POINTER(c_uint64),
                                         POINTER(c_uint64)], byref(data), byref(frames), byref(flags), None, None),
                "GetBuffer",
            )
            n = frames.value
            if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                chunks.append(np.zeros(n, dtype=np.float32))
            else:
                raw = ctypes.string_at(data.value, n * self._block_align)
                chunks.append(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
            _check(_call(self._capture, 4, [c_uint32], n), "ReleaseBuffer")
        return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)

    def stop(self) -> None:
        if self._client:
            try:
                _call(self._client, 11, [])
            except OSError:
                pass
        _release(self._capture)
        _release(self._client)
        self._capture = self._client = None
