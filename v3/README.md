# Marong AI 장소 추천 (Marong AI Place Recommendation)

마롱(Marong)은 마니또 기반 SNS 서비스의 장소 추천 기능을 담당하는 AI 시스템이며,  
이 저장소는 사용자와 마니또의 MBTI 점수 및 위치 정보를 활용한 음식점·카페 추천기를 구현한 프로젝트입니다.

![Marong Logo](https://github.com/user-attachments/assets/60d19105-80c5-49e5-9c60-0b8400b0db35)

---

## 주요 기능

- **MBTI 기반 추천**  
  사용자와 마니또의 MBTI 점수를 평균내어 성향을 분석하고, 이에 맞는 장소를 추천합니다.
- **선호/비선호 음식 필터**  
  `likedFoods`와 `dislikedFoods`를 반영해 추천 결과를 조정합니다.
- **엔트로피 가중치 동적 조절**  
  각 특성의 정보량(엔트로피)을 계산하여, 정보량이 큰 특성에 더 높은 가중치를 부여합니다.
- **위치 기반 스코어링**  
  사용자·마니또의 위도·경도 정보를 활용해 거리를 계산하고, 거리 점수를 반영합니다.
- **결과 저장**  
  추천 결과를 `PlaceRecommendationSessions`, `PlaceRecommendations` 테이블에 자동 저장합니다.
- **사용자 피드백 루프 반영**  
  사용자의 장소 평가(좋아요/싫어요)를 기반으로 가중치 및 선호 벡터를 동적으로 업데이트합니다.  
  (`preference_update.py` 모듈 기반으로 DB 및 Chroma 벡터 갱신 수행)

---

## 아키텍처 개요

```
[사용자 입력: MBTI, 선호음식, 위도/경도]
               ↓
     MBTI → 벡터 변환 (mbti_projector.py)
               ↓
      점수 계산 (recommend_place.py)
   • 거리
   • 평점
   • MBTI 유사도
   • 엔트로피 가중치
               ↓
    ThreadPoolExecutor 기반 멀티스레딩 처리 (main_tool.py)
               ↓
     추천 결과 DB 저장
               ↓
  장소 피드백 기반 preference_update.py 실행 시,
  사용자의 선호 벡터 및 Chroma 벡터 갱신
```

---

## 설치 방법

```bash
git clone https://github.com/100-hours-a-week/12-marong-AI-place.git
cd 12-marong-AI-place

pip install -r requirements.txt
python scripts/sbert_down.py
```

---

## 사용 예시

```bash
# ChromaDB 실행
python scripts/run_chroma.py

# 프로세스 확인 및 종료 (필요시)
ps aux | grep chroma
kill [포트번호]

# 추천 실행
python main.py
```

---

## 디렉토리 구조

```
12-marong-AI-place/
├── main.py
├── preference_update.py          # 사용자 피드백 기반 선호도 갱신 모듈
├── requirements.txt
├── .env                          # 환경변수 (gitignore)
│
├── core/                         # 추천 알고리즘 로직
│   ├── recommend_place.py        # 추천 시스템 핵심 클래스
│   ├── recommend_tool.py         # 추천 시스템 관련 Backend DB, ChromaDB 조회 및 모든 사용자에 대한 추천 실행
│   ├── calculate_score.py        # 점수 계산 (거리, 평점, 유사도, 엔트로피)
│   ├── average_latlng.py         # 평균 위치 계산
│   ├── get_week_index.py         # 주차 계산 (주간 트렌드 반영 시 사용)
│   └── haversine.py              # 위경도 거리 계산
│
├── models/                       # MBTI 벡터 변환 및 키워드 추출
│   ├── mbti_projector.py         # MBTI → 벡터 변환기
│   ├── extract_mbti_keywords.py  # 키워드 임베딩 추출
│   └── best_mbti_projector.pt    # 학습된 MBTI 변환 모델
│
├── db/                           # DB 연결 및 ORM 정의
│   ├── db.py                     # SQLAlchemy 세션 유틸
│   ├── db_models.py              # 테이블 정의
│   └── preference_update.py      # 사용자 피드백 기반 선호도 갱신
│
├── scripts/                      # 실행 전용 스크립트
│   ├── run_chroma.py             # ChromaDB 실행 스크립트
│   └── sbert_down.py             # SBERT 모델 다운로드 스크립트
│
└── README.md
```

---

## 핵심 모듈 설명

| 모듈                     | 설명                                          |
| ------------------------ | --------------------------------------------- |
| `RecommendPlace`         | 전체 추천 파이프라인을 관리하는 핵심 클래스   |
| `recommend_tool`         | 추천 시스템 관련 DB 조회 및 사용자 추천 실행  |
| `preference_update.py`   | 사용자 피드백 기반 선호도 갱신 모듈           |
| `calculate_score.py`     | 거리·평점·MBTI 유사도·엔트로피 기반 점수 계산 |
| `mbti_projector.py`      | MBTI 점수를 벡터로 변환                       |
| `haversine.py`           | 위경도 기반 거리 계산                         |
| `preference_update.py`   | 사용자 피드백 기반 Chroma 및 DB 벡터 갱신     |
| `average_latlng.py`      | 여러 위치의 평균 위경도 계산                  |
| `db.db` & `db_models.py` | 추천 세션 및 결과 저장을 위한 ORM 정의        |

---

## 추천 규칙

1. MBTI 벡터 평균 기반 유사도 상위 순 정렬
2. 평점이 높은 장소 우선 고려
3. 선호 음식 필터링, 비선호 음식 제외
4. 거리 점수(가까운 순) 반영
5. 엔트로피 가중치로 특성별 중요도 보정
6. 멀티스레딩으로 동시 처리 후 최종 스코어 계산
7. 사용자 피드백 기반 `preference_update.py`로 벡터 및 선호도 갱신

---

## 출력 예시

```json
{
  "index": 1,
  "user_id_pair": ["user_001", "manitto_001"],
  "message": "recommend_success",
  "food_data": [
    {
      "name": "비눔",
      "address": "경기 성남시 분당구 대왕판교로 660 지하1층 B106",
      "rating": 5.0,
      "distance": 0.76,
      "link": "https://place.map.kakao.com/224825790",
      "score": 0.68,
      "category": "양식",
      "operation_hour": ["월~금: 11:00~24:00", "토: 18:00~24:00"]
    }
  ],
  "cafe_data": [
    {
      "name": "마키아티 판교점",
      "address": "경기 성남시 분당구 대왕판교로 660 A동 1층 129호",
      "rating": 5.0,
      "distance": 0.07,
      "link": "https://place.map.kakao.com/1313606369",
      "score": 0.97,
      "category": "카페/디저트",
      "operation_hour": ["월~금: 08:00~17:00"]
    }
  ]
}
```
