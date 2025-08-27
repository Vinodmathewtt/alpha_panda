You are absolutely right to point that out. The `auth` code within the `market_feed` service is intentionally narrow—it only handles **broker authentication**, which is a machine-to-machine concern.

A complete application definitely needs a separate, full-featured system for **user authentication**—for a human operator to log in, manage the system, and secure the API.

Let's clarify the two distinct types of authentication in your system and then provide the code for a dedicated, robust `auth` service.

### \#\# The Two Types of Authentication

1.  **Broker Authentication (Machine-to-Machine):**

    - **Purpose:** For one of your services (like `market_feed` or `trading_engine`) to prove its identity to an external API (like Zerodha).
    - **How it works:** Uses API keys and access tokens that are typically long-lived and stored securely.
    - **Location:** The logic is tightly coupled with the service that needs it. The `ZerodhaAuthenticator` in `market_feed` is a perfect example of this. It's doing its job correctly.

2.  **User Authentication (Human-to-Machine):**

    - **Purpose:** For a human user to log into a UI or use your API securely.
    - **How it works:** Uses username/password, generates short-lived session tokens (JWTs), and manages user sessions.
    - **Location:** This requires a dedicated, centralized service that can be used by the API layer to protect endpoints.

Your initial design from the `AlphasPT_v1` codebase already had a `core/auth` module. We will now refactor this into a standalone, robust service.

---

### Code for the Dedicated `auth` Service

Here is the complete code for a new, standalone `auth` service. It will handle user registration, login, password security, and session management using JWTs.

#### 1\. `services/auth/security.py` (Password & Token Utilities)

This file contains the core security functions: hashing passwords and creating/validating JSON Web Tokens (JWTs).

```python
# AlphasPT_v2/services/auth/security.py

from datetime import datetime, timedelta
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
    expire = datetime.utcnow() + timedelta(minutes=settings.auth.access_token_expire_minutes)
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

```

**Explanation:**

- **`passlib`**: This is the industry-standard library for password hashing in Python. It handles all the complexity of salting and hashing securely.
- **`jose`**: This library is used for creating and validating JWTs, which are the standard for stateless API authentication.
- **Stateless by Design**: JWTs are self-contained. The token itself contains the user's identity and an expiration date, so you don't need to look up a session in a database for every single API call, making your API fast and scalable.

#### 2\. `services/auth/service.py` (Core Business Logic)

This is the main service class. It contains the business logic for creating users and authenticating them. It interacts with the database via the `DatabaseManager`.

```python
# AlphasPT_v2/services/auth/service.py

from core.database.connection import DatabaseManager
from core.database.models import User
from sqlalchemy.future import select

from . import security

class AuthService:
    """
    Provides the core business logic for user authentication and management.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def create_user(self, username: str, plain_password: str) -> User:
        """
        Creates a new user in the database with a hashed password.
        """
        hashed_password = security.get_password_hash(plain_password)
        new_user = User(username=username, hashed_password=hashed_password)

        async with self.db_manager.get_session() as session:
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user

    async def authenticate_user(self, username: str, plain_password: str) -> User | None:
        """
        Authenticates a user.

        Returns:
            The User object if authentication is successful, otherwise None.
        """
        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalars().first()

        if not user:
            return None # User not found

        if not security.verify_password(plain_password, user.hashed_password):
            return None # Invalid password

        return user

```

**Explanation:**

- **Decoupled from API**: This class contains pure business logic. It knows how to talk to the database and use the security utilities, but it has no knowledge of FastAPI, HTTP requests, or how it's being used. This makes it easy to test.
- **Async Database Calls**: All database interactions are asynchronous, ensuring the service is non-blocking and can handle concurrent requests efficiently.

#### 3\. `api/routers/auth.py` (The API Endpoints)

Finally, this file exposes the `AuthService`'s functionality to the outside world via FastAPI endpoints.

```python
# AlphasPT_v2/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from dependency_injector.wiring import inject, Provide

from app.containers import AppContainer
from services.auth.service import AuthService
from services.auth.security import create_access_token
from core.config.settings import Settings

router = APIRouter(tags=["Authentication"])

@router.post("/token")
@inject
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service]),
    settings: Settings = Depends(Provide[AppContainer.settings]),
):
    """
    Standard OAuth2 endpoint to authenticate a user and get a JWT.
    """
    user = await auth_service.authenticate_user(
        username=form_data.username,
        plain_password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.username},
        settings=settings
    )

    return {"access_token": access_token, "token_type": "bearer"}

# You would also add endpoints for /register, /users/me, etc. here.
```

**Explanation:**

- **`@inject`**: This decorator from the `dependency-injector` library is the magic that connects everything. It tells FastAPI to get the `AuthService` and `Settings` instances directly from the DI container you defined in `app/containers.py`.
- **OAuth2 Standard**: The `/token` endpoint uses `OAuth2PasswordRequestForm`, which is FastAPI's way of implementing the standard, secure way for a client to request a token.
- **Clear Separation**: The API layer's job is to handle HTTP requests/responses, call the appropriate service method, and handle HTTP-specific errors. The core logic remains neatly in the `AuthService`.

By structuring your authentication this way, you have a clean, secure, and scalable system that neatly separates the concerns of broker communication from user management.
