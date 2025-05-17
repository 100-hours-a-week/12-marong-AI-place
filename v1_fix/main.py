import os
import torch
import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy.orm import Session
# from fastapi import FastAPI, Depends, HTTPException
# from fastapi.responses import JSONResponse
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from typing import List

from db import SessionLocal
from db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations, Manittos
from sentence_transformers import SentenceTransformer
from recommend_place import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import HttpClient
from get_week_index import GetWeekIndex
from average_latlng import AverageLatLng

logger = logging.getLogger("uvicorn.error")
load_dotenv()

base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

executor = asyncio.get_event_loop()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")

chroma_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT, ssl=False)
embedding_model = SentenceTransformer("./kr-sbert")
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("best_mbti_projector.pt", map_location="cpu"))
mbti_model.eval()


def build_user_input(user_id: int, lat: float, lng: float, db: Session):
    mbti = db.query(SurveyMBTI).filter(SurveyMBTI.user_id == user_id).first()
    liked = db.query(SurveyLikedFood).filter(SurveyLikedFood.user_id == user_id).all()
    disliked = db.query(SurveyDislikedFood).filter(SurveyDislikedFood.user_id == user_id).all()

    if mbti is None:
        raise ValueError(f"MBTI 정보가 없습니다: user_id={user_id}")

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


def get_all_pairs(db: Session, week: int):
    return db.query(Manittos).filter(Manittos.week == week).all()


def get_avg_vector(me, manitto):
    return [
        (me['eiScore'] + manitto['eiScore']) / 2,
        (me['snScore'] + manitto['snScore']) / 2,
        (me['tfScore'] + manitto['tfScore']) / 2,
        (me['jpScore'] + manitto['jpScore']) / 2
    ]


def run_batch_recommendation():
    db = SessionLocal()
    try:
        pairs = get_all_pairs(db, week_index)
        history_collection = chroma_client.get_or_create_collection(name="history_collection")

        for pair in pairs:
            manittee_id = pair.manittee_id
            manitto_id = pair.manitto_id

            try:
                # 사용자 위치는 둘 다 동일하다고 가정 (기획 상)
                lat, lng = 37.401115170038, 127.10625450375 # 유스페이스1
                me = build_user_input(manittee_id, lat, lng, db)
                manitto = build_user_input(manitto_id, lat, lng, db)
                avg_vector = get_avg_vector(me, manitto)

                average_loc = AverageLatLng(lat, lng, lat, lng)
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

                food_results = food_recommender.recommend(avg_lat, avg_lng, 10, 5, like_foods, dislike_foods)
                cafe_results = cafe_recommender.recommend(avg_lat, avg_lng, 10, 5, like_foods, dislike_foods)

                for uid in [manittee_id, manitto_id]:
                    session_entry = PlaceRecommendationSessions(
                        manittee_id=uid,
                        manitto_id=manitto_id if uid == manittee_id else manittee_id,
                        week=week_index
                    )
                    db.add(session_entry)
                    db.commit()
                    db.refresh(session_entry)

                    # 추천 결과 저장
                    places_to_add = []
                    for place in food_results + cafe_results:
                        places_to_add.append(PlaceRecommendations(
                            session_id=session_entry.id,
                            type="cafe" if place in cafe_results else "restaurant",
                            name=place['name'],
                            category=place.get('category'),
                            opening_hours=place.get('operation_hour'),
                            address=place.get('address'),
                            latitude=place.get('latitude'),
                            longitude=place.get('longitude')
                        ))
                    db.add_all(places_to_add)
                    db.commit()

                    # ChromaDB 히스토리 저장
                    timestamp = datetime.now().isoformat()
                    history_docs = [place['name'] for place in food_results + cafe_results]
                    history_ids = [f"history__{uuid4()}" for _ in history_docs]
                    history_metas = [{
                        "week": week_index,
                        "user_id": uid,
                        "manitto_id": manitto_id if uid == manittee_id else manittee_id,
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

            except Exception as e:
                logger.error(f"[ERROR] user_id={manittee_id}, manitto_id={manitto_id} 추천 실패: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    run_batch_recommendation()