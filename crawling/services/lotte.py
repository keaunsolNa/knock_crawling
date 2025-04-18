import logging
import re
from datetime import datetime, timedelta
from typing import List

from bs4 import BeautifulSoup, ResultSet, Tag

from crawling.base.abstract_crawling_service import AbstractCrawlingService
from crawling.base.webdriver_config import create_driver, scroll_until_loaded
from crawling.services.crawling_util import get_detail_data_with_selenium, make_dto
from infra.elasticsearch_config import get_es_client
from infra.es_utils import load_all_categories_into_cache, fetch_or_create_category, \
    search_kofic_index_by_title_and_director
from method.StringDateConvert import StringDateConvertLongTimeStamp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()

es = get_es_client()
load_all_categories_into_cache("MOVIE")

def extract_detail_url(element: Tag) -> str:
    detail_anchor = element.select_one("div.over_box a[href*='MovieDetailView']")
    if detail_anchor:
        return detail_anchor.get("href", "")
    return ""

def extract_director_and_actors(soup: BeautifulSoup) -> (List[str], List[str]):
    info_block = soup.select_one("ul.detail_info2")
    if not info_block:
        return [], []

    directors, actors = [], []

    for li in info_block.select("li"):
        label = li.find("em")
        value = li.find("span")

        if not label or not value:
            continue

        label_text = label.get_text(strip=True)

        if "감독" in label_text:
            # 감독은 a 태그 기준
            directors = [a.get_text(strip=True) for a in value.select("a") if a.get_text(strip=True)]
        elif "출연" in label_text:
            if value.select("a"):
                actors = [a.get_text(strip=True) for a in value.select("a") if a.get_text(strip=True)]
            else:
                raw_text = value.get_text(separator=",").strip()
                actors = [a.strip() for a in raw_text.split(",") if a.strip()]

    return directors, actors

def extract_genres(soup: BeautifulSoup) -> List[str]:
    info_block = soup.select_one("ul.detail_info2")
    if not info_block:
        return ["기타"]

    for li in info_block.select("li"):
        label = li.find("em")
        value = li.find("span")

        if not label or not value:
            continue

        if "장르" in label.get_text(strip=True):
            full_text = value.get_text(strip=True)

            # 슬래시(/) 기준으로 국가 등 뒷부분 제거
            genre_text = full_text.split("/")[0].strip()

            # 쉼표로 장르 분할
            genres = [g.strip() for g in genre_text.split(",") if g.strip()]
            return genres if genres else ["기타"]

    return ["기타"]

def extract_runtime(soup: BeautifulSoup) -> int:
    info_block = soup.select_one("ul.detail_info2")
    if not info_block:
        return 0

    for li in info_block.select("li"):
        label = li.find("em")
        value = li.find("span")

        if not label or not value:
            continue

        # 런타임도 장르 라인에 포함되어 있을 수 있으므로 같이 체크
        if "장르" in label.get_text(strip=True):
            text = value.get_text(strip=True)
            match = re.search(r"(\d+)\s*분", text)
            if match:
                return int(match.group(1))

    return 0

def extract_release_date_and_opening_time(element: Tag, converter) -> (str, int):
    d_day_span = element.select_one("span.remain_info")
    if not d_day_span:
        return "", 0

    text = d_day_span.get_text(strip=True)
    match = re.search(r"D-(\d+)", text)
    if not match:
        return "", 0

    days_remaining = int(match.group(1))
    release_date_obj = datetime.today() + timedelta(days=days_remaining)
    release_date_str = release_date_obj.strftime("%Y.%m.%d")
    opening_time = converter.string_to_epoch(release_date_str)

    return release_date_str, opening_time

class LOTTECrawler(AbstractCrawlingService):

    def __init__(self, config):
        super().__init__(config)
        self.driver = create_driver()

    def get_crawling_data(self) -> ResultSet[Tag]:
        try:
            url = self.config["url"]
            self.driver.get(url)
            scroll_until_loaded(self.driver)
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            return soup.select(".screen_add_box")
        finally:
            self.driver.quit()

    def create_dto(self, element: Tag) -> dict:
        try:
            title_tag = element.select_one("div.btm_info strong.tit_info")
            if not title_tag:
                return {}

            #제목
            title = title_tag.text.strip()
            detail_url = extract_detail_url(element)

            detail_soup = get_detail_data_with_selenium(detail_url) if detail_url else None
            # 개봉일
            raw_date = element.select_one("span.remain_info").text.strip() if element.select_one("span.remain_info") else ""
            release_date, opening_time = extract_release_date_and_opening_time(element, converter)
            running_time = extract_runtime(detail_soup) if detail_soup else 0

            # 포스터
            img_tag = element.select_one("img")
            poster = img_tag["src"] if img_tag and img_tag.has_attr("src") else ""

            # 줄거리
            plot = "정보없음"
            if detail_soup:
                plot_tag = detail_soup.find("meta", attrs={"property": "og:description"})
                if plot_tag:
                    plot = plot_tag.get("content", "").strip()

            genres = extract_genres(detail_soup) if detail_soup else ["기타"]
            category_level_two = [
                fetch_or_create_category(genre, "MOVIE") for genre in genres
                if genre
            ]

            # 감독, 배우
            directors, actors = extract_director_and_actors(detail_soup) if detail_soup else ([], [])

            # 🔍 KOFIC 인덱스 조회 (문자열로)
            kofic_index = search_kofic_index_by_title_and_director(title, directors)

            # 예매 링크
            reservation_link = [None, None, None]  # MEGA BOX, CGV, LOTTE
            if detail_url:
                reservation_link[2] = detail_url

            return make_dto(
                title=title,
                opening_time=opening_time,
                poster=poster,
                reservation_link=reservation_link,
                directors=directors,
                actors=actors,
                category_level_two=category_level_two,
                plot=plot,
                running_time=running_time,
                kofic_index=kofic_index
            )

        except Exception as e:
            logger.warning(f"[LOTTE] DTO 생성 실패: {e}")
            return {}

    def crawl(self) -> List[dict]:
        raw = self.get_crawling_data()
        results = [self.create_dto(item) for item in raw]
        logger.info(f"[LOTTE] Crawled {len(results)} items")
        return results