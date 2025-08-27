from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from core.config.settings import Settings

# --- Password Hashing ---
# Use passlib for robust and secure password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its hashed version."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)


# --- JSON Web Tokens (JWT) ---
# These tokens are used to authenticate API requests after a user logs in.

def create_access_token(data: dict, settings: Settings) -> str:
    """Creates a new JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.auth.access_token_expire_minutes)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.auth.secret_key,
        algorithm=settings.auth.algorithm
    )
    return encoded_jwt


def decode_access_token(token: str, settings: Settings) -> dict | None:
    """
    Decodes and validates a JWT access token.

    Returns:
        The token's payload if valid, otherwise None.
    """
    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm]
        )
        return payload
    except JWTError:
        # Token is invalid (expired, wrong signature, etc.)
        return None