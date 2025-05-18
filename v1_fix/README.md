# 12-marong-AI-place

![435163003-08e222cf-4552-45f6-bb5d-818e7df50890](https://github.com/user-attachments/assets/94d48140-82c6-49bb-90ee-f52801000cf4)

## 프로젝트 개요

**12-marong-AI-place**는 사용자와 마니또의 MBTI 점수와 위치 정보를 기반으로 음식점과 카페를 추천해주는 AI 기반 추천 시스템입니다.

## 주요 기능

- **MBTI 기반 추천**: 사용자와 마니또의 MBTI 점수를 평균내어 성향을 분석하고, 이에 맞는 장소를 추천합니다.
- **선호/비선호 음식 고려**: 사용자의 선호 음식과 비선호 음식을 반영하여 추천 결과를 조정합니다.
- **엔트로피 기반 추천 가중치 동적 조절**: MVP 모델 단계에서는 각 특성의 정보량(엔트로피)을 분석하여, 분포가 다양한(정보량이 큰) 특성에 더 높은 가중치를 부여함으로써 보다 정교하고 개인화된 추천을 제공합니다.
- **위치 기반 고려**: 사용자와 마니또의 위도와 경도를 활용하여 추천 결과를 조정합니다.
- **식당/카페 추천**: 사용자와 마니또에게 추천 점수가 높은 맞춤 식당과 카페를 추천합니다.
- **비동기 + 멀티스레딩 최적화 구조**: 식당/카페 추천을 `asyncio`와 `ThreadPoolExecutor`를 활용해 동시에 실행함으로써 프로그램 속도를 최적화하였습니다.

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
python sbert_down.py
python run_chroma.py
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
  "me_lng": 126.978,
  "manitto_lat": 37.5651,
  "manitto_lng": 126.9895
}
```

**Response:**

```json
{
  "index": 1,
  "user_id_pair": ["user_001", "manitto_001"],
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

## 추천 모델 고도화 방안 (Recommendation Model Improvement)

기존 추천 시스템의 정확성과 개인화를 강화하기 위해 다음과 같은 방식을 단계적으로 적용할 예정입니다.

### 1. 사용자 선호 데이터 반영 강화

**목적**  
현재 MBTI 중심의 추천 방식에 더해, 실제 사용자와 마니또의 장소 선호 데이터(좋아하는 음식, 방문 기록, 클릭 이력 등)를 반영하여 추천의 정확도를 향상합니다.

**적용 방안**

- 설문조사 데이터(`likedFoods`, `dislikedFoods`) 외에도 사용자 행동 데이터(방문, 클릭, 저장 등)를 수집하여 벡터화합니다.
- 사용자 피드백(리뷰 평점, 재방문 여부 등)을 모델에 반영하여 개인화를 정교화합니다.

### 2. Retrieval 단계 강화 (후보군 탐색)

추천 시스템을 Retrieval (후보군 탐색)과 Ranking (점수 산정)으로 구조화하고, Retrieval 단계에서 다양한 접근법을 병행합니다.

#### 2-1. Nearest Neighbor Search 기반 Retrieval (현재 방식)

- **원리**: 사용자/마니또의 MBTI 및 음식 선호 임베딩을 기반으로 유사 장소를 ChromaDB에서 검색
- **장점**: 빠르고 가벼움
- **한계**: 협업 필터링 부족, Cold-start 대응에 한계

#### 2-2. GNN(Graph Neural Network) 기반 Retrieval (예정)

- **원리**: 사용자-장소 상호작용 데이터를 그래프로 구성 → GNN으로 유사 장소 예측
- **기대 효과**:
  - 협업 필터링 효과로 Cold-start 완화
  - 친구/그룹 등 사회적 관계성 반영 가능

#### 2-3. Sequence Model 기반 Retrieval (예정)

- **원리**: 장소 방문 이력을 시퀀스로 변환 → Transformer/GRU 등으로 다음 방문 장소 예측
- **기대 효과**:
  - 최근 방문 흐름 및 트렌드 반영
  - 시계열 기반 개인화 강화

### 3. Ranking 단계 개선 (점수 산정)

후보군에 대해 최종 점수를 계산하는 Ranking 단계에 아래와 같은 최적화 기법을 적용합니다.

#### 3-1. Bayesian Optimization 기반 가중치 조정

- **원리**: 평점, 거리, 유사도 등의 가중치를 베이지안 최적화를 통해 자동으로 학습 및 조정
- **효과**: 수동 튜닝 없이 정밀한 가중치 학습 가능

#### 3-2. Entropy 기반 가중치 조정 고도화

- **현재**: 다양성 확보를 위해 엔트로피 기반 가중치 사용 중
- **향후**:
  - 사용자 및 마니또의 선호 데이터를 기반으로 엔트로피 계산 정교화
  - 피드백 데이터를 반영한 동적 가중치 조정

### 4. 추천 대상 확장

**목적**  
현재는 음식점/카페에 한정된 추천에서 나아가 취미, 문화, 여행 등 다양한 라이프스타일 카테고리로 확장할 예정입니다.

**적용 방안**

- 문화/여가/쇼핑/여행 등의 장소 데이터를 수집하여 벡터화
- 다양한 개인화 추천 서비스로 확장

### 참고 사례

**Toss의 Multi-Stage Recommendation System**  
Toss는 Retrieval → Ranking → Re-ranking의 다단계 추천 파이프라인을 통해 개인화를 강화하고 있습니다.  
본 시스템도 이 구조를 참고하여 고도화를 진행합니다.

🔗 [Toss 추천 시스템 상세 설명](https://toss.tech/article/toss-shopping-recommendation-system)

## 참고 사항

- 이 프로젝트는 FastAPI를 기반으로 개발되었습니다.
- MBTI 점수는 `eiScore`, `snScore`, `tfScore`, `jpScore`로 구성되며, 각 점수는 0에서 100 사이의 정수입니다.
- 위도(`latitude`)와 경도(`longitude`)는 소수점 형태의 실수로 입력받습니다.
- `likedFoods`와 `dislikedFoods`는 문자열 리스트로 입력받습니다.
- 장소 추천 결과를 데이터베이스의 `PlaceRecommendationSessions`, `PlaceRecommendations` 테이블에 저장합니다.
