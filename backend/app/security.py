"""
Password hashing (bcrypt), JWT creation/verification and role guards.
Role checks happen HERE on the backend — frontend routing is only cosmetic.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from .database import get_db
from .models import Role, User

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    # bcrypt only uses the first 72 bytes
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode())
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please login again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled")
    if user.role != payload.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Role changed, please login again")
    return user


def require_role(*roles: str):
    for r in roles:
        assert r in Role.ALL, r

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this resource")
        return user

    return checker


require_admin = require_role(Role.ADMIN)
require_interviewer = require_role(Role.INTERVIEWER)
require_candidate = require_role(Role.CANDIDATE)
