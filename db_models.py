from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Users(Base):
    __tablename__ = "Users"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)

class SurveyMBTI(Base):
    __tablename__ = "SurveyMBTI"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, index=True, nullable=False)
    ei_score = Column(Integer, nullable=False)
    sn_score = Column(Integer, nullable=False)
    tf_score = Column(Integer, nullable=False)
    jp_score = Column(Integer, nullable=False)

class SurveyLikedFood(Base):
    __tablename__ = "SurveyLikedFood"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, index=True, nullable=False)
    food_name = Column(String(100), nullable=False)

class SurveyDislikedFood(Base):
    __tablename__ = "SurveyDislikedFood"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, index=True, nullable=False)
    food_name = Column(String(100), nullable=False)

class PlaceRecommendationSessions(Base):
    __tablename__ = "PlaceRecommendationSessions"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    manittee_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    manitto_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    week = Column(Integer, nullable=False)

    recommendations = relationship("PlaceRecommendations", back_populates="session")

class PlaceRecommendations(Base):
    __tablename__ = "PlaceRecommendations"
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    session_id = Column(BigInteger, ForeignKey("PlaceRecommendationSessions.id"), nullable=False)
    type = Column(String(20), nullable=False)  # 'cafe' or 'restaurant'
    name = Column(String(150), nullable=False)
    category = Column(String(50))
    opening_hours = Column(Text)
    address = Column(String(255))

    session = relationship("PlaceRecommendationSessions", back_populates="recommendations")