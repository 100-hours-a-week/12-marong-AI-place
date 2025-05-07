from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from db import SessionLocal
from db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations
from sentence_transformers import SentenceTransformer
from recommend_place import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import PersistentClient
from chromadb.config import Settings
from datetime import datetime
from get_week_index import GetWeekIndex
from average_latlng import AverageLatLng
from concurrent.futures import ThreadPoolExecutor
import torch, asyncio

executor = ThreadPoolExecutor()

# 비동기 실행 함수
async def recommend_async(recommender, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: recommender.recommend(*args, **kwargs))

# 날짜 기준 주차 계산
base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

# FastAPI 서버
app = FastAPI()

# 모델 로딩
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("best_mbti_projector.pt", map_location="cpu"))
mbti_model.eval()
embedding_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
chroma_client = PersistentClient(path="/Users/kimss/Documents/marong/chroma_db", settings=Settings(anonymized_telemetry=False))

# 입력 스키마
class RecommendationRequest(BaseModel):
    me_id: int
    manitto_id: int
    me_lat: float
    me_lng: float
    manitto_lat: float
    manitto_lng: float

# DB 세션
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 사용자 정보 조합 함수
def build_user_input(user_id: int, lat: float, lng: float, db: Session):
    mbti = db.query(SurveyMBTI).filter(SurveyMBTI.user_id == user_id).first()
    liked = db.query(SurveyLikedFood).filter(SurveyLikedFood.user_id == user_id).all()
    disliked = db.query(SurveyDislikedFood).filter(SurveyDislikedFood.user_id == user_id).all()

    return {
        "id": user_id,
        "eiScore": mbti.ei_score,
        "snScore": mbti.sn_score,
        "tfScore": mbti.tf_score,
        "jpScore": mbti.jp_score,
        "latitude": lat,
        "longitude": lng,
        "likedFoods": [x.food_name for x in liked],
        "dislikedFoods": [x.food_name for x in disliked]
    }

# 추천 요청 엔드포인트
@app.post("/recommend/place")
async def recommend_places(req: RecommendationRequest, db: Session = Depends(get_db)):
    me = build_user_input(req.me_id, req.me_lat, req.me_lng, db)
    manitto = build_user_input(req.manitto_id, req.manitto_lat, req.manitto_lng, db)

    avg_vector = [
        (me['eiScore'] + manitto['eiScore']) / 2,
        (me['snScore'] + manitto['snScore']) / 2,
        (me['tfScore'] + manitto['tfScore']) / 2,
        (me['jpScore'] + manitto['jpScore']) / 2
    ]

    average_loc = AverageLatLng(me['latitude'], me['longitude'], manitto['latitude'], manitto['longitude'])
    average_loc.loc_to_vec()
    avg_lat, avg_lng = average_loc.get()

    like_foods = list(set(me['likedFoods'] + manitto['likedFoods']))
    dislike_foods = list(set(me['dislikedFoods'] + manitto['dislikedFoods']))

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

    food_task = recommend_async(food_recommender, lat=avg_lat, lng=avg_lng, radius_km=10, like_foods=like_foods, dislike_foods=dislike_foods)
    cafe_task = recommend_async(cafe_recommender, lat=avg_lat, lng=avg_lng, radius_km=10, like_foods=like_foods, dislike_foods=dislike_foods)

    food_results, cafe_results = await asyncio.gather(food_task, cafe_task)

    # ✅ 추천 세션 저장
    session_entry = PlaceRecommendationSessions(
        manittee_id=me['id'],
        manitto_id=manitto['id'],
        week=week_index
    )
    db.add(session_entry)
    db.commit()
    db.refresh(session_entry)  # 세션 ID 확보

    # ✅ 장소 추천 저장
    for place in food_results:
        db.add(PlaceRecommendations(
            session_id=session_entry.id,
            type="restaurant",
            name=place['name'],
            category=place.get('category'),
            opening_hours=place.get('operation_hour')
        ))

    for place in cafe_results:
        db.add(PlaceRecommendations(
            session_id=session_entry.id,
            type="cafe",
            name=place['name'],
            category=place.get('category'),
            opening_hours=place.get('operation_hour')
        ))

    db.commit()

    return {
        "index": week_index,
        "user_id_pair": [me['id'], manitto['id']],
        "message": "recommend_success",
        "food_data": food_results,
        "cafe_data": cafe_results
    }