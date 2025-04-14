import logging
import re
from typing import List
from bs4 import BeautifulSoup, ResultSet, Tag
from crawling.base.abstract_crawling_service import AbstractCrawlingService
from method.StringDateConvert import StringDateConvertLongTimeStamp
from infra.elasticsearch_config import get_es_client
from infra.es_utils import load_all_categories_into_cache, fetch_or_create_category, search_kofic_index_by_title_and_director, exists_movie_by_kofic_code
from crawling.base.webdriver_config import create_driver, scroll_until_loaded
from crawling.services.crawling_util import get_detail_data

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()

es = get_es_client()
load_all_categories_into_cache("MOVIE")

def extract_detail_url(element: Tag) -> str:
    onclick = element.select_one("a.btn_reserve").get("onclick", "")
    match = re.search(r"fnQuickReserve\('(\d+)'", onclick)
    if match:
        code = match.group(1)
        return f"https://www.cgv.co.kr/movies/detail-view/?midx={code}"
    logger.warning("[CGV] 예매 코드 추출 실패: %s", onclick)
    return ""

def extract_director_and_actors(soup: BeautifulSoup) -> (List[str], List[str]):
    spec_block = soup.select_one("div.spec")
    if not spec_block:
        return [], []

    directors, actors = [], []
    dl_children = spec_block.select_one("dl").find_all(["dt", "dd"], recursive=False)

    current_label = None
    for tag in dl_children:
        if tag.name == "dt":
            text = tag.get_text(strip=True).replace(" ", "").replace(":", "").replace("/", "")
            current_label = text  # ex: "감독", "배우"
        elif tag.name == "dd" and current_label:
            if "감독" in current_label:
                directors.extend([a.text.strip() for a in tag.select("a") if a.text.strip()])
            elif "배우" in current_label:
                # 배우가 a 태그에 없을 수도 있음 (텍스트 분리)
                if tag.select("a"):
                    actors.extend([a.text.strip() for a in tag.select("a") if a.text.strip()])
                else:
                    raw_text = tag.get_text(separator=",").strip()
                    actors.extend([a.strip() for a in raw_text.split(",") if a.strip()])

    return directors, actors

def extract_genre(soup: BeautifulSoup) -> str:
    spec_block = soup.select_one("div.spec")
    if not spec_block:
        return "기타"

    dt_elements = spec_block.select("dt")

    for dt in dt_elements:
        if "장르" in dt.text:
            genre_text = dt.get_text(strip=True).replace("장르 :", "").strip()
            if genre_text:
                genre = genre_text.split(",")[0].strip()
                return genre

    return "기타"

def extract_runtime(soup: BeautifulSoup) -> int:
    spec_block = soup.select_one("div.spec")
    if not spec_block:
        return 0

    dt_elements = spec_block.select("dt")
    dd_elements = spec_block.select("dd")

    for i, dt in enumerate(dt_elements):
        if "기본 정보" in dt.text:
            dd_text = dd_elements[i].text.strip()
            match = re.search(r"(\d+)\s*분", dd_text)
            if match:
                return int(match.group(1))
    return 0


class CGVCrawler(AbstractCrawlingService):

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
            return soup.select("div.mm_list_item")
        finally:
            self.driver.quit()

    def create_dto(self, element: Tag) -> dict:
        try:
            title_tag = element.select_one("div.tit_area strong.tit")
            if not title_tag:
                return {}

            #제목
            title = title_tag.text.strip()
            detail_url = extract_detail_url(element)

            detail_soup = get_detail_data(detail_url) if detail_url else None

            # 개봉일
            raw_date = element.select_one("span.rel-date").text.strip() if element.select_one("span.rel-date") else ""
            release_date = raw_date.replace("개봉", "").strip()
            opening_time = converter.string_to_epoch(release_date) if release_date else 0
            running_time = extract_runtime(detail_soup) if detail_soup else 0

            # 포스터
            img_tag = element.select_one("span.imgbox img")
            poster = img_tag["src"] if img_tag else ""

            # 줄거리
            plot = "정보없음"
            if detail_soup:
                plot_tag = detail_soup.find("meta", attrs={"property": "og:description"})
                if plot_tag:
                    plot = plot_tag.get("content", "").strip()

            genre = extract_genre(detail_soup) if detail_soup else "기타"
            # 장르 → 카테고리
            category_level_two = fetch_or_create_category(genre, "MOVIE")

            # 감독, 배우
            directors, actors = extract_director_and_actors(detail_soup) if detail_soup else ([], [])

            # 🔍 KOFIC 인덱스 조회 (문자열로)
            kofic_index = search_kofic_index_by_title_and_director(title, directors)

            # 예매 링크
            reservation_link = [None, None, None]  # MEGA BOX, CGV, LOTTE
            if detail_url:
                reservation_link[1] = "https://www.cgv.co.kr/movies/detail-view/?midx=" + detail_url.split("=")[-1]

            if kofic_index:

                kofic_category = kofic_index.get("categoryLevelTwo", category_level_two)
                # 리스트인 경우 첫 번째 항목 사용
                if isinstance(kofic_category, list) and kofic_category:
                    kofic_category = kofic_category[0]

                is_update = exists_movie_by_kofic_code(kofic_index.get("KOFICCode"))
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

            # fallback: CGV-only 정보 기반
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
            logger.warning(f"[CGV] DTO 생성 실패: {e}")
            return {}

    def crawl(self) -> List[dict]:
        raw = self.get_crawling_data()
        results = [self.create_dto(item) for item in raw]
        logger.info(f"[CGV] Crawled {len(results)} items")
        return results