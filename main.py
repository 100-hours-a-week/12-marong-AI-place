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
from get_week_index import GetWeekIndex

# 기준일: 2025년 5월 12일 (월요일)
base_date = datetime(2025, 5, 12)

# 오늘 날짜
today = datetime.today()

# 오늘의 회차 출력
week_index = GetWeekIndex(today, base_date).get()

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
# 기존 RecommendInput 그대로 사용
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

# me + manitto 묶기
class PairInput(BaseModel):
    me: RecommendInput
    manitto: RecommendInput

import math

def average_latlng(lat1, lon1, lat2, lon2):
    # 위도/경도를 라디안으로 변환
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # 위도/경도를 3D 좌표로 변환
    x1, y1, z1 = math.cos(lat1)*math.cos(lon1), math.cos(lat1)*math.sin(lon1), math.sin(lat1)
    x2, y2, z2 = math.cos(lat2)*math.cos(lon2), math.cos(lat2)*math.sin(lon2), math.sin(lat2)

    # 평균 벡터
    x, y, z = (x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2

    # 다시 위도/경도로 변환
    lon = math.atan2(y, x)
    hyp = math.sqrt(x * x + y * y)
    lat = math.atan2(z, hyp)

    # 라디안 → 도(degree)
    return math.degrees(lat), math.degrees(lon)

# 추천 API 엔드포인트
@app.post("/recommend/place")
def recommend_places(input: PairInput):
    # ✅ 평균 벡터 계산
    avg_vector = [
        (input.me.eiScore + input.manitto.eiScore) / 2,
        (input.me.snScore + input.manitto.snScore) / 2,
        (input.me.tfScore + input.manitto.tfScore) / 2,
        (input.me.jpScore + input.manitto.jpScore) / 2,
    ]

    # ✅ 평균 위치
    avg_lat, avg_lng = average_latlng(input.me.latitude, input.me.longitude,  input.manitto.latitude, input.manitto.longitude)

    # ✅ 취향 합치기
    like_foods = list(set(input.me.likedFoods + input.manitto.likedFoods))
    dislike_foods = list(set(input.me.dislikedFoods + input.manitto.dislikedFoods))

    food_recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=avg_vector,
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=False
        )

    # recommend 메서드 호출
    food_results = food_recommender.recommend(
        lat=avg_lat,
        lng=avg_lng,
        radius_km=10,
        like_foods=like_foods,
        dislike_foods=dislike_foods
    )

    cafe_recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=avg_vector,
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=True
    )

    # recommend 메서드 호출
    cafe_results = cafe_recommender.recommend(
        lat=avg_lat,
        lng=avg_lng,
        radius_km=10,
        like_foods=like_foods,
        dislike_foods=dislike_foods
    )

    return {
        "index": f"{week_index}회차",
        "user_id_pair": [input.me.id, input.manitto.id],
        "message": "recommend_success",
        "food_data": food_results,
        "cafe_data": cafe_results
    }