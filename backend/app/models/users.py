from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    phone_number = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    notification_preference = Column(String, nullable=True)  # "email" | "whatsapp" | "telegram"

    alert_rules = relationship("AlertRuleDB", back_populates="owner", cascade="all, delete-orphan")
