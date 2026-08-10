from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import settings


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
        return Fernet(settings.ENCRYPTION_KEY).encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return Fernet(settings.ENCRYPTION_KEY).decrypt(value.encode("utf-8")).decode("utf-8")
