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
        action = {
            "_index": index,
            "_source": doc
        }
        if dedup_keys:
            doc_id = "_".join([str(doc.get(k, '')) for k in dedup_keys])
            action["_id"] = doc_id
        actions.append(action)
    success, _ = bulk(es, actions, raise_on_error=False)
    print(f"✅ Elasticsearch 저장 완료: {success}/{len(documents)}")

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

def search_kofic_index_by_title_and_director(title: str, director: list) -> dict:
    es = get_es_client()
    if not title or not director:
        return {}

    try:
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"movieNm": title}},
                        {
                            "bool": {
                                "should": [{"match": {"directors": d}} for d in director],
                                "minimum_should_match": 1
                            }
                        }
                    ]
                }
            }
        }

        res = es.search(index="kofic-index", body=query)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            return hits[0]["_source"]
        return {}
    except NotFoundError:
        logger.warning("[KOFIC] 인덱스 검색 실패: KOFIC 인덱스를 찾을 수 없습니다.")
        return {}
    except Exception as e:
        logger.warning(f"[KOFIC] 제목+감독 검색 중 오류 발생: {e}")
        return {}