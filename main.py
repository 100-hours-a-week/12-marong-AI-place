# 필요한 모듈 임포트
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import torch
from sentence_transformers import SentenceTransformer
from RecommendPlace import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import PersistentClient
from chromadb.config import Settings
from datetime import datetime, timedelta

# 기준일: 2025년 5월 12일 (월요일)
base_date = datetime(2025, 5, 12)

# 오늘 날짜
today = datetime.today()

# 회차 계산 함수
def get_week_index(target_date: datetime, base_date: datetime) -> int:
    delta_days = (target_date - base_date).days
    return 1 + (delta_days // 7 + 1 if delta_days >= 0 else 0)  # 기준일 이전이면 0회차

# 오늘의 회차 출력
week_index = get_week_index(today, base_date)

# FastAPI 서버 초기화
app = FastAPI()

# 모델 로딩
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("best_mbti_projector.pt", map_location="cpu"))
mbti_model.eval()

# 임베딩 모델 로딩
embedding_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# Chroma DB 연결
chroma_client = PersistentClient(path="/Users/kimss/Documents/marong/chroma_db", settings=Settings(anonymized_telemetry=False))

# 입력 스키마 정의
class RecommendInput(BaseModel):
    id: str
    eiScore: int
    snScore: int
    tfScore: int
    jpScore: int
    latitude: float
    longitude: float
    likedFoods: List[str] = []
    dislikedFoods: List[str] = []

# 추천 API 엔드포인트
@app.post("/recommend/place")
def recommend_places(input: RecommendInput):
    food_recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=[input.eiScore, input.snScore, input.tfScore, input.jpScore],
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=False
        )

    # recommend 메서드 호출
    food_results = food_recommender.recommend(
        lat=input.latitude,
        lng=input.longitude,
        radius_km=10,
        like_foods=input.likedFoods,
        dislike_foods=input.dislikedFoods
    )

    cafe_recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=[input.eiScore, input.snScore, input.tfScore, input.jpScore],
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=True
    )

    # recommend 메서드 호출
    cafe_results = cafe_recommender.recommend(
        lat=input.latitude,
        lng=input.longitude,
        radius_km=10,
        like_foods=input.likedFoods,
        dislike_foods=input.dislikedFoods
    )

    return {
        "index": f"{week_index}회차",
        "user_id": input.id,
        "message": "recommend_success",
        "food_data": food_results,
        "cafe_data": cafe_results
    }