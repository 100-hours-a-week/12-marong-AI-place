from datetime import datetime, timedelta, time
from chromadb import HttpClient
from dotenv import load_dotenv
from db.db import SessionLocal
from db.db_models import (
    PlaceLikes, PlaceRecommendations
)
from collections import Counter
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
vibelikes_collection = chroma_client.get_or_create_collection(name="vibelikes_collections")
menulikes_collection = chroma_client.get_or_create_collection(name="menulikes_collections")
vlikes_history_collection = chroma_client.get_or_create_collection(name="vlikes_history_collections")
mlikes_history_collection = chroma_client.get_or_create_collection(name="mlikes_history_collections")

review_collection = chroma_client.get_or_create_collection(name="review_collections")
menu_collection = chroma_client.get_or_create_collection(name="menu_collections")

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
  vibe_doc = vibelikes_collection.get(ids=[chroma_user_id], include=["embeddings"])
  menu_doc = menulikes_collection.get(ids=[chroma_user_id], include=["embeddings"])
  start, end = get_last_week_range()
  
  vibe_embed_vector = np.zeros(768)
  menu_embed_vector = np.zeros(768)
  
  if vibe_doc.get("embeddings") and len(vibe_doc["embeddings"]) > 0:
      vibe_embed_vector = np.array(vibe_doc["embeddings"][0])
      
  if menu_doc.get("embeddings") and len(menu_doc["embeddings"]) > 0:
      menu_embed_vector = np.array(menu_doc["embeddings"][0])

  stmt = (
    select(PlaceLikes.id, PlaceRecommendations.name)
    .join(PlaceRecommendations, PlaceLikes.place_id == PlaceRecommendations.id)
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
            where={"name": place_name},
            include=["embeddings"],
            limit=1
        )
        
        vibe_like_history = vlikes_history_collection.get(
            ids=[chroma_placelike_id],
            include=["ids", "metadatas"],
            limit=1
        )
    
    # menu_collection 처리
        menu_result = menu_collection.get(
            where={"name": place_name},
            include=["embeddings"],
            limit=1
        )
        
        menu_like_history = mlikes_history_collection.get(
            ids=[chroma_placelike_id],
            include=["ids", "metadatas"],
            limit=1
        )
        
        condition1 = (review_result.get("embeddings") and len(review_result["embeddings"]) > 0 and 
                        len(vibe_like_history["ids"]) == 0)
        
        condition2 = (menu_result.get("embeddings") and len(menu_result["embeddings"]) > 0 and
                        len(menu_like_history["ids"]) == 0)
        
        if condition1 and condition2:
            vibe_vec = np.array(review_result["embeddings"][0])
            menu_vec = np.array(menu_result["embeddings"][0])
                                
            vibe_embed_vector += 0.01 * vibe_vec
            menu_embed_vector += 0.01 * menu_vec
            
            vlikes_history_collection.add(
                ids=[chroma_placelike_id],
                metadatas=[{"user_id": user_id, "place_name": place_name}]
            )
            
            mlikes_history_collection.add(
                ids=[chroma_placelike_id],
                metadatas=[{"user_id": user_id, "place_name": place_name}]
            )
            
    except Exception as e:
        logger.warning(f"{place_name} 에 대한 임베딩 검색 실패: {e}")
  
  v_tensor = torch.tensor(vibe_embed_vector, dtype=torch.float32)
  if torch.norm(v_tensor) > 0:
    vibe_embed_vector = F.normalize(v_tensor, dim=0).numpy()

  m_tensor = torch.tensor(menu_embed_vector, dtype=torch.float32)
  if torch.norm(m_tensor) > 0:
    menu_embed_vector = F.normalize(m_tensor, dim=0).numpy()
  
  vibelikes_collection.upsert(
        ids=[chroma_user_id],
        embeddings=[vibe_embed_vector.tolist()],
        metadatas=[{"user_id": user_id}]
    )
  
  menulikes_collection.upsert(
        ids=[chroma_user_id],
        embeddings=[menu_embed_vector.tolist()],
        metadatas=[{"user_id": user_id}]
    )