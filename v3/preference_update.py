from datetime import datetime, timedelta, time
from chromadb import HttpClient
from dotenv import load_dotenv
from db.db import SessionLocal
from db.db_models import (
    PlaceLikes, PlaceRecommendations
)
from sqlalchemy import select, func
import torch.nn.functional as F
import torch
import logging
import numpy as np
import os

logger = logging.getLogger(__name__)

load_dotenv()
CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT")

chroma_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT, ssl=False)

vibelikes_collection = chroma_client.get_or_create_collection(name="vibelikes_collection")
menulikes_collection = chroma_client.get_or_create_collection(name="menulikes_collection")
vlikes_history_collection = chroma_client.get_or_create_collection(name="vlikes_history_collection")
mlikes_history_collection = chroma_client.get_or_create_collection(name="mlikes_history_collection")

review_collection = chroma_client.get_or_create_collection(name="review_collection")
menu_collection = chroma_client.get_or_create_collection(name="menu_collection")

def get_last_week_range(now: datetime = None):
    now = now or datetime.now()
    days_since_sunday = (now.weekday() + 1) % 7
    this_sunday = now - timedelta(days=days_since_sunday)
    start = datetime.combine((this_sunday - timedelta(days=7)).date(), time.min)
    end   = datetime.combine(this_sunday.date(), time.min)
    return start, end

db = SessionLocal()
user_ids = set(
    row[0] for row in db.query(PlaceLikes.user_id).distinct().all()
)

for user_id in user_ids:
  chroma_user_id = f"user_{user_id}"
  print(f"Processing user_id: {user_id} with chroma_user_id: {chroma_user_id}")
  
  vibe_doc = vibelikes_collection.get(ids=[chroma_user_id], include=["embeddings"])
  menu_doc = menulikes_collection.get(ids=[chroma_user_id], include=["embeddings"])
  start, end = get_last_week_range()
  
  vibe_embed_vector = np.zeros(768)
  menu_embed_vector = np.zeros(768)
  
  if len(vibe_doc["embeddings"]) > 0:
      vibe_embed_vector = np.array(vibe_doc["embeddings"][0])
      
  if len(menu_doc["embeddings"]) > 0:
      menu_embed_vector = np.array(menu_doc["embeddings"][0])
      
  original_vibe_vector = vibe_embed_vector.copy()
  original_menu_vector = menu_embed_vector.copy()

  stmt = (
    select(PlaceLikes.id, PlaceRecommendations.name)
    .join(PlaceRecommendations, PlaceLikes.place_recommendation_id == PlaceRecommendations.id)
    .where(
        PlaceLikes.user_id == user_id,
        start <= PlaceLikes.created_at,
        end > PlaceLikes.created_at
    )
  )
  
  rows = db.execute(stmt).all()
  
  for placelike_id, place_name in rows:
    chroma_placelike_id = f"like_{placelike_id}"
    # review_collection 처리
    try:        
        review_result = review_collection.get(
            where={"상호명": place_name},
            include=["embeddings"],
            limit=1
        )
        
        vibe_like_history = vlikes_history_collection.get(
            ids=[chroma_placelike_id],
            include=["metadatas"],
            limit=1
        )
    
    # menu_collection 처리
        menu_result = menu_collection.get(
            where={"상호명": place_name},
            include=["embeddings"],
            limit=1
        )
        
        menu_like_history = mlikes_history_collection.get(
            ids=[chroma_placelike_id],
            include=["metadatas"],
            limit=1
        )
        
        condition1 = (len(review_result["embeddings"]) > 0 and len(vibe_like_history["ids"]) == 0)
        condition2 = (len(menu_result["embeddings"]) > 0 and len(menu_like_history["ids"]) == 0)
        # print(f"Processing place: {place_name}, conditions: {condition1}, {condition2}")
        
        if condition1 and condition2:
            vibe_vec = np.array(review_result["embeddings"][0])
            menu_vec = np.array(menu_result["embeddings"][0])
            
            # print(f"Found embeddings for {place_name}: vibe_vec={vibe_vec}, menu_vec={menu_vec}")
            vibe_embed_vector += 0.1 * vibe_vec
            menu_embed_vector += 0.1 * menu_vec
            # print(f"Updated vibe_embed_vector: {vibe_embed_vector}, menu_embed_vector: {menu_embed_vector}")
            
            vlikes_history_collection.add(
            ids=[chroma_placelike_id],
            documents=["vibe like record"],  # 꼭 필요
            metadatas=[{"user_id": user_id, "상호명": place_name}]
            )

            mlikes_history_collection.add(
                ids=[chroma_placelike_id],
                documents=["menu like record"],  # 꼭 필요
                metadatas=[{"user_id": user_id, "상호명": place_name}]
            )
                
    except Exception as e:
        logger.warning(f"{place_name}에 대한 임베딩 검색 실패: {e}")
        pass
  
  v_tensor = torch.tensor(vibe_embed_vector, dtype=torch.float32)
  if torch.norm(v_tensor) > 0:
    vibe_embed_vector = F.normalize(v_tensor, dim=0).numpy()

  m_tensor = torch.tensor(menu_embed_vector, dtype=torch.float32)
  if torch.norm(m_tensor) > 0:
    menu_embed_vector = F.normalize(m_tensor, dim=0).numpy()
    
  # 2. 벡터 업데이트 이후 → 차이 계산
  def cosine_similarity(a, b):
      return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

  def l2_distance(a, b):
      return np.linalg.norm(a - b)

  # 변화량 출력
  def safe_cosine_similarity(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return None
    return np.dot(a, b) / (norm_a * norm_b)

  def l2_distance(a, b):
    return np.linalg.norm(a - b)

  vibe_cos = safe_cosine_similarity(original_vibe_vector, vibe_embed_vector)
  menu_cos = safe_cosine_similarity(original_menu_vector, menu_embed_vector)

  vibe_l2 = l2_distance(original_vibe_vector, vibe_embed_vector)
  menu_l2 = l2_distance(original_menu_vector, menu_embed_vector)

  print(f"[user_id: {user_id}] vibe_cos_sim={vibe_cos if vibe_cos is not None else '값 없음'}, vibe_l2={vibe_l2:.4f}")
  print(f"[user_id: {user_id}] menu_cos_sim={menu_cos if menu_cos is not None else '값 없음'}, menu_l2={menu_l2:.4f}")

  
  vibelikes_collection.upsert(
        ids=[chroma_user_id],
        embeddings=[vibe_embed_vector.tolist()],
        documents=["vibe like record"],
        metadatas=[{"user_id": user_id}]
    )
  
  menulikes_collection.upsert(
        ids=[chroma_user_id],
        embeddings=[menu_embed_vector.tolist()],
        documents=["menu like record"],
        metadatas=[{"user_id": user_id}]
    )