import os
import torch
import logging
from datetime import datetime
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy.orm import Session
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
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("uvicorn.error")
load_dotenv()

base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get() - 3
print(week_index)

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
def get_chroma_preference(chroma_client, user_id):
    vibelikes_collection = chroma_client.get_or_create_collection(name="vibelikes_collection")
    menulikes_collection = chroma_client.get_or_create_collection(name="menulikes_collection")
    
    chroma_user_id = f"user_{user_id}"
    
    vibe_preference_result = vibelikes_collection.get(
        ids=[chroma_user_id],
        include=["embeddings"],
        limit=1
    )
    
    vibe_embeddings = vibe_preference_result["embeddings"]

    if len(vibe_embeddings) > 0:
        # 이미 저장된 벡터가 있으면 그걸 사용
        user_vibe_embedding = vibe_embeddings[0]
    else:
        # 없으면 더미 벡터 생성
        EMBEDDING_DIM = 768
        dummy_embedding = [0.0] * EMBEDDING_DIM

        # 3) 컬렉션에 add
        vibelikes_collection.add(
            ids=[chroma_user_id],
            embeddings=[dummy_embedding],
            metadatas=[{"user_id": user_id}],
            documents=["user vibe preference record"]
        )

        # 4) 더미 벡터를 사용
        user_vibe_embedding = dummy_embedding
        
    menu_preference_result = menulikes_collection.get(
        ids=[f"user_{user_id}"],
        include=["embeddings"],
        limit=1
    )
    
    menu_embeddings = menu_preference_result["embeddings"]

    if len(menu_embeddings) > 0:
        # 이미 저장된 벡터가 있으면 그걸 사용
        user_menu_embedding = menu_embeddings[0]
    else:
        # 없으면 더미 벡터 생성
        EMBEDDING_DIM = 768
        dummy_embedding = [0.0] * EMBEDDING_DIM

        # 3) 컬렉션에 add
        menulikes_collection.add(
            ids=[chroma_user_id],
            embeddings=[dummy_embedding],
            metadatas=[{"user_id": user_id}],
            documents=["user menu preference record"]
        )

        # 4) 더미 벡터를 사용
        user_menu_embedding = dummy_embedding
        
    return user_vibe_embedding, user_menu_embedding

# User 정보 데이터 구축 함수
def build_user_input(user_id: int, lat: float, lng: float, db: Session):
    vibe_preference, menu_preference = get_chroma_preference(chroma_client, user_id)
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
        "vibe_preference": vibe_preference,
        "menu_preference": menu_preference,
        "latitude": lat,
        "longitude": lng,
        "likedFoods": [x.food_name for x in liked],
        "dislikedFoods": [x.food_name for x in disliked]
    }

# process_pair 함수: DB 업로드 함수
def process_pair(pair, week_index, chroma_client, embedding_model, mbti_model):
    db = SessionLocal()
    
    try:
        manitto_id = pair.manitto_id
        manittee_id = pair.manittee_id
        lat, lng = 37.401115170038, 127.10625450375  # 유스페이스1

        me = build_user_input(manitto_id, lat, lng, db)
        manittee = build_user_input(manittee_id, lat, lng, db)
        
        me_mbti_vector = torch.tensor([me['eiScore'], me['snScore'], me['tfScore'], me['jpScore']], device=device, dtype=torch.float)
        manittee_mbti_vector = torch.tensor([manittee['eiScore'], manittee['snScore'], manittee['tfScore'], manittee['jpScore']], device=device, dtype=torch.float)
        me_vibe_vector = torch.tensor(me['vibe_preference'], device=device, dtype=torch.float)
        manittee_vibe_vector = torch.tensor(manittee['vibe_preference'], device=device, dtype=torch.float)
        me_menu_vector = torch.tensor(me['menu_preference'], device=device, dtype=torch.float)
        manittee_menu_vector = torch.tensor(manittee['menu_preference'], device=device, dtype=torch.float)

        average_loc = AverageLatLng(lat, lng, lat, lng)
        average_loc.loc_to_vec()
        avg_lat, avg_lng = average_loc.get()

        like_foods = list(set(me['likedFoods'] + manittee['likedFoods']))
        dislike_foods = list(set(me['dislikedFoods'] + manittee['dislikedFoods']))

        food_recommender = RecommendPlace(
            model=mbti_model,
            embedding_model=embedding_model,
            me_mbti_vector=me_mbti_vector,
            manittee_mbti_vector=manittee_mbti_vector,
            me_vibe_vector=me_vibe_vector,
            manittee_vibe_vector=manittee_vibe_vector,
            me_menu_vector=me_menu_vector,
            manittee_menu_vector=manittee_menu_vector,
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
            me_mbti_vector=me_mbti_vector,
            manittee_mbti_vector=manittee_mbti_vector,
            me_vibe_vector=me_vibe_vector,
            manittee_vibe_vector=manittee_vibe_vector,
            me_menu_vector=me_menu_vector,
            manittee_menu_vector=manittee_menu_vector,
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
                manittee_id=manittee_id,
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
        
def process_pair_safe(pair, week_index, chroma_client, embedding_model, mbti_model, failed_pairs):
    try:
        process_pair(pair, week_index, chroma_client, embedding_model, mbti_model)
    except Exception as e:
        logger.error(f"[ERROR] user_id={pair.manitto_id}, manittee_id={pair.manittee_id} 추천 실패: {e}")
        failed_pairs.append(pair)

def run_batch_recommendation():
    start_time = datetime.now()
    print(f"[START] 장소 추천 실행 시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    db = SessionLocal()
    try:
        pairs = db.query(Manittos).filter(Manittos.week == week_index).all()
    finally:
        db.close()

    def run_and_collect_failures(pairs_to_run):
        failed = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(process_pair_safe, pair, week_index, chroma_client, embedding_model, mbti_model, failed): pair
                for pair in pairs_to_run
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"[FATAL] 처리 중 예외 발생: {e}")
        return failed

    # 1차 실행
    failed_once = run_and_collect_failures(pairs)

    # 실패한 쌍 재시도
    if failed_once:
        logger.info(f"[RETRY] {len(failed_once)}건 재시도 중...")
        failed_twice = run_and_collect_failures(failed_once)
        if failed_twice:
            logger.warning(f"[FAILED] 재시도 후에도 실패한 쌍 {len(failed_twice)}건:")
            for pair in failed_twice:
                logger.warning(f" - user_id={pair.manitto_id}, manittee_id={pair.manittee_id}")

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"[END] 장소 추천 실행 완료: {end_time.strftime('%Y-%m-%d %H:%M:%S')} (총 소요 시간: {elapsed})")