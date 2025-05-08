from db import SessionLocal
from db_models import Users, Manittos, UserGroups
from manitto_matcher import ManittoMatcher
from get_week_index import GetWeekIndex
from datetime import datetime
import json

# 날짜 기준 주차 계산
base_date = datetime(2025, 1, 6)
today = datetime.today()
current_week = GetWeekIndex(today, base_date).get()

# DB 세션 열기
session = SessionLocal()

# ✅ 모든 user_id → group_id 매핑 가져오기
user_group_map = {
    row.user_id: row.group_id
    for row in session.query(UserGroups.user_id, UserGroups.group_id).all()
}

# ✅ user_id만 따로 추출
user_ids = list(user_group_map.keys())

# 과거 매칭 정보 가져오기
previous_matches = {}
matches = session.query(Manittos.manittee_id, Manittos.manitto_id, Manittos.week).all()
for manittee, manitto, week in matches:
    key = frozenset([manittee, manitto])
    if key not in previous_matches or week > previous_matches[key]:
        previous_matches[key] = week

# 마니또 매칭 수행
matcher = ManittoMatcher(user_ids, previous_matches, current_week)
pairs, excluded = matcher.assign_weighted_pairs()

# 결과 저장
result = []

for u1, u2 in pairs:
    group_id = user_group_map.get(u1)  # ✅ user_id → group_id 자동 추출

    result.append({
        "week": current_week,
        "user_id": u1,
        "manitto_id": u2,
        "group_id": group_id
    })

    session.add(Manittos(
        group_id=group_id,
        manittee_id=u1,
        manitto_id=u2,
        week=current_week
    ))

if excluded:
    group_id = user_group_map.get(excluded)

    result.append({
        "week": current_week,
        "user_id": excluded,
        "manitto_id": None,
        "group_id": group_id
    })

# DB 반영
session.commit()
session.close()

# JSON 출력
print(json.dumps(result, indent=2, ensure_ascii=False))