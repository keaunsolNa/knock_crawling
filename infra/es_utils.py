import logging
from dotenv import load_dotenv
from elasticsearch.helpers import bulk
from infra.elasticsearch_config import get_es_client
from typing import Dict, Tuple

load_dotenv()
logger = logging.getLogger(__name__)
category_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
_cached_movies_by_kofic_code: Dict[str, dict] = {}
_cached_kofic_by_kofic_code: Dict[str, dict] = {}
_cached_kopis_by_kopis_code: Dict[str, dict] = {}

def save_to_es(index: str, documents: list, dedup_keys: list = None):

    es = get_es_client()
    actions = []
    for doc in documents:

        if not doc or not isinstance(doc, dict):
            continue  # ❗ None, 빈 dict 방지
        if not index or not isinstance(index, str) or index.strip() == "":
            print(index)
            raise ValueError("❌ [ES] index is missing or invalid. 전달된 index 값이 없습니다.")

        is_update = doc.pop("__update__", False)
        kofic_code = doc.get("KOFICCode")
        doc_id = None

        if is_update and kofic_code:

            try:
                # 🧠 기존 문서 조회
                search_result = es.search(index=index, query={"term": {"KOFICCode.keyword": kofic_code}})
                hits = search_result["hits"]["hits"]

                if hits:
                    existing_doc = hits[0]["_source"]
                    doc_id = hits[0]["_id"]
                    partial_doc = {}

                    # 🧩 reservationLink 병합
                    existing_links = existing_doc.get("reservationLink", [None, None, None])
                    incoming_links = doc.get("reservationLink", [None, None, None])
                    merged_links = [
                        new if new else old for new, old in zip(incoming_links, existing_links)
                    ]
                    if any(merged_links):
                        partial_doc["reservationLink"] = merged_links

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
                            "_id": doc_id,
                            "doc": partial_doc,
                            "doc_as_upsert": False
                        })

            except Exception as e:
                logger.warning(f"[ES] 기존 문서 조회 실패: {doc_id}, 예외: {e}")
                actions.append({
                    "_op_type": "index",
                    "_index": index,
                    "_source": doc
                })
        else:
            action = {
                "_op_type": "index",
                "_index": index,
                "_source": doc
            }
            actions.append(action)

    success, _ = bulk(es, actions, raise_on_error=False)
    print(f"✅ Elasticsearch 저장 완료: {success}/{len(actions)}")

# category-level-two 캐싱
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

# category-level-two fetch/create
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

# kofic-index 캐싱
def load_all_kofic_into_cache(index_name="kofic-index"):
    global _cached_kofic_by_kofic_code

    es = get_es_client()
    try:
        response = es.search(index=index_name, body={"query": {"match_all": {}}}, size=10000)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            kofic_code = src.get("KOFICCode")
            if kofic_code:
                _cached_kofic_by_kofic_code[kofic_code] = {
                    **src,
                    "_id": hit["_id"]
                }
        logger.info(f"[CACHE] kofic 캐시 적재 완료: {len(_cached_kofic_by_kofic_code)}편")
    except Exception as e:
        logger.warning(f"[CACHE] kofic-index 캐싱 실패: {e}")

# kofic-index kofic 기반 exist 검색
def exists_kofic_by_kofic_code(kofic_code: str) -> bool:

    print(kofic_code)
    if not kofic_code:
        return False
    return kofic_code in _cached_kofic_by_kofic_code

# kofic-index 캐시 기반 title/director 로 검색
def search_kofic_index_by_title_and_director(title: str, director_list: list) -> dict:

    if not title or not director_list:
        return {}

    best_match = None
    for kofic_code, data in _cached_kofic_by_kofic_code.items():
        # 제목 완전 일치
        if data.get("movieNm") != title:
            continue

        # 감독 일치율 계산
        cached_directors = data.get("directors", [])
        if not cached_directors:
            continue

        matched = any(d in cached_directors for d in director_list)
        if matched:
            best_match = data
            break  # 첫 매칭 결과 반환 (또는 일치율 높은 결과를 탐색할 수도 있음)

    return best_match if best_match else {}

# kopis-index 캐싱
def load_all_kopis_into_cache(index_name="kopis-index"):
    global _cached_kopis_by_kopis_code

    es = get_es_client()
    try:
        response = es.search(index=index_name, body={"query": {"match_all": {}}}, size=10000)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            kopis_code = src.get("code")
            if kopis_code:
                _cached_kopis_by_kopis_code[kopis_code] = {
                    **src,
                    "_id": hit["_id"]
                }
        logger.info(f"[CACHE] kopis 캐시 적재 완료: {len(_cached_kopis_by_kopis_code)}편")
    except Exception as e:
        logger.warning(f"[CACHE] kopis-index 캐싱 실패: {e}")

# kopis-index kopis 기반 exist 검색
def exists_kopis_by_kopis_code(kopis_code: str) -> bool:
    if not kopis_code:
        return False
    return kopis_code in _cached_kopis_by_kopis_code

# movie-index 캐싱
def load_all_movies_into_cache(index_name="movie-index"):
    global _cached_movies_by_kofic_code

    es = get_es_client()
    try:
        response = es.search(index=index_name, body={"query": {"match_all": {}}}, size=10000)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            kofic_code = src.get("KOFICCode")
            if kofic_code:
                _cached_movies_by_kofic_code[kofic_code] = {
                    **src,
                    "_id": hit["_id"]
                }
        logger.info(f"[CACHE] 영화 캐시 적재 완료: {len(_cached_movies_by_kofic_code)}편")
    except Exception as e:
        logger.warning(f"[CACHE] movie-index 캐싱 실패: {e}")

# movie-index kofic 기반 exist 검색
def exists_movie_by_kofic_code(kofic_code: str) -> bool:
    if not kofic_code:
        return False
    return kofic_code in _cached_movies_by_kofic_code

# movie-index kofic 기반 검색
def get_movie_document_id_by_kofic_code(kofic_code: str) -> str | None:
    doc = _cached_movies_by_kofic_code.get(kofic_code)
    return doc.get("_id") if doc else None