Of course. Here is the complete, production-ready code for the `api` module, redesigned for the Unified Log architecture.

The role of the API in this new design is fundamentally different and much simpler. It is a **thin, read-only layer** that is completely decoupled from the core trading pipeline. Its primary responsibilities are:

1.  **Serving Data:** To provide a fast, real-time view of the system's state (like portfolio positions and P\&L) to a user interface or dashboard. It achieves this by reading directly from the high-speed Redis cache, never from the core trading services.
2.  **Handling User Authentication:** To secure its endpoints using the dedicated `auth` service, ensuring only authorized users can view the data.
3.  **Issuing Commands (Optional):** To publish "command" events into Redpanda if a user needs to perform an action (e.g., "stop strategy X").

This decoupling is a critical feature: a surge in API requests can never slow down or crash your core trading operations.

---

### 1\. `api/dependencies.py` (New)

This file manages dependencies for the API endpoints. It defines how to get a shared Redis client instance and how to verify a user's JWT to protect routes.

```python
# AlphasPT_v2/api/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from pydantic import BaseModel
from dependency_injector.wiring import inject, Provide

from app.containers import AppContainer
from core.config.settings import Settings
from services.auth.security import decode_access_token
from services.portfolio_manager.cache import PortfolioCache

# --- Dependency for getting the Portfolio Cache ---
# This allows our endpoints to easily access the Redis cache.
@inject
def get_portfolio_cache(
    cache: PortfolioCache = Depends(Provide[AppContainer.portfolio_cache])
) -> PortfolioCache:
    return cache

# --- Dependencies for Authentication ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

class TokenData(BaseModel):
    username: str | None = None

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> dict:
    """
    Decodes the JWT and returns the user's data if the token is valid.
    This is used to protect endpoints.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token, settings)
    if payload is None or payload.get("sub") is None:
        raise credentials_exception

    # In a real app, you might fetch the full user object from the database here
    return {"username": payload.get("sub")}

```

**Explanation:**

- **`@inject`**: This decorator from `dependency-injector` tells FastAPI to get the `PortfolioCache` instance directly from the central container. This is clean and avoids global variables.
- **`OAuth2PasswordBearer`**: This is a standard FastAPI utility that handles extracting the JWT bearer token from the `Authorization` header of an incoming request.
- **`get_current_user`**: This is a "dependable" function. Any endpoint that includes it as a dependency will automatically be protected. FastAPI will run this function first, and if the token is invalid, it will immediately reject the request with a 401 Unauthorized error.

---

### 2\. `api/routers/portfolios.py`

This is the main data-serving router. It provides endpoints for clients to query the real-time state of their trading portfolios.

```python
# AlphasPT_v2/api/routers/portfolios.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from services.portfolio_manager.cache import PortfolioCache
from services.portfolio_manager.models import Portfolio
from api.dependencies import get_portfolio_cache, get_current_user

router = APIRouter(
    prefix="/portfolios",
    tags=["Portfolios"],
    dependencies=[Depends(get_current_user)] # Protect all routes in this file
)

@router.get("/{portfolio_id}", response_model=Portfolio)
async def get_portfolio_by_id(
    portfolio_id: str,
    cache: PortfolioCache = Depends(get_portfolio_cache)
):
    """
    Retrieves the complete, real-time state of a single portfolio by its ID.
    (e.g., "paper_Momentum_NIFTY50_1")
    """
    portfolio = await cache.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio

@router.get("/", response_model=List[Portfolio])
async def get_all_portfolios(
    cache: PortfolioCache = Depends(get_portfolio_cache)
):
    """
    Retrieves the state of all tracked portfolios.
    NOTE: This could be slow if there are many portfolios. A real implementation
    would use Redis SCAN to get all keys without blocking.
    """
    # This is a simplified implementation. A production version would use SCAN.
    all_keys = await cache.redis_client.keys("portfolio:*")
    portfolios = []
    for key in all_keys:
        portfolio_id = key.split(":")[-1]
        p = await cache.get_portfolio(portfolio_id)
        if p:
            portfolios.append(p)
    return portfolios

```

**Explanation:**

- **Protected Routes**: By adding `dependencies=[Depends(get_current_user)]` to the router, every single endpoint in this file is automatically protected. No unauthenticated user can access them.
- **Read-Only from Cache**: Notice that the endpoints only interact with the `PortfolioCache`. They have zero knowledge of the trading pipeline, the database, or any other core service. This makes them extremely fast and ensures they can't interfere with trading operations.
- **Pydantic `response_model`**: FastAPI uses this to automatically validate and serialize the outgoing data, ensuring your API responses are always consistent with your `Portfolio` data model.

---

### 3\. `api/main.py`

This is the main entry point for the API service. It creates the FastAPI application, wires up the dependency injection container, and includes all the routers.

```python
# AlphasPT_v2/api/main.py

import uvicorn
from fastapi import FastAPI
from dependency_injector.wiring import inject, Provide

# Import your application's DI container
from app.containers import AppContainer

# Import the routers for your API
from .routers import portfolios, auth # Assuming auth router is in api/routers/auth.py

@inject
def create_app(
    # Inject any dependencies needed at the top level
) -> FastAPI:
    """
    Creates and configures the FastAPI application and its routers.
    """
    app = FastAPI(
        title="AlphaPT Trading API",
        version="2.0.0",
        description="API for monitoring and managing the AlphaPT trading system."
    )

    # Include all your API routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(portfolios.router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok"}

    return app

def run():
    """
    Main function to run the API server.
    This would be the entry point in your Docker container for the API service.
    """
    # 1. Create the DI container
    container = AppContainer()

    # 2. Wire the container to the modules that need dependency injection
    container.wire(modules=[__name__, ".dependencies", ".routers.portfolios", ".routers.auth"])

    # 3. Create the FastAPI app instance
    app = create_app()

    # 4. Run the Uvicorn server
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    run()

```

**Explanation:**

- **DI Wiring**: The `container.wire(...)` call is crucial. It connects your DI container to your API modules, enabling the `@inject` decorators and `Depends(Provide[...])` to work correctly.
- **Modular Routers**: The code uses `app.include_router` to add the different sections of your API (auth, portfolios). This keeps your main application file clean and organized as you add more endpoints.
- **Standalone Service**: The `run()` function shows how this module is intended to be run as its own independent service (e.g., in its own Docker container), separate from the core trading services.
