# 12-marong-AI-place
![435163003-08e222cf-4552-45f6-bb5d-818e7df50890](https://github.com/user-attachments/assets/94d48140-82c6-49bb-90ee-f52801000cf4)

## 프로젝트 개요

**12-marong-AI-place**는 사용자와 마니또의 MBTI 점수와 위치 정보를 기반으로 음식점과 카페를 추천해주는 AI 기반 추천 시스템입니다.

## 주요 기능

- **MBTI 기반 추천**: 사용자와 마니또의 MBTI 점수를 평균내어 성향을 분석하고, 이에 맞는 장소를 추천합니다.
- **엔트로피 기반 추천 가중치 동적 조절**: 각 특성의 정보량(엔트로피)을 분석하여, 분포가 다양한(정보량이 큰) 특성에 더 높은 가중치를 부여함으로써 보다 정교하고 개인화된 추천을 제공합니다.
- **위치 기반 필터링**: 사용자의 위도와 경도를 활용하여 반경 내의 장소를 추천합니다.
- **선호/비선호 음식 고려**: 사용자의 선호 음식과 비선호 음식을 반영하여 추천 결과를 조정합니다.
- **카페 포함 여부 선택**: 카페를 포함한 추천 여부를 선택할 수 있습니다.

## 프로젝트 구조

```
12-marong-AI-place/
├── recommend_place.py
├── average_latlng.py
├── calculate_score.py
├── extract_mbti_keywords.py
├── get_week_index.py
├── haversine.py
├── main.py
├── mbti_projector.py
└── README.md
```

- `recommend_place.py`: 추천 시스템의 핵심 로직을 담고 있습니다.
- `average_latlng.py`: 위도와 경도의 평균을 계산합니다.
- `calculate_score.py`: 추천 점수를 계산하는 로직을 포함합니다.
- `extract_mbti_keywords.py`: MBTI 관련 키워드를 추출합니다.
- `get_week_index.py`: 현재 날짜를 기준으로 회차를 계산합니다.
- `haversine.py`: 두 지점 간의 거리를 계산하는 함수를 제공합니다.
- `main.py`: FastAPI를 활용한 서버 실행 파일입니다.
- `mbti_projector.py`: MBTI 점수를 벡터로 변환하는 기능을 제공합니다.

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
  "me": {
    "id": "user_001",
    "eiScore": 20,
    "snScore": 20,
    "tfScore": 30,
    "jpScore": 80,
    "latitude": 37.394726159,
    "longitude": 127.111209047,
    "likedFoods": ["고기"],
    "dislikedFoods": ["매운 음식"]
  },
  "manitto": {
    "id": "manitto_001",
    "eiScore": 50,
    "snScore": 20,
    "tfScore": 20,
    "jpScore": 70,
    "latitude": 37.394726159,
    "longitude": 127.111209047,
    "likedFoods": ["고기", "피자"],
    "dislikedFoods": ["채소"]
  }
}
```

**Response:**

```json
{
  "index": "1회차",
  "user_id_pair": [
        "user_001",
        "manitto_001"
    ],
  "message": "recommend_success",
  "food_data": [...],
  "cafe_data": [...]
}
```

## 참고 사항

- 이 프로젝트는 FastAPI를 기반으로 개발되었습니다.
- MBTI 점수는 `eiScore`, `snScore`, `tfScore`, `jpScore`로 구성되며, 각 점수는 0에서 100 사이의 정수입니다.
- 위도(`latitude`)와 경도(`longitude`)는 소수점 형태의 실수로 입력받습니다.
- `likedFoods`와 `dislikedFoods`는 문자열 리스트로 입력받습니다.
