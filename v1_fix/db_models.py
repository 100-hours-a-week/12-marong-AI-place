from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, Text, DECIMAL, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# ✅ Users
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

    # 🔗 관계 설정
    groups = relationship("UserGroups", back_populates="user")


# ✅ Groups
class Groups(Base):
    __tablename__ = "Groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    invite_code = Column(String(6), unique=True, nullable=False)
    image_url = Column(Text)

    # 🔗 관계 설정
    users = relationship("UserGroups", back_populates="group")


# ✅ UserGroups
class UserGroups(Base):
    __tablename__ = "UserGroups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), nullable=False)

    # 🔗 관계 매핑
    user = relationship("Users", back_populates="groups")
    group = relationship("Groups", back_populates="users")

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
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))

    session = relationship("PlaceRecommendationSessions", back_populates="recommendations")
    
# ✅ Manittos
class Manittos(Base):
    __tablename__ = "Manittos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    group_id = Column(BigInteger, ForeignKey("Groups.id", ondelete="CASCADE"), index=True, nullable=False)
    manitto_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    manittee_id = Column(BigInteger, ForeignKey("Users.id", ondelete="CASCADE"), nullable=False)
    week = Column(Integer, nullable=False)