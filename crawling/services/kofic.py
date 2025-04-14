import requests
import logging
from typing import List
from crawling.base.abstract_crawling_service import AbstractCrawlingService
from method.StringDateConvert import StringDateConvertLongTimeStamp
from infra.elasticsearch_config import get_es_client
from infra.es_utils import fetch_or_create_category, exists_kofic_by_kofic_code, load_all_kofic_into_cache, \
    load_all_categories_into_cache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()
es = get_es_client()

load_all_categories_into_cache("MOVIE")
load_all_kofic_into_cache()

global dto
class KOFICCrawler(AbstractCrawlingService):

    def get_crawling_data(self) -> List[dict]:
        url = self.config["url"]
        params = self.config.get("params", {})
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("movieListResult", {}).get("movieList", [])

    def get_detail_data(self, movie_cd: str) -> dict:
        detail_url = self.config.get("url_sub")
        key = self.config["params"].get("key")
        try:
            response = requests.get(detail_url, params={"key": key, "movieCd": movie_cd})
            response.raise_for_status()
            return response.json().get("movieInfoResult", {}).get("movieInfo", {})
        except Exception as e:
            logger.warning(f"[KOFIC] Detail fetch failed for {movie_cd}: {e}")
            return {}

    def create_dto(self, item: dict) -> dict:

        prdt_year_str = item.get("prdtYear", "")
        prdt_year_long = 0 if not prdt_year_str else converter.string_to_epoch(prdt_year_str)
        opening_time_str = item.get("openDt", "")
        opening_time_long = 0  if not opening_time_str else converter.string_to_epoch(opening_time_str)

        directors = [a.get("peopleNm", "") for a in item.get("directors", []) if a.get("peopleNm")]
        companies = [b.get("companyNm", "") for b in item.get("companys", []) if b.get("companyNm")]

        genre_str = item.get("genreAlt", "")
        genre_list = [c.strip() for c in genre_str.split(",") if c.strip()]
        categories = [fetch_or_create_category(genre, "MOVIE") for genre in genre_list if genre]
        categories = [cat for cat in categories if cat]

        detail_data = self.get_detail_data(item.get("movieCd"))
        actors = [d.get("peopleNm", "") for d in detail_data.get("actors", []) if d.get("peopleNm")]

        running_time = 0
        if detail_data:
            try:
                running_time = int(detail_data.get("showTm", "0"))
            except ValueError:
                logger.warning(f"[KOFIC] Invalid showTm for {item.get('movieCd')}")

        return {
            "KOFICCode": item.get("movieCd"),
            "movieNm": item.get("movieNm"),
            "prdtYear": prdt_year_long,
            "openingTime": opening_time_long,
            "directors": directors,
            "actors": actors,
            "companyNm": companies,
            "categoryLevelOne": "MOVIE",
            "categoryLevelTwo": categories,
            "runningTime": running_time,
            "__update__": exists_kofic_by_kofic_code(item.get("movieCd"))
        }

    def crawl(self) -> List[dict]:
        global dto
        results = []
        page = 1
        stop_crawling = False

        while not stop_crawling:
            self.config["params"]["curPage"] = str(page)
            raw_data = self.get_crawling_data()
            if not raw_data:
                break

            for item in raw_data:
                dto = self.create_dto(item)
                if dto.get("__update__"):
                    logger.info(f"[KOFIC] 이미 존재하는 항목 발견: {dto.get('movieNm')}({dto.get('KOFICCode')}). 크롤링 중단.")
                    stop_crawling = True
                    break

            results.append(dto)

            if stop_crawling or len(raw_data) < int(self.config["params"].get("itemPerPage", 100)):
                break

            page += 1
        logger.info(f"[KOFIC] Crawled total {len(results)} items across {page} pages")
        return results
