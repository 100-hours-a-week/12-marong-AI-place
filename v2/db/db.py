from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 커넥션 풀 설정 추가
engine = create_engine(
    DATABASE_URL,
    pool_size=20,          # 기본값은 5 → 동시에 유지되는 커넥션 수
    max_overflow=30,       # 초과 시 임시 커넥션 수 (총 50까지 허용됨)
    pool_timeout=30,       # 커넥션 대기 시간 (초)
    pool_recycle=1800,     # 30분 후 커넥션 재활용
    pool_pre_ping=True     # 커넥션 유효성 검사
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)