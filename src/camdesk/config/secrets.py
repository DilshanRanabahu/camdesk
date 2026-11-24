"""Camera passwords in Windows Credential Manager (via keyring). Never on disk in plain text."""

from __future__ import annotations

import contextlib
import logging
import sys

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "CamDesk"


def _use_windows_credential_manager() -> None:
    """Pick the Windows backend explicitly.

    keyring normally finds backends through package metadata (entry points), which a packaged
    .exe can lose — passwords would then silently fail to save. Choosing it directly works the
    same from source and from CamDesk.exe.
    """
    if sys.platform != "win32":
        return
    try:
        from keyring.backends.Windows import WinVaultKeyring

        keyring.set_keyring(WinVaultKeyring())
    except Exception:  # missing pywin32-ctypes etc.: fall back to keyring's own choice
        log.warning("Windows Credential Manager backend unavailable", exc_info=True)


_use_windows_credential_manager()


def get_password(camera_id: str) -> str:
    try:
        return keyring.get_password(SERVICE, camera_id) or ""
    except KeyringError:
        log.warning("Could not read password from the credential store")
        return ""


def set_password(camera_id: str, password: str) -> None:
    try:
        if password:
            keyring.set_password(SERVICE, camera_id, password)
        else:
            delete_password(camera_id)
    except KeyringError:
        log.warning("Could not save password to the credential store")


def delete_password(camera_id: str) -> None:
    with contextlib.suppress(PasswordDeleteError, KeyringError):
        keyring.delete_password(SERVICE, camera_id)
