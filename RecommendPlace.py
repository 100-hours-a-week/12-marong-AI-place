import torch
import torch.nn.functional as F
from haversine import haversine
from extract_mbti_keywords import ExtractMBTIKeywords
from calculate_score import CalculateScore

class RecommendPlace:
    def __init__(self, model, embedding_model, mbti_vector, chroma_client, review_col_name, menu_col_name, allow_cafe=True):
        # print("RecommendPlace 초기화 시작")
        self.model = model.eval()
        # print("모델 구조:", self.model)
        self.allow_cafe = allow_cafe

        self.embedding_model = embedding_model
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # print("디바이스:", self.device)

        self.review_collection = chroma_client.get_or_create_collection(name=review_col_name)
        self.menu_collection = chroma_client.get_or_create_collection(name=menu_col_name)
        # print("컬렉션 불러오기 완료")

        mbti_keywords = ExtractMBTIKeywords().extract(mbti_vector)
        # print("추출된 MBTI 키워드:", mbti_keywords)

        if not mbti_keywords:
            # print("MBTI 키워드가 비어있습니다.")
            self.user_vibe = torch.zeros((1, 768)).numpy()
            return

        keyword_embs = [embedding_model.encode(k, convert_to_tensor=True) for k in mbti_keywords]
        # print("키워드 임베딩 완료. 개수:", len(keyword_embs))

        mbti_tensor = F.normalize(torch.stack(keyword_embs).mean(dim=0, keepdim=True), dim=1).to(self.device)
        # print("평균 벡터 shape:", mbti_tensor.shape)

        with torch.no_grad():
            projected = self.model(mbti_tensor)
            self.user_vibe = F.normalize(projected, dim=1).cpu().numpy()
        # print("사용자 벡터 생성 완료. shape:", self.user_vibe.shape)

    def recommend(self, lat, lng, radius_km=15.0, top_k=5, like_foods=[], dislike_foods=[]):
        # print("추천 시작")
        food_embs = []
        for food in like_foods:
            # print("좋아하는 음식:", food)
            food_embs.append(1.5 * self.embedding_model.encode(food, convert_to_tensor=True))
        for food in dislike_foods:
            # print("싫어하는 음식:", food)
            food_embs.append(-1.5 * self.embedding_model.encode(food, convert_to_tensor=True))

        if food_embs:
            food_tensor = F.normalize(torch.stack(food_embs).mean(dim=0, keepdim=True), dim=1).to(self.device)
            user_pref_vector = F.normalize(
                torch.tensor(self.user_vibe, device=self.device) + food_tensor, dim=1
            ).cpu().numpy()
        else:
            user_pref_vector = self.user_vibe
        # print("최종 사용자 벡터 shape:", user_pref_vector.shape)

        # 더 많은 후보군 확보
        top_k_each = 300 * (2 if self.allow_cafe else 1)

        # print("🔍 리뷰 컬렉션에서 유사도 검색 중...")
        review_results = self.review_collection.query(
            query_embeddings=user_pref_vector,
            n_results=top_k_each,
            include=["metadatas", "distances", "documents"]
        )
        # print("✅ 리뷰 검색 결과 개수:", len(review_results.get("metadatas", [[]])[0]))

        # print("🔍 메뉴 컬렉션에서 유사도 검색 중...")
        menu_results = self.menu_collection.query(
            query_embeddings=user_pref_vector,
            n_results=top_k_each,
            include=["metadatas", "distances", "documents"]
        )
        # print("✅ 메뉴 검색 결과 개수:", len(menu_results.get("metadatas", [[]])[0]))

        # 후보 통합 및 점수 계산
        scored = {}

        def process_results(results, weight, tag, Flag):
            for metadata, distance in zip(results.get("metadatas", [[]])[0], results.get("distances", [[]])[0]):
                store_id = metadata.get("상호명", "")
                rating = float(metadata.get("평균별점", 0))
                lat_p, lng_p = metadata.get("위도"), metadata.get("경도")

                if Flag:  # allow_cafe=True
                    if metadata.get("대표카테고리", "") not in ["카페/디저트"]:
                        continue
                else:
                    if metadata.get("대표카테고리", "") in ["카페/디저트"]:
                        continue 


                if lat_p is None or lng_p is None:
                    print(f"⚠️ 위치 정보 없음 → {store_id}")
                    continue

                dist = haversine(lat, lng, lat_p, lng_p)
                # if dist > radius_km:
                #     continue

                sim_score = 1 - distance
                score = CalculateScore(rating, dist, sim_score, radius_km).calculate() * weight

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
                    "category": metadata.get("대표카테고리", "미분류")
                    # "operation_hours": {
                    #     "월": metadata.get("월", "정보 없음"),
                    #     "화": metadata.get("화", "정보 없음"),
                    #     "수": metadata.get("수", "정보 없음"),
                    #     "목": metadata.get("목", "정보 없음"),
                    #     "금": metadata.get("금", "정보 없음"),
                    #     "토": metadata.get("토", "정보 없음"),
                    #     "일": metadata.get("일", "정보 없음")
                    }

        process_results(review_results, 0.4, "리뷰", self.allow_cafe)
        process_results(menu_results, 0.6, "메뉴", self.allow_cafe)

        # 상위 top_k만 반환
        result = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        print("최종 추천 개수:", len(result))
        return result