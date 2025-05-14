from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from db import SessionLocal
from db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations, Manittos
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
from dotenv import load_dotenv
import torch, asyncio, logging, os

logger = logging.getLogger("uvicorn.error")

load_dotenv()

executor = ThreadPoolExecutor()

# 비동기 실행 함수
async def recommend_async(recommender, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, lambda: recommender.recommend(*args, **kwargs))

def get_manitto_id_by_manittee(db: Session, manittee_id: int, week: int) -> int:
    entry = db.query(Manittos).filter(
        Manittos.manittee_id == manittee_id,
        Manittos.week == week
    ).first()

    if entry is None:
        raise HTTPException(status_code=404, detail="마니또 정보가 없습니다.")
    
    return entry.manitto_id

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
mbti_model.load_state_dict(torch.load("best_mbti_projector.pt", map_location="cpu"))
mbti_model.eval()

# 임베딩 모델 로딩
embedding_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# ChromaDB 설정
CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")

# ChromaDB HttpClient 연결
chroma_client = HttpClient(
    host=f"{CHROMA_HOST}",
    port=f"{CHROMA_PORT}",
    ssl=False
)

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

async def get_chroma_mbti_with_timeout(chroma_client, me_id, manitto_id, timeout=3):
    loop = asyncio.get_running_loop()
    collection = chroma_client.get_or_create_collection(name="user_latest")

    def blocking_get():
        me_doc = collection.get(where={"id": me_id})
        manitto_doc = collection.get(where={"id": manitto_id})
        return me_doc, manitto_doc

    try:
        me_doc, manitto_doc = await asyncio.wait_for(
            loop.run_in_executor(None, blocking_get),
            timeout=timeout
        )

        if not me_doc or not manitto_doc:
            raise ValueError("MBTI 정보가 하나 이상 존재하지 않음")

        me_data = me_doc[0]
        manitto_data = manitto_doc[0]

        return [
            (me_data['ei_score'] + manitto_data['ei_score']) / 2,
            (me_data['sn_score'] + manitto_data['sn_score']) / 2,
            (me_data['tf_score'] + manitto_data['tf_score']) / 2,
            (me_data['jp_score'] + manitto_data['jp_score']) / 2
        ]

    except Exception as e:
        logger.warning(f"[Timeout or Error] ChromaDB MBTI 조회 실패: {e}")
        return None    

# 추천 요청 엔드포인트
@app.post("/recommend/place")
async def recommend_places(req: RecommendationRequest, db: Session = Depends(get_db)):
    try:
        me = build_user_input(req.me_id, req.me_lat, req.me_lng, db)
        manitto_id = get_manitto_id_by_manittee(db, manittee_id=req.me_id, week=week_index)
        
        # mvp는 사용자 위치를 마니또 위치로 사용
        manitto = build_user_input(manitto_id, req.me_lat, req.me_lng, db)

        avg_vector = await get_chroma_mbti_with_timeout(chroma_client, req.me_id, manitto_id)

        if avg_vector is None:
            logger.info("백엔드 DB에서 MBTI 점수를 가져옵니다.")
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

        # 1. 세션 엔트리 저장
        session_entry = PlaceRecommendationSessions(
            manittee_id=me['id'],
            manitto_id=manitto['id'],
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
            "manitto_id": manitto['id'],
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