from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from db.config import settings


def _get_fernet() -> Fernet:
    if not settings.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY is not set; cannot encrypt/decrypt EncryptedString columns.")
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


class EncryptedString(TypeDecorator):
    """Stores strings encrypted at rest (Fernet/AES) via ENCRYPTION_KEY.

    Transparent to callers: reads/writes plain str in Python, ciphertext
    in the DB column.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
