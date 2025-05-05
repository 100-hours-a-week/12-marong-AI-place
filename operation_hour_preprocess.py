# 전처리 코드 전체 모음

import pandas as pd
import ast
import re

# 파일 불러오기
df1 = pd.read_csv('/mnt/data/crawl_result_13.csv')
df2 = pd.read_csv('/mnt/data/crawl_result_11.csv')

# 데이터프레임 통합
merged_df = pd.concat([df1, df2], ignore_index=True)

# 상호명에서 '장소명' 접두어 제거
merged_df['상호명'] = merged_df['상호명'].str.replace(r'^\s*장소명', '', regex=True).str.strip()

# 주소에서 '(우)우편번호' 제거
merged_df['주소'] = merged_df['주소'].str.replace(r'\s*\(우\)\d+', '', regex=True).str.strip()

# 운영시간 문자열을 리스트로 복구
def safe_eval(x):
    try:
        return ast.literal_eval(x)
    except:
        return []

merged_df['운영시간_리스트'] = merged_df['운영시간'].apply(safe_eval)

# 요일 리스트
days_order = ['금', '토', '일', '월', '화', '수', '목']

# 시간 포맷 정리 함수
def clean_time_format(time_str):
    time_str = time_str.replace(' ', '')
    time_str = time_str.replace('~', '~')
    return time_str

# 시간대 여부 판단 함수
def is_time_format(s):
    return bool(re.search(r'\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}', s))

# 운영시간을 요일별로 분배하는 함수 (수정 버전)
def assign_operation_hours_fixed(row):
    operation_list = row['운영시간_리스트']
    if not operation_list:
        return {day: None for day in days_order}

    temp_result = {day: None for day in days_order}
    everyday_items = [item for item in operation_list if '매일' in item]
    if everyday_items:
        everyday_time = everyday_items[0].split('매일')[-1].strip()
        everyday_time = clean_time_format(everyday_time)
        for day in days_order:
            temp_result[day] = everyday_time
        return temp_result

    day_idx = 0
    for item in operation_list:
        if '라스트오더' in item or '브레이크타임' in item:
            continue
        if not is_time_format(item):
            day_idx += 1
            continue
        temp_result[days_order[day_idx % 7]] = clean_time_format(item)
        day_idx += 1

    return temp_result

# 요일별 컬럼 생성 및 채우기
operation_info_fixed = merged_df.apply(assign_operation_hours_fixed, axis=1)
for day in days_order:
    merged_df[day] = operation_info_fixed.apply(lambda x: x[day])

# 최종 CSV 저장
merged_df.to_csv('/mnt/data/merged_operation_time_fixed.csv', index=False)