"""Password hashing, JWT issuing/verification, and the current-user
dependency every route depends on. Kept as one small top-level module
(alongside config.py/database.py) rather than under api/ or services/,
since it's a cross-cutting concern every api/*.py route file needs."""
import datetime

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import UserDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def seed_default_user():
    """Creates the admin/admin account so it can be used without signing up.
    Dev/demo convenience only - never runs when ENVIRONMENT=production, so a
    real deployment never gets a default admin/admin account seeded into
    whatever database it points to."""
    if config.ENVIRONMENT == "production":
        return
    from .database import SessionLocal

    db = SessionLocal()
    try:
        if not db.query(UserDB).filter(UserDB.username == "admin").first():
            db.add(UserDB(
                username="admin",
                hashed_password=get_password_hash("admin"),
                full_name="Admin",
                notification_preference="email",
            ))
            db.commit()
    finally:
        db.close()
