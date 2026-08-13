from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.ENCRYPTION_KEY:
            raise ValueError(
                "ENCRYPTION_KEY is not set. Configure a valid Fernet key "
                "(see cryptography.fernet.Fernet.generate_key()) before "
                "reading/writing encrypted columns."
            )
        _fernet = Fernet(settings.ENCRYPTION_KEY)
    return _fernet


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
