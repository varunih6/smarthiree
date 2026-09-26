from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Role, User
from ..schemas import LoginIn, RegisterIn, ResetPasswordIn
from ..security import (create_access_token, get_current_user, hash_password,
                        verify_password)
from ..services.audit import audit, notify
from ..services.views import user_view

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID = "Invalid credentials"


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    # same generic message for every failure (no user enumeration)
    if not user or user.role != body.role or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, INVALID)
    if not user.is_active:
        raise HTTPException(403, "Your account has been deactivated. Contact the admin.")
    audit(db, user, "LOGIN", "user", user.id, f"{user.role} login")
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_view(user)}


@router.post("/register", status_code=201)
def register_candidate(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Please login instead.")
    if db.query(User).filter(User.mobile == body.mobile).first():
        raise HTTPException(409, "An account with this mobile number already exists.")
    user = User(full_name=body.full_name, email=email, mobile=body.mobile,
                password_hash=hash_password(body.password), role=Role.CANDIDATE)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # DB-level UNIQUE constraint as the final guard
        db.rollback()
        raise HTTPException(409, "Candidate already exists with this email or mobile number.")
    audit(db, user, "CANDIDATE_REGISTERED", "user", user.id, f"{user.full_name} <{email}>")
    db.commit()
    notify(email, "Welcome to SmartHire", "Registration successful")
    # NOTE: no token returned -> candidate must log in manually
    return {"message": "Successfully registered. Please login using your email and password."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or (body.role and user.role != body.role):
        raise HTTPException(404, "No account found with this email.")
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "PASSWORD_RESET", "user", user.id, "Password reset via reset page")
    db.commit()
    return {"message": "Password Reset Successful", "role": user.role}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_view(user)


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit(db, user, "LOGOUT", "user", user.id, "")
    db.commit()
    return {"message": "Logged out"}
