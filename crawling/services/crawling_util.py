from datetime import timezone, timedelta, datetime

import requests
import ssl
import logging
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from urllib3 import PoolManager
from requests.adapters import HTTPAdapter

from crawling.base.webdriver_config import create_driver
from infra.es_utils import exists_movie_by_kofic_code, exists_movie_by_nm

logger = logging.getLogger(__name__)

## 셀레니움 연결을 위한 SSLAdapter
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")  # 핵심
        self.poolmanager = PoolManager(*args, ssl_context=ctx, **kwargs)

## 셀레니움을 이용한 Detail 주소 접속 
def get_detail_data(url: str) -> BeautifulSoup | None:
    try:
        session = requests.Session()
        session.mount("https://", SSLAdapter())

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = session.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    except Exception as e:
        logger.warning(f"[HTML_UTILS] 상세 페이지 요청 실패: {e}")
        return None

## 접속된 주소의 정보 요청 및 반환
def get_detail_data_with_selenium(url: str, timeout: int = 10) -> BeautifulSoup:
    driver = create_driver()
    try:
        driver.get(url)

        # 실제 내용을 담고 있는 React 컨테이너가 로딩될 때까지 대기
        WebDriverWait(driver, timeout).until(
            expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "div.movi_tab_info1"))  # 또는 "ul.detail_info2"
        )

        # 동적으로 로딩된 div의 innerHTML 가져오기
        content_element = driver.find_element(By.CSS_SELECTOR, "div.movi_tab_info1")
        inner_html = content_element.get_attribute("innerHTML")
        return BeautifulSoup(inner_html, "html.parser")
    except Exception as e:
        logger.warning(f"[LOTTE] 상세 페이지 로딩 실패: {e}")
        return None
    finally:
        driver.quit()

## KST 기준 현재 시간 epochmills 반환
def get_kst_epoch_millis() -> int:
    kst = timezone(timedelta(hours=9))  # UTC+9
    now_kst = datetime.now(kst)
    return int(now_kst.timestamp() * 1000)

## DTO 만들어 반환
def make_dto(title: str,
             opening_time: int,
             poster: str,
             reservation_link: list,
             directors: list,
             actors: list,
             category_level_two: list,
             plot: str,
             running_time: int,
             kofic_index: dict = None) -> dict:

    epoch_millis = get_kst_epoch_millis()
    is_delete    = opening_time < epoch_millis

    if kofic_index:
        kofic_category = kofic_index.get("categoryLevelTwo", category_level_two)
        kofic_categories = (
            [c for c in kofic_category if c] if isinstance(kofic_category, list)
            else [kofic_category] if kofic_category else []
        )

        is_update = exists_movie_by_kofic_code(kofic_index.get("KOFICCode"))
        return {
            "movieNm": kofic_index.get("movieNm", title),
            "openingTime": kofic_index.get("openingTime", opening_time),
            "KOFICCode": kofic_index.get("KOFICCode"),
            "reservationLink": reservation_link,
            "posterBase64": poster,
            "directors": kofic_index.get("directors", []),
            "actors": kofic_index.get("actors", []),
            "companyNm": kofic_index.get("companyNm", []),
            "categoryLevelOne": "MOVIE",
            "categoryLevelTwo": kofic_categories,
            "runningTime": kofic_index.get("runningTime", running_time),
            "plot": plot or "정보없음",
            "favorites": [],
            "__update__": is_update,
            "__delete__": is_delete
        }
    else:
        is_update = exists_movie_by_nm(title)
        if is_update:
            return {
                "movieNm": title,
                "openingTime": opening_time,
                "KOFICCode": "",
                "reservationLink": reservation_link,
                "posterBase64": poster,
                "directors" : directors,
                "actors" : actors,
                "companyNm" : [],
                "categoryLevelOne": "MOVIE",
                "categoryLevelTwo": category_level_two,
                "runningTime" : running_time,
                "plot": plot if plot else "정보없음",
                "favorites" : [],
                "__update__": is_update,
                "__delete__": is_delete
            }
        else:
            return {
                "movieNm": title,
                "openingTime": opening_time,
                "KOFICCode": "",
                "reservationLink": reservation_link,
                "posterBase64": poster,
                "directors" : directors,
                "actors" : actors,
                "companyNm" : [],
                "categoryLevelOne": "MOVIE",
                "categoryLevelTwo": category_level_two,
                "runningTime" : running_time,
                "plot": plot if plot else "정보없음",
                "favorites" : [],
                "__update__": is_update,
                "__delete__": is_delete
            }
        
