import base64
import ctypes
from ctypes import wintypes


CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _to_blob(data: bytes):
    if not data:
        return DATA_BLOB(0, None), None
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _from_blob(blob: DATA_BLOB) -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _is_windows() -> bool:
    return hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32")


def protect_secret(plain_text: str) -> str:
    if not plain_text:
        return ""
    if not _is_windows():
        raise RuntimeError("Secret protection is supported only on Windows.")

    plain_blob, plain_buffer = _to_blob(plain_text.encode("utf-8"))
    out_blob = DATA_BLOB()

    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(plain_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise RuntimeError("CryptProtectData failed")

    try:
        protected = _from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    _ = plain_buffer  # keep buffer alive through API call
    return base64.b64encode(protected).decode("ascii")


def unprotect_secret(encoded_text: str) -> str:
    if not encoded_text:
        return ""
    if not _is_windows():
        raise RuntimeError("Secret unprotection is supported only on Windows.")

    protected = base64.b64decode(encoded_text.encode("ascii"))
    protected_blob, protected_buffer = _to_blob(protected)
    out_blob = DATA_BLOB()

    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(protected_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise RuntimeError("CryptUnprotectData failed")

    try:
        plain = _from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    _ = protected_buffer  # keep buffer alive through API call
    return plain.decode("utf-8")
