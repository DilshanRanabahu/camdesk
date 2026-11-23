"""Camera passwords in Windows Credential Manager (via keyring). Never on disk in plain text."""

from __future__ import annotations

import contextlib
import logging

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

SERVICE = "CamDesk"


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
