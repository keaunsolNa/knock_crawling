import requests
import logging
from typing import List
from crawling.base.abstract_crawling_service import AbstractCrawlingService
from method.StringDateConvert import StringDateConvertLongTimeStamp
from infra.elasticsearch_config import get_es_client
from infra.es_utils import load_all_categories_into_cache, fetch_or_create_category

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()

es = get_es_client()

load_all_categories_into_cache("MOVIE")

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
            "runningTime": running_time
        }

    def crawl(self) -> List[dict]:
        results = []
        page = 1
        while True:
            self.config["params"]["curPage"] = str(page)
            raw_data = self.get_crawling_data()
            if not raw_data:
                break
            results.extend([self.create_dto(item) for item in raw_data])
            if len(raw_data) < int(self.config["params"].get("itemPerPage", 100)):
                break
            page += 1
        logger.info(f"[KOFIC] Crawled total {len(results)} items across {page} pages")
        return results
