# 필요한 모듈 임포트
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from sentence_transformers import SentenceTransformer
from recommend_place import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import PersistentClient
from chromadb.config import Settings
from datetime import datetime, timedelta
from get_week_index import GetWeekIndex
from average_latlng import AverageLatLng
from concurrent.futures import ThreadPoolExecutor
import torch, math, asyncio

executor = ThreadPoolExecutor()

async def recommend_async(recommender, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        lambda: recommender.recommend(*args, **kwargs)
    )

# 기준일: 2025년 1월 1일
base_date = datetime(2025, 1, 1)

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
    id: int
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

# 추천 API 엔드포인트
@app.post("/recommend/place")
async def recommend_places(input: PairInput):
    # 평균 벡터 계산
    avg_vector = [
        (input.me.eiScore + input.manitto.eiScore) / 2,
        (input.me.snScore + input.manitto.snScore) / 2,
        (input.me.tfScore + input.manitto.tfScore) / 2,
        (input.me.jpScore + input.manitto.jpScore) / 2,
    ]
    # 평균 위치
    average_loc = AverageLatLng(input.me.latitude, input.me.longitude, input.manitto.latitude, input.manitto.longitude)
    average_loc.loc_to_vec()
    avg_lat, avg_lng = average_loc.get()

    # 취향 합치기
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

    cafe_recommender = RecommendPlace(
        model=mbti_model,
        embedding_model=embedding_model,
        mbti_vector=avg_vector,
        chroma_client=chroma_client,
        review_col_name="review_collection",
        menu_col_name="menu_collection",
        allow_cafe=True
    )
    
    food_task = recommend_async(
        food_recommender,
        lat=avg_lat,
        lng=avg_lng,
        radius_km=10,
        like_foods=like_foods,
        dislike_foods=dislike_foods
    )

    cafe_task = recommend_async(
        cafe_recommender,
        lat=avg_lat,
        lng=avg_lng,
        radius_km=10,
        like_foods=like_foods,
        dislike_foods=dislike_foods
    )

    food_results, cafe_results = await asyncio.gather(food_task, cafe_task)

    return {
        "index": week_index,
        "user_id_pair": [input.me.id, input.manitto.id],
        "message": "recommend_success",
        "food_data": food_results,
        "cafe_data": cafe_results
    }