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
    def __init__(self, model, embedding_model, me_mbti_vector, manittee_mbti_vector, me_vibe_vector,
                 manittee_vibe_vector, me_menu_vector, manittee_menu_vector, chroma_client,
                 review_col_name, menu_col_name, device, allow_cafe=True, embedding_func=None):
        self.device = device
        self.model = model.to(self.device).eval()
        self.embedding_model = embedding_model.to(self.device)
        self.allow_cafe = allow_cafe
        self.review_collection = chroma_client.get_or_create_collection(name=review_col_name)
        self.menu_collection = chroma_client.get_or_create_collection(name=menu_col_name)
        self.me_mbti_vector = me_mbti_vector
        self.manittee_mbti_vector = manittee_mbti_vector
        self.me_menu_vector = me_menu_vector
        self.manittee_menu_vector = manittee_menu_vector

        self.me_vibe_vector = self._generate_vibe_vector(me_mbti_vector, me_vibe_vector)
        self.manittee_vibe_vector = self._generate_vibe_vector(manittee_mbti_vector, manittee_vibe_vector)

    def _generate_vibe_vector(self, mbti_vector, original_vibe_vector):
        try:
            mbti_keywords = ExtractMBTIKeywords().extract(mbti_vector)
            if not mbti_keywords:
                return torch.zeros((1, 768), device=self.device).cpu().numpy()

            keyword_embs = [self.embedding_model.encode(k, convert_to_tensor=True, device=self.device) for k in mbti_keywords]
            mbti_tensor = F.normalize(torch.stack(keyword_embs).mean(dim=0, keepdim=True), dim=1)

            with torch.no_grad():
                projected = self.model(mbti_tensor)
                vibe_tensor = F.normalize(projected, dim=1)
                return F.normalize(0.7 * vibe_tensor + 0.3 * original_vibe_vector, dim=1).cpu().numpy()
        except Exception as e:
            logger.error(f"MBTI 키워드 임베딩 및 분위기 벡터 생성 실패: {e}")
            raise RuntimeError(f"MBTI 키워드 임베딩 및 분위기 벡터 생성 실패: {e}")

    def calculate_entropy_weights(self, df):
        norm_df = df / df.sum()
        k = 1 / np.log(len(df))
        entropy = -k * (norm_df * np.log(norm_df + 1e-12)).sum()
        diversity = 1 - entropy
        return (diversity / diversity.sum()).to_dict()

    def sigmoid_similarity(self, vec1, vec2, scale=1.0, bias=2.0):
        dist = torch.norm(vec1 - vec2, p=2)
        return 1.0 / (1.0 + torch.exp(scale * (dist - bias)))

    def contains_disliked_food(self, text, disliked_foods):
        return any(food in text for food in disliked_foods if food)

    def recommend(self, lat, lng, radius_km=10.0, top_k=5, like_foods=[], dislike_foods=[]):
        try:
            food_embs = [1.5 * self.embedding_model.encode(f, convert_to_tensor=True, device=self.device) for f in like_foods] + \
                        [-12 * self.embedding_model.encode(f, convert_to_tensor=True, device=self.device) for f in dislike_foods]

            if food_embs:
                food_tensor = F.normalize(torch.stack(food_embs).mean(dim=0, keepdim=True), dim=1).to(self.device)
                self.menu_pref_vector = F.normalize(food_tensor, dim=1)
            else:
                self.menu_pref_vector = torch.zeros((1, 768), device=self.device)

            self.menu_vector = F.normalize(0.7 * self.menu_pref_vector + 0.3 * self.me_menu_vector, dim=1).cpu().numpy()
        except Exception as e:
            logger.error(f"선호 음식 벡터 계산 실패: {e}")
            raise

        def query_collection(collection, query_vector):
            return collection.query(query_embeddings=query_vector, n_results=700, include=["metadatas", "distances", "documents"])

        review_results = query_collection(self.review_collection, self.me_vibe_vector)
        menu_results = query_collection(self.menu_collection, self.menu_vector)

        score_rows = [
            {
                "rating": float(meta.get("평균별점", 0)),
                "distance": haversine(lat, lng, meta.get("위도"), meta.get("경도")),
                "similarity": (1 - dist) * 4
            }
            for meta, dist in zip(review_results["metadatas"][0], review_results["distances"][0])
        ]

        review_df = pd.DataFrame(score_rows)
        review_df["similarity"] = (review_df["similarity"] - review_df["similarity"].min()) / (review_df["similarity"].max() - review_df["similarity"].min() + 1e-12)
        weights = self.calculate_entropy_weights(review_df[["rating", "distance", "similarity"]])

        def process_results(results, weight, allow_cafe):
            scored = {}
            for meta, dist in zip(results.get("metadatas", [[]])[0], results.get("distances", [[]])[0]):
                category = meta.get("대표카테고리", "")
                if allow_cafe and category not in ["카페/디저트"]:
                    continue
                if not allow_cafe and category in ["카페/디저트"]:
                    continue

                store_name = meta.get("상호명", "")
                rating = float(meta.get("평균별점", 0))
                lat_p, lng_p = meta.get("위도"), meta.get("경도")
                if lat_p is None or lng_p is None:
                    continue

                dist_val = haversine(lat, lng, lat_p, lng_p)
                sim_score = max(0.0, tanh((1 - dist) * 3))
                score = CalculateScore(rating, dist_val, sim_score, radius_km, weights).calculate() * weight

                mbti_sim = self.sigmoid_similarity(self.me_mbti_vector, self.manittee_mbti_vector)
                vibe_sim = self.sigmoid_similarity(
                    torch.tensor(self.me_vibe_vector[0], dtype=torch.float32, device=self.device),
                    torch.tensor(self.manittee_vibe_vector[0], dtype=torch.float32, device=self.device)
                )

                menu_sim = self.sigmoid_similarity(
                    torch.tensor(self.me_menu_vector[0], dtype=torch.float32, device=self.device),
                    torch.tensor(self.manittee_menu_vector[0], dtype=torch.float32, device=self.device)
                )

                combined_sim = 0.4 * mbti_sim + 0.3 * vibe_sim + 0.3 * menu_sim
                score *= combined_sim.item()

                menu_text = meta.get("대표메뉴", "") + store_name
                if self.contains_disliked_food(menu_text, dislike_foods):
                    score *= 0.01

                if store_name in scored:
                    scored[store_name]["score"] += score
                else:
                    scored[store_name] = {
                        "name": store_name,
                        "address": meta.get("주소", ""),
                        "rating": rating,
                        "distance": dist_val,
                        "link": meta.get("링크", ""),
                        "score": score,
                        "category": category,
                        "operation_hour": meta.get("영업시간", ""),
                        "latitude": lat_p,
                        "longitude": lng_p
                    }
            return scored

        result_scores = process_results(review_results, 0.4, self.allow_cafe)
        result_scores.update(process_results(menu_results, 0.6, self.allow_cafe))
        return sorted(result_scores.values(), key=lambda x: x["score"], reverse=True)[:top_k]