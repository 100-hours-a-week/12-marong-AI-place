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
        "user_id": input.id,
        "message": "recommend_success",
        "food_data": food_results,
        "cafe_data": cafe_results
    }