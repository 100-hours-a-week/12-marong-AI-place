import torch
import torch.nn.functional as F
from core.haversine import haversine
from models.extract_mbti_keywords import ExtractMBTIKeywords
from core.calculate_score import CalculateScore
import pandas as pd
import numpy as np
from math import tanh
import logging

logger = logging.getLogger(__name__)

class RecommendPlace:
    def __init__(self, model, embedding_model, mbti_vector, chroma_client,
                 review_col_name, menu_col_name, device, allow_cafe=True, embedding_func=None):
        self.device = device
        self.model = model.to(self.device).eval()
        self.embedding_model = embedding_model.to(self.device)
        self.allow_cafe = allow_cafe

        # 예외 처리: Chroma 컬렉션 초기화
        try:
            self.review_collection = chroma_client.get_or_create_collection(
                name=review_col_name,
                embedding_function=None
            )
            self.menu_collection = chroma_client.get_or_create_collection(
                name=menu_col_name,
                embedding_function=None
            )
        except Exception as e:
            logger.error(f"Chroma 컬렉션 초기화 실패: {e}")
            raise RuntimeError(f"Chroma 컬렉션 초기화 실패: {e}")

        # 예외 처리: MBTI 키워드 임베딩 및 투영
        try:
            mbti_keywords = ExtractMBTIKeywords().extract(mbti_vector)
            if not mbti_keywords:
                self.user_vibe = torch.zeros((1, 768), device=self.device).numpy()
                return

            keyword_embs = [self.embedding_model.encode(k, convert_to_tensor=True, device=self.device).to(self.device) for k in mbti_keywords]
            mbti_tensor = F.normalize(torch.stack(keyword_embs).mean(dim=0, keepdim=True), dim=1)

            with torch.no_grad():
                projected = self.model(mbti_tensor)
                self.user_vibe = F.normalize(projected, dim=1).cpu().numpy()
                self.user_vibe_tensor = torch.tensor(self.user_vibe, device=self.device)
        except Exception as e:
            logger.error(f"MBTI 키워드 임베딩 또는 투영 실패: {e}")
            raise RuntimeError(f"MBTI 키워드 임베딩 또는 투영 실패: {e}")

    def calculate_entropy_weights(self, df):
        norm_df = df / df.sum()
        k = 1 / np.log(len(df))
        entropy = -k * (norm_df * np.log(norm_df + 1e-12)).sum()
        diversity = 1 - entropy
        return (diversity / diversity.sum()).to_dict()

    def recommend(self, lat, lng, radius_km=10.0, top_k=5, like_foods=[], dislike_foods=[]):
        try:
            food_embs = []
            for food in like_foods:
                food_embs.append(1.5 * self.embedding_model.encode(food, convert_to_tensor=True, device=self.device))
            for food in dislike_foods:
                food_embs.append(-4.5 * self.embedding_model.encode(food, convert_to_tensor=True, device=self.device))

            if food_embs:
                food_tensor = F.normalize(torch.stack(food_embs).mean(dim=0, keepdim=True), dim=1).to(self.device)
                user_pref_vector = F.normalize(
                    self.user_vibe_tensor + food_tensor, dim=1
                ).cpu().numpy()
            else:
                user_pref_vector = self.user_vibe
        except Exception as e:
            logger.error(f"선호 음식 벡터 계산 실패: {e}")
            raise RuntimeError(f"선호 음식 벡터 계산 실패: {e}")

        try:
            top_k_each = int(400 * (1.5 if self.allow_cafe else 1))

            review_results = self.review_collection.query(
                query_embeddings=user_pref_vector,
                n_results=top_k_each,
                include=["metadatas", "distances", "documents"]
            )
        except Exception as e:
            logger.error(f"리뷰 임베딩 쿼리 실패: {e}")
            raise RuntimeError(f"리뷰 임베딩 쿼리 실패: {e}")

        try:
            menu_results = self.menu_collection.query(
                query_embeddings=user_pref_vector,
                n_results=top_k_each,
                include=["metadatas", "distances", "documents"]
            )
        except Exception as e:
            logger.error(f"메뉴 임베딩 쿼리 실패: {e}")
            raise RuntimeError(f"메뉴 임베딩 쿼리 실패: {e}")
        
        try:
            score_rows = []
            for metadata, dist in zip(review_results["metadatas"][0], review_results["distances"][0]):
                sim = (1 - dist) * 4
                score_rows.append({
                    "rating": float(metadata.get("평균별점", 0)),
                    "distance": haversine(lat, lng, metadata.get("위도"), metadata.get("경도")),
                    "similarity": sim
                })

            review_df = pd.DataFrame(score_rows)

            review_df["similarity"] = (
                (review_df["similarity"] - review_df["similarity"].min()) /
                (review_df["similarity"].max() - review_df["similarity"].min() + 1e-12)
            )

            weights = self.calculate_entropy_weights(review_df[["rating", "distance", "similarity"]])
        except Exception as e:
            logger.error(f"스코어 정규화 및 가중치 계산 실패: {e}")
            raise RuntimeError(f"스코어 정규화 및 가중치 계산 실패: {e}")

        try:
            scored = {}

            def process_results(results, weight, Flag, T):
                for metadata, distance in zip(results.get("metadatas", [[]])[0], results.get("distances", [[]])[0]):
                    store_id = metadata.get("상호명", "")
                    rating = float(metadata.get("평균별점", 0))
                    lat_p, lng_p = metadata.get("위도"), metadata.get("경도")

                    if Flag:
                        if metadata.get("대표카테고리", "") not in ["카페/디저트"]:
                            continue
                    else:
                        if metadata.get("대표카테고리", "") in ["카페/디저트"]:
                            continue

                    if lat_p is None or lng_p is None:
                        continue

                    dist = haversine(lat, lng, lat_p, lng_p)
                    sim_score = max(0.0, tanh((1 - distance) * 3))

                    score = CalculateScore(rating, dist, sim_score, radius_km, weights).calculate() * weight

                    if store_id in scored:
                        scored[store_id]["score"] += score
                    else:
                        scored[store_id] = {
                            "name": store_id,
                            "address": metadata.get("주소", ""),
                            "rating": rating,
                            "distance": dist,
                            "link": metadata.get("링크", ""),
                            "score": score,
                            "category": metadata.get("대표카테고리", "미분류"),
                            "operation_hour": metadata.get("영업시간", ""),
                            "latitude": lat_p,
                            "longitude": lng_p
                        }

            process_results(review_results, 0.4, self.allow_cafe, 0.2)
            process_results(menu_results, 0.6, self.allow_cafe, 0.2)

            result = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:top_k]
            return result
        except Exception as e:
            logger.error(f"추천 결과 처리 중 오류: {e}")
            raise RuntimeError(f"추천 결과 처리 중 오류: {e}")