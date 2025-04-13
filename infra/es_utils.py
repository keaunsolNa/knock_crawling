import logging
from dotenv import load_dotenv
from elasticsearch import NotFoundError
from elasticsearch.helpers import bulk
from infra.elasticsearch_config import get_es_client
from typing import Dict, Tuple

load_dotenv()
logger = logging.getLogger(__name__)
category_cache: Dict[Tuple[str, str], Dict[str, str]] = {}

def save_to_es(index: str, documents: list, dedup_keys: list = None):

    es = get_es_client()
    actions = []
    for doc in documents:

        is_update = doc.pop("__update__", False)
        kofic_code = doc.get("KOFICCode")
        doc_id = None

        if is_update and kofic_code:

            try:
                # 🧠 기존 문서 조회
                existing_doc = es.get(index=index, kofic_code=kofic_code)["_source"]
                partial_doc = {}

                # 🎯 조건 기반 병합 (자바 로직 반영)
                if doc.get("reservationLink") and any(doc["reservationLink"]):
                    partial_doc["reservationLink"] = doc["reservationLink"]

                if not existing_doc.get("posterBase64") or existing_doc.get("posterBase64", "").strip() == "":
                    if doc.get("posterBase64"):
                        partial_doc["posterBase64"] = doc["posterBase64"]

                plot = existing_doc.get("plot", "")
                if not plot or plot.strip() == "" or plot.strip() == "정보없음":
                    partial_doc["plot"] = doc.get("plot", "정보없음")

                # 업데이트할 게 있을 때만 추가
                if partial_doc:
                    actions.append({
                        "_op_type": "update",
                        "_index": index,
                        "doc": partial_doc,
                        "doc_as_upsert": False
                    })

            except Exception as e:
                logger.warning(f"[ES] 기존 문서 조회 실패: {doc_id}, 예외: {e}")

        else:
            action = {
                "_op_type": "index",
                "_index": index,
                "_source": doc
            }
            actions.append(action)

    success, _ = bulk(es, actions, raise_on_error=False)
    print(f"✅ Elasticsearch 저장 완료: {success}/{len(actions)}")

def load_all_categories_into_cache(parent_nm: str = "MOVIE"):
    es = get_es_client()
    query = {
        "query": {
            "match": {
                "parentNm": parent_nm
            }
        },
        "size": 1000
    }
    try:
        response = es.search(index="category-level-two-index", body=query)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            key = (src["nm"].strip().upper(), src["parentNm"].strip().upper())
            category_cache[key] = src
        logger.info(f"[CACHE] Loaded {len(category_cache)} categories into cache.")
    except Exception as e:
        logger.warning(f"[CACHE] 카테고리 캐싱 실패: {e}")

def fetch_or_create_category(nm: str, parent_nm: str = "MOVIE") -> Dict[str, str]:

    if not nm.strip():
        logger.warning("[CATEGORY] 빈 장르명은 건너뜀")
        return {}

    es = get_es_client()
    key = (nm.strip().upper(), parent_nm.strip().upper())
    if key in category_cache:
        return category_cache[key]

    query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"nm": nm}},
                    {"match": {"parentNm": parent_nm}}
                ]
            }
        }
    }
    try:
        response = es.search(index="category-level-two-index", body=query)
        hits = response.get("hits", {}).get("hits", [])
        if hits:
            category_cache[key] = hits[0]["_source"]
            return hits[0]["_source"]

        # 없으면 새로 생성
        doc = {"nm": nm, "parentNm": parent_nm}
        es.index(index="category-level-two-index", document=doc)
        category_cache[key] = doc
        logger.info(f"[CATEGORY] Created new category: {nm}, {parent_nm}")
        return doc
    except Exception as e:
        logger.warning(f"[CATEGORY] 검색 실패 또는 생성 실패 - {nm}: {e}")
        return {}

def search_kofic_index_by_title_and_director(title: str, director_list: list) -> dict:
    es = get_es_client()
    if not title or not director_list:
        return {}

    try:
        director_should = [{"match_phrase": {"directors": d}} for d in director_list]
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"movieNm": title}}  # 정확한 문구 일치
                    ],
                    "should": director_should,
                    "minimum_should_match": 1
                }
            }
        }

        res = es.search(index="kofic-index", body=query)
        hits = res.get("hits", {}).get("hits", [])
        return hits[0]["_source"] if hits else {}

    except NotFoundError:
        logger.warning("[KOFIC] 인덱스 검색 실패: KOFIC 인덱스를 찾을 수 없습니다.")
        return {}
    except Exception as e:
        logger.warning(f"[KOFIC] 제목+감독 검색 중 오류 발생: {e}")
        return {}

def exists_movie_by_kofic_code(kofic_code: str) -> bool:
    es = get_es_client()
    if not kofic_code:
        return False

    try:
        query = {
            "query": {
                "term": {
                    "KOFICCode.keyword": kofic_code  # 정확 일치 검색을 위해 .keyword 사용
                }
            }
        }

        res = es.search(index="movie-index", body=query)
        hits = res.get("hits", {}).get("hits", [])
        return len(hits) > 0

    except NotFoundError:
        return False
    except Exception as e:
        logger.warning(f"[MOVIE] KOFICCode 존재 여부 검색 중 오류 발생: {e}")
        return False

def get_movie_document_id_by_kofic_code(kofic_code: str) -> str | None:
    es = get_es_client()
    try:
        res = es.search(index="movie-index", body={
            "query": {
                "term": {
                    "KOFICCode.keyword": kofic_code
                }
            }
        }, size=1)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            return hits[0]["_id"]
    except Exception as e:
        logger.warning(f"[MOVIE] ID 조회 실패: {e}")
    return None