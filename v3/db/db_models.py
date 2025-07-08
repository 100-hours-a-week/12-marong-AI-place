from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, Text, DECIMAL, Boolean, UniqueConstraint, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()

# Users
class Users(Base):
    __tablename__ = "Users"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    provider_id = Column(String(100), nullable=False, unique=True)
    nickname = Column(String(200), nullable=False)
    provider_name = Column(String(100))
    profile_image_url = Column(Text)
    status = Column(String(40), default="active")
    has_completed_survey = Column(Boolean, default=False)

    # 관계 설정
    usergroups = relationship("UserGroups", back_populates="users")
    place_likes = relationship("PlaceLikes", back_populates="users_2")


# Groups
class Groups(Base):
    __tablename__ = "Groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    invite_code = Column(String(6), unique=True, nullable=False)
    image_url = Column(Text)

    # 관계 설정
    usergroups_2 = relationship("UserGroups", back_populates="groups")


# UserGroups
class UserGroups(Base):
    __tablename__ = "UserGroups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), nullable=False)

    # 관계 매핑
    users = relationship("Users", back_populates="usergroups")
    groups = relationship("Groups", back_populates="usergroups_2")

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )

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
    manitto_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    manittee_id = Column(BigInteger, ForeignKey("Users.id"), nullable=False)
    week = Column(Integer, nullable=False)

    place_recommendations = relationship("PlaceRecommendations", back_populates="place_recommendation_sessions")

class PlaceRecommendations(Base):
    __tablename__ = "PlaceRecommendations"
    id = Column(BigInteger, ForeignKey("PlaceLikes.place_recommendation_id", ondelete="CASCADE"), primary_key=True, autoincrement=True, nullable=False)
    session_id = Column(BigInteger, ForeignKey("PlaceRecommendationSessions.id"), nullable=False)
    type = Column(String(20), nullable=False)  # 'cafe' or 'restaurant'
    name = Column(String(150), nullable=False)
    category = Column(String(50))
    opening_hours = Column(Text)
    address = Column(String(255))
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))

    place_recommendation_sessions = relationship("PlaceRecommendationSessions", back_populates="place_recommendations")
    place_likes_2 = relationship(
    "PlaceLikes",
    back_populates="place_recommendations_2",
    foreign_keys="[PlaceLikes.place_recommendation_id]"
    )

    
# Manittos
class Manittos(Base):
    __tablename__ = "Manittos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), index=True, nullable=False)
    manitto_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    manittee_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    week = Column(Integer, nullable=False)
    
    
class PlaceLikes(Base):
    __tablename__ = "PlaceLikes"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), index=True, nullable=False)
    place_recommendation_id = Column(BigInteger, ForeignKey("PlaceRecommendations.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    users_2 = relationship("Users", back_populates="place_likes")
    place_recommendations_2 = relationship(
    "PlaceRecommendations",
    back_populates="place_likes_2",
    foreign_keys=[place_recommendation_id]
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "place_recommendation_id", name="unique_user_place_like"),
    )