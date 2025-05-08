from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, DateTime, Boolean,
    ForeignKey, func, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# ✅ Users
class Users(Base):
    __tablename__ = "Users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(100), nullable=False, unique=True)
    provider_id = Column(String(100), nullable=False, unique=True)
    nickname = Column(String(200), nullable=False)
    provider_name = Column(String(100))
    profile_image_url = Column(Text)
    status = Column(String(40), default="active")
    has_completed_survey = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    # 🔗 관계 설정
    groups = relationship("UserGroups", back_populates="user")


# ✅ Groups
class Groups(Base):
    __tablename__ = "Groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    invite_code = Column(String(6), unique=True, nullable=False)
    image_url = Column(Text)

    # 🔗 관계 설정
    users = relationship("UserGroups", back_populates="group")


# ✅ UserGroups
class UserGroups(Base):
    __tablename__ = "UserGroups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), nullable=False)

    # 🔗 관계 매핑
    user = relationship("Users", back_populates="groups")
    group = relationship("Groups", back_populates="users")

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )


# ✅ Manittos
class Manittos(Base):
    __tablename__ = "Manittos"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), index=True, nullable=False)
    manittee_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    manitto_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    week = Column(Integer, nullable=False)