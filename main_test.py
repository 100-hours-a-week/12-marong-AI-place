from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from sentence_transformers import SentenceTransformer
from recommend_place import RecommendPlace
from mbti_projector import MBTIProjector
from chromadb import HttpClient
from chromadb.config import Settings
from datetime import datetime
from get_week_index import GetWeekIndex
from average_latlng import AverageLatLng
from concurrent.futures import ThreadPoolExecutor
import torch, asyncio, logging

# 로깅 설정
logger = logging.getLogger("uvicorn.error")

# 비동기 실행기
executor = ThreadPoolExecutor()
async def recommend_async(recommender, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        lambda: recommender.recommend(*args, **kwargs)
    )

# 기준일과 오늘 날짜 기반 주차 계산
base_date = datetime(2025, 1, 6)
today = datetime.today()
week_index = GetWeekIndex(today, base_date).get()

# FastAPI 앱 생성
app = FastAPI()

# ✅ 예외 처리: 모델 및 클라이언트 로딩
try:
    mbti_model = MBTIProjector()
    mbti_model.load_state_dict(torch.load("best_mbti_projector.pt", map_location="cpu"))
    mbti_model.eval()

    embedding_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    chroma_client = HttpClient(
        host="localhost",
        port=8001,
        ssl=False
    )
except Exception as e:
    logger.error(f"모델 또는 Chroma 연결 실패: {e}")
    raise RuntimeError(f"초기화 실패: {e}")

# ✅ 요청 스키마
class RecommendInput(BaseModel):
    id: int
    eiScore: int
    snScore: int
    tfScore: int
    jpScore: int
    latitude: float
    longitude: float
    likedFoods: List[str] = []
    dislikedFoods: List[str] = []

class PairInput(BaseModel):
    me: RecommendInput
    manitto: RecommendInput

# ✅ 추천 API
@app.post("/recommend/place")
async def recommend_places(input: PairInput):
    try:
        # 평균 MBTI 벡터 및 위치
        avg_vector = [
            (input.me.eiScore + input.manitto.eiScore) / 2,
            (input.me.snScore + input.manitto.snScore) / 2,
            (input.me.tfScore + input.manitto.tfScore) / 2,
            (input.me.jpScore + input.manitto.jpScore) / 2,
        ]
        average_loc = AverageLatLng(input.me.latitude, input.me.longitude,
                                    input.manitto.latitude, input.manitto.longitude)
        average_loc.loc_to_vec()
        avg_lat, avg_lng = average_loc.get()

        # 선호 음식 통합
        like_foods = list(set(input.me.likedFoods + input.manitto.likedFoods))
        dislike_foods = list(set(input.me.dislikedFoods + input.manitto.dislikedFoods))

        # 추천 객체 생성
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

        # 추천 비동기 실행
        food_task = recommend_async(
            food_recommender,
            lat=avg_lat,
            lng=avg_lng,
            radius_km=10,
            like_foods=like_foods,
            dislike_foods=dislike_foods
        )
        cafe_task = recommend_async(
            cafe_recommender,
            lat=avg_lat,
            lng=avg_lng,
            radius_km=10,
            like_foods=like_foods,
            dislike_foods=dislike_foods
        )

        # ✅ gather 실행 중 오류 처리
        try:
            food_results, cafe_results = await asyncio.gather(food_task, cafe_task)
        except Exception as e:
            logger.error(f"추천 수행 중 오류: {e}")
            raise HTTPException(status_code=500, detail=f"추천 처리 중 오류 발생: {str(e)}")

        return {
            "index": week_index,
            "user_id_pair": [input.me.id, input.manitto.id],
            "message": "recommend_success",
            "food_data": food_results,
            "cafe_data": cafe_results
        }

    except HTTPException as http_e:
        raise http_e

    except Exception as e:
        logger.error(f"서버 오류: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": "서버 내부 오류 발생", "detail": str(e)}
        )