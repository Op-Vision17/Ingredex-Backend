"""FastAPI dependencies (auth, DB sessions)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils.jwt_handler import get_token_data
from app.utils.logger import logger

security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Load the authenticated user from JWT ``sub`` or raise 401."""
    token = credentials.credentials
    data = get_token_data(token)
    user_id = data["user_id"]
    user = await db.get(User, user_id)
    if user is None:
        logger.warning("JWT references missing user_id={}", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        logger.warning("Inactive user attempted access: user_id={}", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
