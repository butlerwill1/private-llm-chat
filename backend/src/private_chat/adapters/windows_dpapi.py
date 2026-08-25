"""Windows current-user protection for the local transcript master key."""

import ctypes
import os
from ctypes import POINTER, Structure, byref, c_byte, create_string_buffer, wintypes
from pathlib import Path
from typing import Any, Final

from private_chat.adapters.encryption import LocalAesDataKeyProvider


class _DataBlob(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(c_byte))]


_CRYPTPROTECT_UI_FORBIDDEN: Final = 0x1
_MASTER_KEY_FILE: Final = "master-key.dpapi"


def _blob(value: bytes) -> tuple[_DataBlob, Any]:
    buffer = create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, POINTER(c_byte))), buffer


def _crypt_protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is available only on Windows")
    source, source_buffer = _blob(value)
    result = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        POINTER(_DataBlob),
        wintypes.LPCWSTR,
        POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(
        byref(source),
        "Private LLM Chat local master key",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        byref(result),
    ):
        raise OSError(ctypes.get_last_error(), "Windows failed to protect the local master key")
    del source_buffer
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.WinDLL("kernel32", use_last_error=True).LocalFree(result.pbData)


def _crypt_unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is available only on Windows")
    source, source_buffer = _blob(value)
    result = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        POINTER(_DataBlob),
        POINTER(wintypes.LPWSTR),
        POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(
        byref(source), None, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN, byref(result)
    ):
        raise OSError(
            ctypes.get_last_error(),
            "Windows could not unlock the local transcript key; existing chats cannot be recovered",
        )
    del source_buffer
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.WinDLL("kernel32", use_last_error=True).LocalFree(result.pbData)


class DpapiLocalDataKeyProvider(LocalAesDataKeyProvider):
    """Envelope-key provider whose master key is bound to the current Windows user."""

    @classmethod
    def load_or_create(
        cls, data_directory: Path, *, database_path: Path
    ) -> "DpapiLocalDataKeyProvider":
        data_directory.mkdir(parents=True, exist_ok=True)
        key_path = data_directory / _MASTER_KEY_FILE
        if key_path.exists():
            key = _crypt_unprotect(key_path.read_bytes())
            return cls(key)
        if database_path.exists() and database_path.stat().st_size > 0:
            raise RuntimeError(
                "The local conversation database exists but its DPAPI key is missing; "
                "creating a replacement would make existing chats unrecoverable"
            )
        key = os.urandom(32)
        protected = _crypt_protect(key)
        try:
            with key_path.open("xb") as handle:
                handle.write(protected)
        except FileExistsError:
            return cls(_crypt_unprotect(key_path.read_bytes()))
        return cls(key)
