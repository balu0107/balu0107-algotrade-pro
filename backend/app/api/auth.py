from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UserDB
from ..security import create_access_token, get_password_hash, verify_password

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    age: int
    phone_number: str
    gender: str
    notification_preference: str  # "email" | "whatsapp" | "telegram"


@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if db_user: raise HTTPException(status_code=400, detail="Username already registered")
    new_user = UserDB(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name,
        age=user.age,
        phone_number=user.phone_number,
        gender=user.gender,
        notification_preference=user.notification_preference,
    )
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
