from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import time

class MyWebCrawler:
    def __init__(self, my_url):
        self.my_url = my_url
        options = Options()
        options.add_argument("--headless")  # 창 안 뜨게
        options.add_argument("--disable-gpu")  # GPU 가속 끄기 (일부 환경에 필요)
        options.add_argument("--no-sandbox")   # 리눅스에서 충돌 방지용
        options.add_argument("--window-size=1920,1080")  
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        self.info = dict()

    def collect_place_info(self):
        self.driver.get(self.my_url)
        time.sleep(2)
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
    
        # 기본 정보 추출
        place_name_tag = soup.select_one("h3.tit_place")
        place_name = place_name_tag.text.strip() if place_name_tag else "장소명 없음"
        detail_tags = soup.select("span.txt_detail")
        details = [tag.text.strip() for tag in detail_tags]

        if place_name.startswith("장소명:"):
          place_name = place_name.replace("장소명:", "").strip()
        self.info["상호명"] = place_name
        self.info["주소"] = details[0] if len(details) > 0 else ""
        self.info["역 정보"] = details[1] if len(details) > 1 else ""
        self.info["도보 거리"] = details[2] if len(details) > 2 else ""
        self.info["전화번호"] = details[-1] if details else ""

        def parse_opening_hours(driver):
            day_time_dict = {}
        
            alias_map = {
                "매일": ["월", "화", "수", "목", "금", "토", "일"],
                "평일": ["월", "화", "수", "목", "금"],
                "주말": ["토", "일"],
            }
        
            time_blocks = driver.find_elements(By.CSS_SELECTOR, 'div.line_fold')
            for block in time_blocks:
                try:
                    text = block.text.strip()
                    if not text:
                        continue
        
                    # 예: "매일 11:00 ~ 22:00"
                    if any(key in text for key in alias_map.keys()):
                        for key, days in alias_map.items():
                            if key in text:
                                time_text = text.replace(key, '').strip()
                                for day in days:
                                    day_time_dict[day] = time_text
                    else:
                        # 예: "월 11:00 ~ 22:00"
                        day_el = block.find_element(By.CSS_SELECTOR, 'span.tit_fold')
                        time_el = block.find_element(By.CSS_SELECTOR, 'span.txt_detail')
        
                        day = day_el.text.strip()
                        time_text = time_el.text.strip()
                        day_time_dict[day] = time_text
        
                except:
                    continue

            return day_time_dict


        try:
            button = self.driver.find_element(By.CSS_SELECTOR, 'button[aria-controls="foldDetail2"]')
            self.driver.execute_script("arguments[0].click();", button)
            time.sleep(0.5)
        except NoSuchElementException:
            pass
        time.sleep(0.5)

        # 요일별 영업시간 파싱
        try:
            self.info["요일별_영업시간"] = parse_opening_hours(self.driver)
        except Exception as e:
            self.info["요일별_영업시간"] = {}
            logger.warning(f"요일별 영업시간 파싱 실패: {e}")

        # time_rows = soup.select("div.line_fold")
        # for row in time_rows:
        #     day_tag = row.select_one("span.tit_fold")
        #     time_tag = row.select_one("div.detail_fold")
        #     if day_tag and time_tag:
        #         label = day_tag.text.strip()
        #         value = time_tag.text.strip()
        #         # 브레이크타임 따로 저장
        #         if "브레이크타임" in label or "브레이크타임" in value:
        #             self.info["브레이크타임"].append(f"{value}")
        #         else:
        #             self.info["운영시간"].append(f"{label} {value}")

    def collect_menu_info(self):
        self.driver.get(self.my_url + "#menuInfo")
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "strong.tit_item"))
            )
        except:
            self.info["메뉴"] = []
            return

        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        menu_tags = soup.select("strong.tit_item")
        menus = [tag.text.strip() for tag in menu_tags]
        self.info["메뉴"] = menus

    def collect_reviews(self):
        self.driver.get(self.my_url + "#comment")
        time.sleep(1.5)

        prev_height = self.driver.execute_script("return document.body.scrollHeight")

        for i in range(30):  # 30번 정도 시도 (필요에 따라 조정)
            # 스크롤을 최하단으로 내림
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            time.sleep(1.5)  # 데이터 로딩 대기
            
            # 새로운 높이 계산
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            
            if new_height == prev_height:
                break
            
            prev_height = new_height
        
        # 스크롤 완료 후 HTML 가져오기
        html = self.driver.page_source

        soup = BeautifulSoup(html, 'html.parser')
        reviews = soup.select('li.inner_review, li')  # 보통 'li.inner_review'로 충분하지만 fallback용으로 'li'도 포함
        review_dict = {}
        cnt = 1
        
        for idx, review in enumerate(reviews, 1):  # 1부터 시작
            # 리뷰 내용
            text_tag = review.select_one('p.desc_review')
            text = text_tag.text.strip() if text_tag else "리뷰 없음"
        
            # 별점: figure_star on의 개수를 세서 별점으로
            star = len(review.select('span.figure_star.on'))
        
            # 날짜
            date_tag = review.select_one('span.txt_date')
            date = date_tag.text.strip() if date_tag else "날짜 없음"
        
            # 저장
            if star != 0 or text != "리뷰 없음" or date != "날짜 없음":
                review_dict[f"리뷰 {cnt}"] = {
                    "별점": star,
                    "리뷰 내용": text,
                    "날짜": date
                }
                cnt += 1

        self.info["리뷰"] = review_dict

    def quit_driver(self):
        self.driver.quit()