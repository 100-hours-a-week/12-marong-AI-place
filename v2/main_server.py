from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from db.db import SessionLocal
from db.db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations, Manittos
from sentence_transformers import SentenceTransformer
from core.recommend_place import RecommendPlace
from models.mbti_projector import MBTIProjector
from chromadb import HttpClient
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from datetime import datetime
from core.get_week_index import GetWeekIndex
from core.average_latlng import AverageLatLng
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from dotenv import load_dotenv
import torch, logging, os

logger = logging.getLogger("uvicorn.error")

load_dotenv()

executor = ThreadPoolExecutor()

def get_manittee_id_by_manitto(db: Session, manitto_id: int, week: int) -> int:
    entry = db.query(Manittos).filter(
        Manittos.manitto_id == manitto_id,
        Manittos.week == week
    ).first()

    if entry is None:
        raise HTTPException(status_code=404, detail="마니또 정보가 없습니다.")
    
    return entry.manittee_id

# 날짜 기준 주차 계산
base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

# FastAPI 서버
app = FastAPI()

# TODO: CORS 설정 나중에 지우기
origins = [
    "http://localhost:5173",
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 모델 로딩
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("./models/best_mbti_projector.pt", map_location="cpu"))
mbti_model.eval()

# 임베딩 모델 로딩
embedding_model = SentenceTransformer("./kr-sbert")

# ChromaDB 설정
CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")

# ChromaDB HttpClient 연결
chroma_client = HttpClient(
    host=f"{CHROMA_HOST}",
    port=f"{CHROMA_PORT}",
    ssl=False
)

def get_chroma_mbti(chroma_client, user_id):
    collection = chroma_client.get_or_create_collection(name="user_latest")
    
    user_doc = collection.get(where={"user_id": user_id}, include=["metadatas"])

    try:
        if not user_doc:
            raise ValueError("MBTI 정보가 하나 이상 존재하지 않음")

        user_data = user_doc["metadatas"][0]
        
        return {'ei_score': user_data['ei_score'], 
                'sn_score': user_data['sn_score'],
                'tf_score': user_data['tf_score'],
                'jp_score': user_data['jp_score']}

    except Exception as e:
        logger.warning(f"[Timeout or Error] ChromaDB MBTI 조회 실패: {e}")
        return None

# 입력 스키마
class RecommendationRequest(BaseModel):
    # mvp는 사용자 위치만 사용
    me_id: int
    me_lat: float
    me_lng: float
    # manitto_id: int
    # manitto_lat: float
    # manitto_lng: float

# DB 세션
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 사용자 정보 조합 함수
def build_user_input(user_id: int, lat: float, lng: float, db: Session):
    user_chroma_mbti = get_chroma_mbti(chroma_client, user_id)
    
    mbti = user_chroma_mbti if user_chroma_mbti else db.query(SurveyMBTI).filter(SurveyMBTI.user_id == user_id).first()
    liked = db.query(SurveyLikedFood).filter(SurveyLikedFood.user_id == user_id).all()
    disliked = db.query(SurveyDislikedFood).filter(SurveyDislikedFood.user_id == user_id).all()
    
    if mbti is None:
        raise HTTPException(status_code=404, detail="MBTI 정보가 없습니다.")

    return {
        "id": user_id,
        "eiScore": mbti['ei_score'] if user_chroma_mbti else mbti.ei_score,
        "snScore": mbti['sn_score'] if user_chroma_mbti else mbti.sn_score,
        "tfScore": mbti['tf_score'] if user_chroma_mbti else mbti.tf_score,
        "jpScore": mbti['jp_score'] if user_chroma_mbti else mbti.jp_score,
        "latitude": 37.401115170038,
        "longitude": 127.10625450375,
        "likedFoods": [x.food_name for x in liked],
        "dislikedFoods": [x.food_name for x in disliked]
    } 

# 추천 요청 엔드포인트
@app.post("/recommend/place")
def recommend_places(req: RecommendationRequest, db: Session = Depends(get_db)):
    try:
        me = build_user_input(req.me_id, req.me_lat, req.me_lng, db)
        manittee_id = get_manittee_id_by_manitto(db, manitto_id=req.me_id, week=week_index)
        
        # mvp는 사용자 위치를 마니띠 위치로 사용
        manittee = build_user_input(manittee_id, req.me_lat, req.me_lng, db)

        avg_vector = [
            (me['eiScore'] + manittee['eiScore']) / 2,
            (me['snScore'] + manittee['snScore']) / 2,
            (me['tfScore'] + manittee['tfScore']) / 2,
            (me['jpScore'] + manittee['jpScore']) / 2
        ]

        average_loc = AverageLatLng(me['latitude'], me['longitude'], manittee['latitude'], manittee['longitude'])
        average_loc.loc_to_vec()
        avg_lat, avg_lng = average_loc.get()

        like_foods = list(set(me['likedFoods'] + manittee['likedFoods']))
        dislike_foods = list(set(me['dislikedFoods'] + manittee['dislikedFoods']))

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

        food_results = food_recommender(lat=avg_lat, lng=avg_lng, radius_km=10, like_foods=like_foods, dislike_foods=dislike_foods)
        cafe_results = cafe_recommender(lat=avg_lat, lng=avg_lng, radius_km=10, like_foods=like_foods, dislike_foods=dislike_foods)

        # 1. 세션 엔트리 저장
        session_entry = PlaceRecommendationSessions(
            manitto_id=me['id'],
            manittee_id=manittee['id'],
            week=week_index
        )
        db.add(session_entry)
        db.commit()
        db.refresh(session_entry)

        # 2. 음식점 + 카페 결과를 한 번에 저장
        places_to_add = []

        for place in food_results:
            places_to_add.append(PlaceRecommendations(
                session_id=session_entry.id,
                type="restaurant",
                name=place['name'],
                category=place.get('category'),
                opening_hours=place.get('operation_hour'),
                address=place.get('address'),
                latitude=place.get('latitude'),
                longitude=place.get('longitude')
            ))

        for place in cafe_results:
            places_to_add.append(PlaceRecommendations(
                session_id=session_entry.id,
                type="cafe",
                name=place['name'],
                category=place.get('category'),
                opening_hours=place.get('operation_hour'),
                address=place.get('address'),
                latitude=place.get('latitude'),
                longitude=place.get('longitude')
            ))

        # 한번에 insert
        db.add_all(places_to_add)
        db.commit()

        # 3. ChromaDB 히스토리 저장도 묶어서 호출
        history_collection = chroma_client.get_or_create_collection(name="history_collection")

        timestamp = datetime.now().isoformat()
        history_docs = [place['name'] for place in food_results + cafe_results]
        history_ids = [f"history__{uuid4()}" for _ in history_docs]
        history_metas = [{
            "week": week_index,
            "user_id": me['id'],
            "manitto_id": manittee['id'],
            "place_name": place.get("name"),
            "category": place.get("category"),
            "opening_hours": place.get("operation_hour"),
            "address": place.get("address"),
            "latitude": place.get('latitude'),
            "longitude": place.get('longitude'),
            "timestamp": timestamp
        } for place in food_results + cafe_results]

        # 한번에 add()
        history_collection.add(
            ids=history_ids,
            documents=history_docs,
            metadatas=history_metas
        )

        return {
            "index": week_index,
            "user_id_pair": [me['id'], manittee['id']],
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
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_fin:app", host="0.0.0.0", port=8000, reload=True)