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
    user_id: str
    mbti_vector: List[float]
    latitude: float
    longitude: float
    max_distance: float
    like_foods: List[str] = []
    dislike_foods: List[str] = []
    allow_cafe: bool = True

# 추천 API 엔드포인트
@app.post("/recommend/place")
def recommend_places(input: RecommendInput):
    recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=input.mbti_vector,
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=input.allow_cafe
    )

    # recommend 메서드 호출
    results = recommender.recommend(
        lat=input.latitude,
        lng=input.longitude,
        radius_km=input.max_distance,
        like_foods=input.like_foods,
        dislike_foods=input.dislike_foods
    )

    return {
        "user_id": input.user_id,
        "message": "recommend_success",
        "data": results
    }