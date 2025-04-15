import logging
import re
from typing import List
from bs4 import BeautifulSoup, ResultSet, Tag

from crawling.base.abstract_crawling_service import AbstractCrawlingService
from method.StringDateConvert import StringDateConvertLongTimeStamp
from infra.elasticsearch_config import get_es_client
from infra.es_utils import load_all_categories_into_cache, fetch_or_create_category, \
    search_kofic_index_by_title_and_director, exists_movie_by_kofic_code, exists_movie_by_nm
from crawling.base.webdriver_config import create_driver, click_until_disappear, get_detail_data_with_selenium

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()

es = get_es_client()
load_all_categories_into_cache("MOVIE")

def extract_detail_url(element: Tag) -> str:
    reservation_element = element.select_one("a.movieBtn")
    if not reservation_element:
        return ""

    link = "https://www.megabox.co.kr/movie-detail?rpstMovieNo=" + reservation_element.get("data-no", "")
    return link

def extract_director_and_actors(soup: BeautifulSoup) -> (List[str], List[str]):

    info_block = soup.select_one("div.movie-info.infoContent")
    if not info_block:
        return [], []

    directors, actors = [], []

    # 1. 감독 추출
    director_p = info_block.find("p", string=re.compile(r"^\s*감독"))
    if director_p:
        text = director_p.get_text(strip=True)
        text = re.sub(r"^감독\s*[:：]?\s*", "", text)
        directors = [d.strip() for d in text.split(",") if d.strip()]

    # 2. 출연진 추출
    actor_p = info_block.find("p", string=re.compile(r"^\s*출연진"))
    if actor_p:
        text = actor_p.get_text(strip=True)
        text = re.sub(r"^출연진\s*[:：]?\s*", "", text)
        actors = [a.strip() for a in text.split(",") if a.strip()]

    return directors, actors

def extract_genre(soup: BeautifulSoup) -> str:
    info_block = soup.select_one("div.movie-info.infoContent")
    if not info_block:
        return "기타"

    genre_p = info_block.find("p", string=lambda text: text and "장르" in text)
    if genre_p:
        text = genre_p.get_text(strip=True)
        parts = text.replace("장르", "").replace(":", "").strip().split("/")
        if parts:
            return parts[0].strip()

    return "기타"

def extract_runtime(soup: BeautifulSoup) -> int:
    info_block = soup.select_one("div.movie-info.infoContent")
    if not info_block:
        return 0

    genre_p = info_block.find("p", string=lambda text: text and "장르" in text)
    if genre_p:
        text = genre_p.get_text(strip=True)
        match = re.search(r"(\d+)\s*분", text)
        if match:
            return int(match.group(1))

    return 0

class MEGABOXCrawler(AbstractCrawlingService):

    def __init__(self, config):
        super().__init__(config)
        self.driver = create_driver()

    def get_crawling_data(self) -> ResultSet[Tag]:
        try:
            url = self.config["url"]
            self.driver.get(url)
            click_until_disappear(self.driver, ".btn-more")
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            return soup.select("ol#movieList li")
        finally:
            self.driver.quit()

    def create_dto(self, element: Tag) -> dict:
        try:
            title_tag = element.select_one("div.tit-area > p.tit")
            if not title_tag:
                return {}

            #제목
            title = title_tag.text.strip()
            detail_url = extract_detail_url(element)

            detail_soup = get_detail_data_with_selenium(detail_url) if detail_url else None

            # 개봉일
            raw_date = element.select_one("div.rate-date > span.date").text.strip() if element.select_one("div.rate-date > span.date") else ""
            release_date = raw_date.replace("개봉일", "").strip()
            opening_time = converter.string_to_epoch(release_date) if release_date else 0
            running_time = extract_runtime(detail_soup) if detail_soup else 0

            # 포스터
            img_tag = element.select_one("img")
            poster = img_tag["src"] if img_tag else ""

            # 줄거리
            plot = "정보없음"
            if detail_soup:
                plot_tag = detail_soup.find("meta", attrs={"property": "og:description"})
                if plot_tag:
                    plot = plot_tag.get("content", "").strip()

            genres = extract_genre(detail_soup) if detail_soup else "기타"
            genre_list = [g.strip() for g in genres.split(",")] if isinstance(genres, str) else []

            category_level_two = [
                fetch_or_create_category(genre, "MOVIE")
                for genre in genre_list
                if genre.strip()
            ]

            logger.info(category_level_two)
            # 감독, 배우
            directors, actors = extract_director_and_actors(detail_soup) if detail_soup else ([], [])

            # 🔍 KOFIC 인덱스 조회 (문자열로)
            kofic_index = search_kofic_index_by_title_and_director(title, directors)

            # 예매 링크
            reservation_link = [None, None, None]  # MEGA BOX, CGV, LOTTE
            if detail_url:
                reservation_link[0] = detail_url

            if kofic_index:

                kofic_category = kofic_index.get("categoryLevelTwo", category_level_two)
                if isinstance(kofic_category, list):
                    kofic_categories = [c for c in kofic_category if c]  # 빈 항목 제거
                elif kofic_category:  # 단일 문자열
                    kofic_categories = [kofic_category]
                else:
                    kofic_categories = []

                is_update = exists_movie_by_kofic_code(kofic_index.get("KOFICCode")) or exists_movie_by_nm(title)
                # KOFIC 기반 정보 덮어쓰기
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
                    "categoryLevelTwo": kofic_category,
                    "runningTime": kofic_index.get("runningTime", 0),
                    "plot": plot if plot else "정보없음",
                    "favorites" : "",
                    "__update__": is_update
                }

            # fallback: MEGABOX-only 정보 기반
            return {
                "movieNm": title,
                "openingTime": opening_time,
                "KOFICCode": "",
                "reservationLink": reservation_link,
                "posterBase64": poster,
                "directors" : directors,
                "actors" : actors,
                "companyNm" : "",
                "categoryLevelOne": "MOVIE",
                "categoryLevelTwo": category_level_two,
                "runningTime" : running_time,
                "plot": plot if plot else "정보없음",
                "favorites" : ""
            }

        except Exception as e:
            logger.warning(f"[MEGABOX] DTO 생성 실패: {e}")
            return {}

    def crawl(self) -> List[dict]:
        raw = self.get_crawling_data()
        results = [self.create_dto(item) for item in raw]
        logger.info(f"[MEGABOX] Crawled {len(results)} items")
        return results