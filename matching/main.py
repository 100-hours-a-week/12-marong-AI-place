from db import SessionLocal
from db_models import Users, Manittos
from manitto_matcher import ManittoMatcher
from get_week_index import GetWeekIndex
from datetime import datetime
from collections import defaultdict
import json

# 날짜 기준 주차 계산
base_date = datetime(2025, 1, 6)
today = datetime.today()
current_week = GetWeekIndex(today, base_date).get()

# group_id 고정 값 (예: 1)
GROUP_ID = 1

# DB 세션 열기
session = SessionLocal()

# 모든 유저 ID 가져오기
user_ids = [user.id for user in session.query(Users.id).all()]

# 과거 매칭 정보 가져오기
previous_matches = {}
matches = session.query(Manittos.manittee_id, Manittos.manitto_id, Manittos.week).all()
for manittee, manitto, week in matches:
    key = frozenset([manittee, manitto])
    if key not in previous_matches or week > previous_matches[key]:
        previous_matches[key] = week

# 매칭 수행
matcher = ManittoMatcher(user_ids, previous_matches, current_week)
pairs, excluded = matcher.assign_weighted_pairs()

# 결과 저장 및 출력
result = []

for u1, u2 in pairs:
    result.append({
        "week": current_week,
        "user_id": u1,
        "manitto_id": u2
    })

    # Manittos 테이블에 저장
    session.add(Manittos(
        group_id=GROUP_ID,
        manittee_id=u1,
        manitto_id=u2,
        week=current_week
    ))

if excluded:
    result.append({
        "week": current_week,
        "user_id": excluded,
        "manitto_id": None
    })

# DB에 커밋
session.commit()
session.close()

# JSON 출력
print(json.dumps(result, indent=2, ensure_ascii=False))