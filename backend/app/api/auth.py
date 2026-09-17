"""Authentication router supporting login token exchange and new user registration.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UserDB
from ..security import get_password_hash, verify_password, create_access_token

router = APIRouter(tags=["auth"])


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    age: int
    phone_number: str
    gender: str
    notification_preference: str = "email"


@router.post("/token")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(UserDB).filter(UserDB.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered",
        )
    
    hashed_password = get_password_hash(payload.password)
    new_user = UserDB(
        username=payload.username,
        hashed_password=hashed_password,
        full_name=payload.full_name,
        age=payload.age,
        phone_number=payload.phone_number,
        gender=payload.gender,
        notification_preference=payload.notification_preference,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User registered successfully", "username": new_user.username}