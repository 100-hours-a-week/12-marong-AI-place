# 12-marong-AI-place
![435163003-08e222cf-4552-45f6-bb5d-818e7df50890](https://github.com/user-attachments/assets/94d48140-82c6-49bb-90ee-f52801000cf4)

## 프로젝트 개요

**12-marong-AI-place**는 사용자와 마니또의 MBTI 점수와 위치 정보를 기반으로 음식점과 카페를 추천해주는 AI 기반 추천 시스템입니다.

## 주요 기능

- **MBTI 기반 추천**: 사용자와 마니또의 MBTI 점수를 평균내어 성향을 분석하고, 이에 맞는 장소를 추천합니다.
- **엔트로피 기반 추천 가중치 동적 조절**: MVP 모델 단계에서는 각 특성의 정보량(엔트로피)을 분석하여, 분포가 다양한(정보량이 큰) 특성에 더 높은 가중치를 부여함으로써 보다 정교하고 개인화된 추천을 제공합니다.
- **위치 기반 고려**: 사용자와 마니또의 위도와 경도를 활용하여 추천 결과를 조정합니다.
- **선호/비선호 음식 고려**: 사용자의 선호 음식과 비선호 음식을 반영하여 추천 결과를 조정합니다.
- **식당/카페 추천**: 사용자와 마니또에게 추천 점수가 높은 맞춤 식당과 카페를 추천합니다.
- **비동기 + 멀티스레딩 최적화 구조**: 식당/카페 추천을 `asyncio`와 `ThreadPoolExecutor`를 활용해 동시에 실행함으로써 평균 응답 속도 400ms를 구현하였습니다.

## 프로젝트 구조

```
12-marong-AI-place/
├── recommend_place.py          # 추천 시스템 핵심 클래스
├── average_latlng.py           # 두 사용자의 평균 위치 계산
├── calculate_score.py          # 거리, 평점, 유사도 기반 점수 계산
├── extract_mbti_keywords.py    # MBTI 벡터에서 키워드 추출
├── get_week_index.py           # 기준일 대비 주차 계산
├── haversine.py                # 위도/경도 거리 계산
├── main_fin.py                 # FastAPI 비동기 서버 진입점
├── mbti_projector.py           # MBTI 점수 → 벡터 예측 모델
├── db.py                       # DB 연동 유틸리티
├── db_models.py                # SQLAlchemy 모델 정의
└── README.md
```

## 실행 방법

1. **필요한 패키지 설치**:

```bash
pip install -r requirements.txt
```

2. **서버 실행**:

```bash
fastapi dev main.py
```

3. **API 테스트**:

Postman을 통해 API를 테스트할 수 있습니다.

## API 예시

### `POST /recommend/place`

**Request Body:**

```json
{
  "me_id": 1,
  "manitto_id": 2,
  "me_lat": 37.5665,
  "me_lng": 126.9780,
  "manitto_lat": 37.5651,
  "manitto_lng": 126.9895
}
```

**Response:**

```json
{
    "index": 1,
    "user_id_pair": [
        "user_001",
        "manitto_001"
    ],
    "message": "recommend_success",
    "food_data": [
        {
            "name": "비눔",
            "address": "경기 성남시 분당구 대왕판교로 660 유스페이스1 지하1층 B106호",
            "rating": 5.0,
            "distance": 0.7611726549458185,
            "link": "https://place.map.kakao.com/224825790",
            "score": 0.6838664493251585,
            "category": "양식",
            "operation_hour": "['월, 화, 수, 목, 금: 11:00~24:00', '토: 18:00~24:00', '일: 휴무일']"
        }
    ],
    "cafe_data": [
        {
            "name": "마키아티 판교점",
            "address": "경기 성남시 분당구 대왕판교로 660 유스페이스1 A동 1층 129호",
            "rating": 5.0,
            "distance": 0.06639226081065448,
            "link": "https://place.map.kakao.com/1313606369",
            "score": 0.9663520224032158,
            "category": "카페/디저트",
            "operation_hour": "['월, 화, 수, 목, 금: 08:00~17:00', '토, 일: 휴무일']"
        }
    ]
}
```

## 참고 사항

- 이 프로젝트는 FastAPI를 기반으로 개발되었습니다.
- MBTI 점수는 `eiScore`, `snScore`, `tfScore`, `jpScore`로 구성되며, 각 점수는 0에서 100 사이의 정수입니다.
- 위도(`latitude`)와 경도(`longitude`)는 소수점 형태의 실수로 입력받습니다.
- `likedFoods`와 `dislikedFoods`는 문자열 리스트로 입력받습니다.
- 장소 추천 결과를 데이터베이스의 `PlaceRecommendationSessions`, `PlaceRecommendations` 테이블에 저장합니다.
