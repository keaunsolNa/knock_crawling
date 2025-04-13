import requests
import xmltodict
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

load_all_categories_into_cache("PERFORMING_ARTS")

class KOPISCrawler(AbstractCrawlingService):

    def get_crawling_data(self) -> List[dict]:
        url = self.config["url"]
        params = self.config.get("params", {})
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = xmltodict.parse(response.text)
        return data.get("dbs", {}).get("db", [])

    def get_detail_data(self, mt20id: str) -> dict:
        detail_url = self.config.get("url")
        params = {
            "service": self.config["params"]["service"]
        }
        try:
            response = requests.get(f"{detail_url}/{mt20id}", params=params)
            response.raise_for_status()
            return xmltodict.parse(response.text).get("db", {})
        except Exception as e:
            logger.warning(f"[KOPIS] Detail fetch failed for {mt20id}: {e}")
            return {}

    def create_dto(self, item: dict) -> dict:

        mt20id = item.get("mt20id", "")
        detail = self.get_detail_data(mt20id)

        relates = []
        relate_data = detail.get("relate")
        if isinstance(relate_data, list):
            for r in relate_data:
                name = r.get("relatenm")
                url = r.get("relateurl")
                if name and url:
                    relates.append(f"{name} : {url}")
        elif isinstance(relate_data, dict):
            name = relate_data.get("relatenm")
            url = relate_data.get("relateurl")
            if name and url:
                relates.append(f"{name} : {url}")

        styurls = []
        styurl = detail.get("styurl")
        if isinstance(styurl, list):
            styurls = styurl
        elif isinstance(styurl, str):
            styurls = [styurl]

        runtime_str = detail.get("prfruntime", "")
        runtime = 0
        if "시간" in runtime_str or "분" in runtime_str:
            h = m = 0
            if "시간" in runtime_str:
                h = int(runtime_str.split("시간")[0].strip())
            if "분" in runtime_str:
                m = int(runtime_str.split("분")[0].split("시간")[-1].strip())
            runtime = h * 60 + m

        start_date_str = item.get("prfpdfrom", "")
        end_date_str = item.get("prfpdto", "")

        start_date = converter.string_to_epoch(start_date_str) if start_date_str else 0
        end_date = converter.string_to_epoch(end_date_str) if end_date_str else 0

        genre = item.get("genrenm", "기타").upper()
        category = fetch_or_create_category(genre, "PERFORMING_ARTS")

        return {
            "code": item.get("mt20id"),
            "name": item.get("prfnm"),
            "from": start_date,
            "to": end_date,
            "directors": item.get("prfcrew", "").split(",") if item.get("prfcrew") else [],
            "actors": item.get("prfcast", "").split(",") if item.get("prfcast") else [],
            "companyNm": [item.get("entrpsnm")] if item.get("entrpsnm") else [],
            "holeNm": item.get("fcltynm"),
            "poster": item.get("poster"),
            "story": item.get("sty"),
            "styurls": styurls,
            "area": item.get("area"),
            "prfState": item.get("prfstate"),
            "dtguidance": item.get("dtguidance", "").split(",") if item.get("dtguidance") else [],
            "relates": relates,
            "runningTime": runtime,
            "categoryLevelOne": "PERFORMING_ARTS",
            "categoryLevelTwo": category,
        }

    def crawl(self) -> List[dict]:
        results = []
        page = 1
        while True:
            self.config["params"]["cpage"] = str(page)
            raw_data = self.get_crawling_data()
            if not raw_data:
                break
            results.extend([self.create_dto(item) for item in raw_data])
            if len(raw_data) < int(self.config["params"].get("rows", 100)):
                break
            page += 1
        logger.info(f"[KOPIS] Crawled total {len(results)} items across {page} pages")
        return results