from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Text

Base = declarative_base()

class Users(Base):
    __tablename__ = "Users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
class Groups(Base):
    __tablename__ = "Groups"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    invite_code = Column(String(6), unique=True, nullable=False)
    image_url = Column(Text)

class Manittos(Base):
    __tablename__ = "Manittos"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("Groups.id"), index=True, nullable=False)
    giver_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    receiver_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    week = Column(Integer, nullable=False)