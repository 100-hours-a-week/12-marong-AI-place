import os
import torch
import logging
from datetime import datetime
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, as_completed
from db.db import SessionLocal
from db.db_models import (
    SurveyMBTI, SurveyLikedFood, SurveyDislikedFood,
    PlaceRecommendationSessions, PlaceRecommendations, Manittos
)
from sentence_transformers import SentenceTransformer
from core.recommend_place import RecommendPlace
from models.mbti_projector import MBTIProjector
from chromadb import HttpClient
from core.get_week_index import GetWeekIndex
from core.average_latlng import AverageLatLng

logger = logging.getLogger("uvicorn.error")
load_dotenv()

base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")
chroma_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT, ssl=False)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

embedding_model = SentenceTransformer("./kr-sbert")
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("./models/best_mbti_projector.pt", map_location=device))
mbti_model.to(device)
mbti_model.eval()

# Chroma DB 검색 함수
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
        logger.warning(
            f"[ChromaDB 조회 실패] user_id={user_id}, error={e} → 백엔드 DB에서 재조회 시도"
        )
        return None

# User 정보 데이터 구축 함수
def build_user_input(user_id: int, lat: float, lng: float, db: Session):
    user_chroma_mbti = get_chroma_mbti(chroma_client, user_id)
    mbti = user_chroma_mbti if user_chroma_mbti else db.query(SurveyMBTI).filter(SurveyMBTI.user_id == user_id).first()
    liked = db.query(SurveyLikedFood).filter(SurveyLikedFood.user_id == user_id).all()
    disliked = db.query(SurveyDislikedFood).filter(SurveyDislikedFood.user_id == user_id).all()
    
    if mbti is None:
        raise ValueError(f"MBTI 정보가 없습니다: user_id={user_id}")
    return {
        "id": user_id,
        "eiScore": mbti['ei_score'] if user_chroma_mbti else mbti.ei_score,
        "snScore": mbti['sn_score'] if user_chroma_mbti else mbti.sn_score,
        "tfScore": mbti['tf_score'] if user_chroma_mbti else mbti.tf_score,
        "jpScore": mbti['jp_score'] if user_chroma_mbti else mbti.jp_score,
        "latitude": lat,
        "longitude": lng,
        "likedFoods": [x.food_name for x in liked],
        "dislikedFoods": [x.food_name for x in disliked]
    }

# 마니또, 마니띠 성향 평균 함수
def get_avg_vector(me, manittee):
    return [
        (me['eiScore'] + manittee['eiScore']) / 2,
        (me['snScore'] + manittee['snScore']) / 2,
        (me['tfScore'] + manittee['tfScore']) / 2,
        (me['jpScore'] + manittee['jpScore']) / 2
    ]

# process_pair 함수: DB 업로드 함수
def process_pair(pair, week_index, chroma_client, embedding_model, mbti_model):
    db = SessionLocal()
    
    try:
        manitto_id = pair.manitto_id
        manittee_id = pair.manittee_id
        lat, lng = 37.401115170038, 127.10625450375  # 유스페이스1

        me = build_user_input(manitto_id, lat, lng, db)
        manittee = build_user_input(manittee_id, lat, lng, db)
        avg_vector = get_avg_vector(me, manittee)

        average_loc = AverageLatLng(lat, lng, lat, lng)
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
            device=device,
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
            device=device,
            allow_cafe=True,
            embedding_func=None
        )

        food_results = food_recommender.recommend(avg_lat, avg_lng, 10, 5, like_foods, dislike_foods)
        cafe_results = cafe_recommender.recommend(avg_lat, avg_lng, 10, 5, like_foods, dislike_foods)
        
        history_collection = chroma_client.get_or_create_collection(name="history_collection")

        for uid in [manitto_id]:
            session_entry = PlaceRecommendationSessions(
                manitto_id=uid,
                manittee_id=manittee_id if uid == manitto_id else manitto_id,
                week=week_index
            )
            db.add(session_entry)
            db.commit()
            db.refresh(session_entry)

            places_to_add = [
                PlaceRecommendations(
                    session_id=session_entry.id,
                    type="cafe" if place in cafe_results else "restaurant",
                    name=place['name'],
                    category=place.get('category'),
                    opening_hours=place.get('operation_hour'),
                    address=place.get('address'),
                    latitude=place.get('latitude'),
                    longitude=place.get('longitude')
                )
                for place in food_results + cafe_results
            ]
            db.add_all(places_to_add)
            db.commit()

            timestamp = datetime.now().isoformat()
            history_docs = [place['name'] for place in food_results + cafe_results]
            history_ids = [f"history__{uuid4()}" for _ in history_docs]
            history_metas = [{
                "week": week_index,
                "user_id": uid,
                "manitto_id": manitto_id,
                "manitte_id": manittee_id,
                "place_name": place.get("name"),
                "category": place.get("category"),
                "opening_hours": place.get("operation_hour"),
                "address": place.get("address"),
                "latitude": place.get('latitude'),
                "longitude": place.get('longitude'),
                "timestamp": timestamp
            } for place in food_results + cafe_results]

            history_collection.add(
                ids=history_ids,
                documents=history_docs,
                metadatas=history_metas
            )

        print(f"[완료] user_id: {manitto_id} ↔ manittee_id: {manittee_id}")

    except Exception as e:
        logger.error(f"[ERROR] user_id={pair.manitto_id}, manittee_id={pair.manittee_id} 추천 실패: {e}")
        
# run_batch_recommendation 함수: 장소 추천 실행 함수
def run_batch_recommendation():
    start_time = datetime.now()
    print(f"[START] 장소 추천 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()
    try:
        pairs = db.query(Manittos).filter(Manittos.week == week_index).all()
    finally:
        db.close()
        
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(process_pair, pair, week_index, chroma_client, embedding_model, mbti_model)
            for pair in pairs
        ]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"[ERROR] 추천 처리 실패: {e}")

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"[END] 장소 추천 실행 완료: {end_time.strftime('%Y-%m-%d %H:%M:%S')} (총 소요 시간: {elapsed})")