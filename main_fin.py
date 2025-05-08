from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from db import SessionLocal
from db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations
from sentence_transformers import SentenceTransformer
from recommend_place import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import HttpClient
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from datetime import datetime
from get_week_index import GetWeekIndex
from average_latlng import AverageLatLng
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import torch, asyncio, logging

logger = logging.getLogger("uvicorn.error")

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

# 임베딩 모델 로딩
embedding_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# ChromaDB HttpClient 연결
chroma_client = HttpClient(
    host="localhost",
    port=8001,
    ssl=False
)

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
    
    if mbti is None:
        raise HTTPException(status_code=404, detail="MBTI 정보가 없습니다.")

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
    try:
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
            allow_cafe=False,
            embedding_func=None
        )

        cafe_recommender = RecommendPlace(
            model=mbti_model,
            embedding_model=embedding_model,
            mbti_vector=avg_vector,
            chroma_client=chroma_client,
            review_col_name="review_collection",
            menu_col_name="menu_collection",
            allow_cafe=True,
            embedding_func=None
        )

        food_task = recommend_async(food_recommender, lat=avg_lat, lng=avg_lng, radius_km=10,
                                    like_foods=like_foods, dislike_foods=dislike_foods)
        cafe_task = recommend_async(cafe_recommender, lat=avg_lat, lng=avg_lng, radius_km=10,
                                    like_foods=like_foods, dislike_foods=dislike_foods)

        food_results, cafe_results = await asyncio.gather(food_task, cafe_task)

        session_entry = PlaceRecommendationSessions(
            manittee_id=me['id'],
            manitto_id=manitto['id'],
            week=week_index
        )
        db.add(session_entry)
        db.commit()
        db.refresh(session_entry)

        for place in food_results:
            db.add(PlaceRecommendations(
                session_id=session_entry.id,
                type="restaurant",
                name=place['name'],
                category=place.get('category'),
                opening_hours=place.get('operation_hour'),
                address=place.get('address')
            ))

        for place in cafe_results:
            db.add(PlaceRecommendations(
                session_id=session_entry.id,
                type="cafe",
                name=place['name'],
                category=place.get('category'),
                opening_hours=place.get('operation_hour'),
                address=place.get('address')
            ))

        db.commit()

        history_collection = chroma_client.get_or_create_collection(name="history_collection")

        timestamp = datetime.now().isoformat()
        history_docs = []
        history_metas = []
        history_ids = []

        for place in food_results + cafe_results:
            history_docs.append(place['name'])
            history_ids.append(f"history__{uuid4()}")
            history_metas.append({
                "week": week_index,
                "user_id": me['id'],
                "manitto_id": manitto['id'],
                "group_id": 1,  # 필요시 동적 처리
                "place_name": place.get("name"),
                "category": place.get("category"),
                "opening_hours": place.get("operation_hour"),
                "address": place.get("address"),
                "timestamp": timestamp
            })

            history_collection.add(
                ids=history_ids,
                documents=history_docs,
                metadatas=history_metas
            )
        
        return {
            "index": week_index,
            "user_id_pair": [me['id'], manitto['id']],
            "message": "recommend_success",
            "food_data": food_results,
            "cafe_data": cafe_results
        }

    except HTTPException as e:
        raise e  # 기존 HTTPException은 그대로 반환

    except Exception as e:
        logger.error(f"Internal Server Error: {str(e)}")  # 콘솔에 로깅
        return JSONResponse(
            status_code=500,
            content={"message": "서버 내부 오류가 발생했습니다.", "detail": str(e)}
        )