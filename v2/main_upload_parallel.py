from datetime import datetime
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from concurrent.futures import ProcessPoolExecutor
from db.db import SessionLocal
from db.db_models import SurveyMBTI, SurveyLikedFood, SurveyDislikedFood, PlaceRecommendationSessions, PlaceRecommendations, Manittos
from sentence_transformers import SentenceTransformer
from core.recommend_place import RecommendPlace
from models.mbti_projector import MBTIProjector
from chromadb import HttpClient
from core.get_week_index import GetWeekIndex
from core.average_latlng import AverageLatLng
import os, torch, logging, asyncio

logger = logging.getLogger("uvicorn.error")
load_dotenv()

base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")
chroma_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT, ssl=False)

embedding_model = SentenceTransformer("./kr-sbert")
mbti_model = MBTIProjector()
mbti_model.load_state_dict(torch.load("./models/best_mbti_projector.pt", map_location="cpu"))
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

def get_avg_vector(me, manitto):
    return [
        (me['eiScore'] + manitto['eiScore']) / 2,
        (me['snScore'] + manitto['snScore']) / 2,
        (me['tfScore'] + manitto['tfScore']) / 2,
        (me['jpScore'] + manitto['jpScore']) / 2
    ]

def run_pair_recommendation(pair_tuple):
    
    pair, week_index = pair_tuple
    db = SessionLocal()
    try:
        manittee_id = pair.manittee_id
        manitto_id = pair.manitto_id
        lat, lng = 37.401115170038, 127.10625450375

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

        print(f"✅ [완료] user_id: {manittee_id} ↔ manitto_id: {manitto_id}")
    except Exception as e:
        logger.error(f"[ERROR] user_id={pair.manittee_id}, manitto_id={pair.manitto_id} 추천 실패: {e}")
    finally:
        db.close()

async def run_batch_parallel():
    start_time = datetime.now()
    print(f"[START] 장소 추천 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    db = SessionLocal()
    pairs = db.query(Manittos).filter(Manittos.week == week_index).all()
    db.close()
    pair_tuples = [(pair, week_index) for pair in pairs]

    loop = asyncio.get_event_loop()
    # Macbook Air 15 M3 16GB RAM 기준
    with ProcessPoolExecutor(max_workers=6) as executor:
        await asyncio.gather(*[
            loop.run_in_executor(executor, run_pair_recommendation, pt)
            for pt in pair_tuples
        ])
        
    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"[END] 장소 추천 실행 완료: {end_time.strftime('%Y-%m-%d %H:%M:%S')} (총 소요 시간: {elapsed})")

if __name__ == "__main__":
    asyncio.run(run_batch_parallel())
