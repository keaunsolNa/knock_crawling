import requests
import xmltodict
import logging
from typing import List
from crawling.base.abstract_crawling_service import AbstractCrawlingService
from method.StringDateConvert import StringDateConvertLongTimeStamp
from infra.elasticsearch_config import get_es_client
from infra.es_utils import load_all_categories_into_cache, fetch_or_create_category, exists_kopis_by_kopis_code, \
    load_all_kopis_into_cache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
converter = StringDateConvertLongTimeStamp()

es = get_es_client()

load_all_categories_into_cache("PERFORMING_ARTS")
load_all_kopis_into_cache()

global dto

def split_comma(s: str | None) -> list[str]:

    if not s or not isinstance(s, str) or None == s or not s.strip():
        return []
    return [item.strip() for item in s.split(",") if item.strip()]

def parse_runtime(runtime_str: str) -> int:
    if not runtime_str or not isinstance(runtime_str, str):
        return 0
    h, m = 0, 0
    if "시간" in runtime_str:
        try:
            h = int(runtime_str.split("시간")[0].strip())
        except:
            h = 0
    if "분" in runtime_str:
        try:
            m = int(runtime_str.split("분")[0].split("시간")[-1].strip())
        except:
            m = 0
    return h * 60 + m

def parse_optional_list(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []

def get_prf_state_enum(korean: str) -> str | None:
    mapping = {
        "공연예정": "UPCOMING",
        "공연중": "ONGOING",
        "공연완료": "COMPLETED",
        "오픈런": "OPEN_RUN",
        "리미티드런": "LIMITED_RUN",
        "마감임박": "CLOSING_SOON",
        "알 수 없음": "UNKNOWN"
    }
    return mapping.get(korean)

class KOPISCrawler(AbstractCrawlingService):

    def get_crawling_data(self) -> List[dict]:
        url = self.config["url"]
        params = self.config.get("params", {})
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = xmltodict.parse(response.text)
            dbs = data.get("dbs", {})

            # 'dbs'가 dict 형태라면 "db" 키를 추출
            if isinstance(dbs, dict):
                db_list = dbs.get("db", [])
                if isinstance(db_list, dict):
                    return [db_list]  # 단일 항목이 dict로 올 수 있음
                elif isinstance(db_list, list):
                    return db_list
                else:
                    logger.warning(f"[KOPIS] Unexpected db format: {type(db_list)}")
                    return []

            logger.warning(f"[KOPIS] Unexpected 'dbs' type: {type(dbs)}")
            return []

        except Exception as e:
            logger.warning(f"[KOPIS] Crawling 실패: {e}")
            return []


    def get_detail_data(self, mt20id: str) -> dict:
        detail_url = self.config.get("url")
        params = {
            "service": self.config["params"]["service"]
        }
        try:
            response = requests.get(f"{detail_url}/{mt20id}", params=params)
            response.raise_for_status()
            data = xmltodict.parse(response.text)
            return data.get("dbs", {}).get("db", {})
        except Exception as e:
            logger.warning(f"[KOPIS] Detail fetch failed for {mt20id}: {e}")
            return {}

    def create_dto(self, item: dict) -> dict:

        mt20id = item.get("mt20id", "")
        detail = self.get_detail_data(mt20id)

        # relates
        relates = []
        relate_data = detail.get("relates", {}).get("relate")
        if isinstance(relate_data, list):
            for r in relate_data:
                name, url = r.get("relatenm"), r.get("relateurl")
                if name and url:
                    relates.append(f"{name} : {url}")
        elif isinstance(relate_data, dict):
            name, url = relate_data.get("relatenm"), relate_data.get("relateurl")
            if name and url:
                relates.append(f"{name} : {url}")

        # styurls
        styurls = []
        styurl_node = detail.get("styurls", {}).get("styurl")
        if isinstance(styurl_node, str):
            styurls.append(styurl_node.strip())
        elif isinstance(styurl_node, list):
            styurls = [url.strip() for url in styurl_node if isinstance(url, str) and url.strip()]


        start_date = converter.string_to_epoch(item.get("prfpdfrom", ""))
        end_date = converter.string_to_epoch(item.get("prfpdto", ""))
        runtime = parse_runtime(detail.get("prfruntime", ""))
        genre = item.get("genrenm", "기타").upper()
        category = fetch_or_create_category(genre, "PERFORMING_ARTS")
        dt_raw = detail.get("dtguidance")
        dtguidance = split_comma(dt_raw) if dt_raw else []

        return {
            "code": mt20id,
            "name": item.get("prfnm"),
            "from": start_date,
            "to": end_date,
            "directors": split_comma(detail.get("prfcrew", "")),
            "actors": split_comma(detail.get("prfcast", "")),
            "companyNm": split_comma(detail.get("entrpsnm", "")),
            "holeNm": item.get("fcltynm"),
            "poster": item.get("poster"),
            "story": detail.get("sty", "").strip() if isinstance(detail.get("sty"), str) else "",
            "styurls": styurls,
            "area": item.get("area"),
            "prfState": get_prf_state_enum(item.get("prfstate")) or "UNKNOWN",
            "dtguidance": dtguidance,
            "relates": relates,
            "runningTime": runtime,
            "categoryLevelOne": "PERFORMING_ARTS",
            "categoryLevelTwo": category,
            "__update__": exists_kopis_by_kopis_code(mt20id)
        }

    def crawl(self) -> List[dict]:
        global dto
        results = []
        page = 1
        stop_crawling = False

        while not stop_crawling:

            self.config["params"]["cpage"] = str(page)
            raw_data = self.get_crawling_data()
            if not raw_data:
                break

            for item in raw_data:
                dto = self.create_dto(item)

                if dto.get("__update__"):
                    logger.info(f"[KOPIS] 이미 존재하는 항목 발견: {dto.get('name')}({dto.get('code')}). 크롤링 중단.")
                    stop_crawling = True
                    break
                results.append(dto)

            page += 1
            if page > 3000:
                break

        logger.info(f"[KOPIS] Crawled total {len(results)} items across {page} pages")
        return results