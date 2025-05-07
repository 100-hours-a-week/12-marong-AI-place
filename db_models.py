from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Users(Base):
    __tablename__ = "Users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(100), nullable=False)
    provider_id = Column(String(100), nullable=False)
    nickname = Column(String(200), nullable=False)

class SurveyMBTI(Base):
    __tablename__ = "SurveyMBTI"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, index=True)
    ei_score = Column(Integer)
    sn_score = Column(Integer)
    tf_score = Column(Integer)
    jp_score = Column(Integer)

class SurveyLikedFood(Base):
    __tablename__ = "SurveyLikedFood"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, index=True)
    food_name = Column(String(100))

class SurveyDislikedFood(Base):
    __tablename__ = "SurveyDislikedFood"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, index=True)
    food_name = Column(String(100))

class PlaceRecommendationSessions(Base):
    __tablename__ = "PlaceRecommendationSessions"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    manittee_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    manitto_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    week = Column(Integer, nullable=False)

    recommendations = relationship("PlaceRecommendations", back_populates="session")

class PlaceRecommendations(Base):
    __tablename__ = "PlaceRecommendations"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("PlaceRecommendationSessions.id"), nullable=False)
    type = Column(String(20), nullable=False)  # 'cafe' or 'restaurant'
    name = Column(String(150), nullable=False)
    category = Column(String(50))
    opening_hours = Column(Text)
    address = Column(String(255))

    session = relationship("PlaceRecommendationSessions", back_populates="recommendations")