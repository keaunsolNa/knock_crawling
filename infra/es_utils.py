import logging
from dotenv import load_dotenv
from elasticsearch.helpers import bulk
from infra.elasticsearch_config import get_es_client
from typing import Dict, Tuple

load_dotenv()
logger = logging.getLogger(__name__)
category_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
_cached_movies_by_kofic_code: Dict[str, dict] = {}
_cached_movies_by_title: Dict[str, dict] = {}
_cached_kofic_by_kofic_code: Dict[str, dict] = {}
_cached_kopis_by_kopis_code: Dict[str, dict] = {}

def save_to_es(index: str, documents: list):

    es = get_es_client()
    actions = []
    for doc in documents:

        if not doc or not isinstance(doc, dict):
            continue  # ❗ None, 빈 dict 방지
        if not index or not isinstance(index, str) or index.strip() == "":
            raise ValueError("❌ [ES] index is missing or invalid. 전달된 index 값이 없습니다.")

        is_update  = doc.pop("__update__", False)
        is_delete  = doc.pop("__delete__", False)
        kofic_code = doc.get("KOFICCode")
        movie_nm   = doc.get("movieNm")
        doc_id = None

        if is_delete:
            try:
                if kofic_code:
                    search_result = es.search(index=index, query={"term": {"KOFICCode.keyword": kofic_code}})
                else:
                    search_result = es.search(index=index, query={"term": {"movieNm.keyword": movie_nm}})
                hits = search_result["hits"]["hits"]
                if hits:
                    doc_id = hits[0]["_id"]
                    actions.append({
                        "_op_type": "delete",
                        "_index": index,
                        "_id": doc_id
                    })
            except Exception as e:
                logger.warning(f"[ES] 문서 삭제 실패: {doc_id}, 예외: {e}")
            continue  # 삭제 완료 후 다음 문서 처리

        elif is_update :

            try:
                # 🧠 기존 문서 조회
                search_result = es.search(index=index, query={"term": {"KOFICCode.keyword": kofic_code}})
                hits = search_result["hits"]["hits"]

                if hits:

                    setting_doc(hits=hits, doc=doc, actions=actions, index=index)

                else:
                    search_result = es.search(index=index, query={"term": {"movieNm.keyword": movie_nm}})
                    hits = search_result["hits"]["hits"]

                    if hits:

                        setting_doc(hits=hits, doc=doc, actions=actions, index=index)


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
    es.indices.refresh(index=index)

# save_to_es doc 셋팅
def setting_doc (hits, doc, actions, index):
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

# category-level-two 캐싱
def load_all_categories_into_cache(parent_nm: str = "MOVIE"):
    es = get_es_client()
    query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"parentNm": parent_nm}}
                ]
            }
        },
        "size": 10000
    }
    try:
        response = es.search(index="category-level-two-index", body=query)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            src = {**src, "id": hit["_id"]}
            key = (src["nm"].strip().upper(), src["parentNm"].strip().upper())
            category_cache[key] = src
        logger.info(f"[CACHE] Loaded {len(category_cache)} categories into cache.")
    except Exception as e:
        logger.warning(f"[CACHE] 카테고리 캐싱 실패: {e}")

def update_kofic_docs_with_category_ids():
    es = get_es_client()
    query = {
        "query": {
            "match_all": {}
        },
        "size": 10000  # 필요한 양에 따라 늘릴 수 있음
    }

    try:
        response = es.search(index="movie-index", body=query)
        actions = []

        for hit in response.get("hits", {}).get("hits", []):
            doc_id = hit["_id"]
            src = hit["_source"]

            updated = False
            if "categoryLevelTwo" in src:
                for cat in src["categoryLevelTwo"]:
                    key = (cat.get("nm", "").strip().upper(), cat.get("parentNm", "").strip().upper())
                    if key in category_cache:
                        cat["id"] = category_cache[key]["id"]
                        updated = True
                    else:
                        logger.warning(f"[WARN] No matching category found in cache for {key}")

            if updated:
                actions.append({
                    "_op_type": "update",
                    "_index": "movie-index",
                    "_id": doc_id,
                    "doc": {
                        "categoryLevelTwo": src["categoryLevelTwo"]
                    }
                })

        if actions:
            bulk(es, actions)
            logger.info(f"[BULK UPDATE] {len(actions)}개의 문서가 성공적으로 업데이트되었습니다.")
        else:
            logger.info("[BULK UPDATE] 업데이트할 문서가 없습니다.")

    except Exception as e:
        logger.error(f"[ERROR] KOFIC 문서 업데이트 실패: {e}")

# category-level-two fetch/create
def fetch_or_create_category(nm: str, parent_nm: str = "MOVIE") -> Dict[str, str]:

    es = get_es_client()
    key = (nm.strip().upper(), parent_nm.strip().upper())
    if key in category_cache:
        return category_cache[key]

    query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"nm": nm}},
                    {"term": {"parentNm": parent_nm}}
                ]
            }
        },
        "size": 1
    }
    try:
        res = es.search(index="category-level-two-index", body=query)
        hits = res.get("hits", {}).get("hits", [])
        if hits:
            src = hits[0]["_source"]
            doc = {**src, "id": hits[0]["_id"]}  # 캐시에만 id 보관
            category_cache[key] = doc
            return doc

        # 2) 없으면 생성 (id 필드 절대 넣지 않음)
        new_doc = {
            "nm": nm,
            "parentNm": parent_nm,
            "favoriteUsers": []
        }
        idx_res = es.index(index="category-level-two-index", document=new_doc)
        doc_id = idx_res.get("_id")

        cached = {**new_doc, "id": doc_id}  # 캐시에만 id 저장
        category_cache[key] = cached
        logger.info(f"[CATEGORY] Created new category: {nm}, {parent_nm} (id={doc_id})")
        return cached
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

    if not kofic_code:
        return False
    return kofic_code in _cached_kofic_by_kofic_code

# kofic-index 캐시 기반 title/director 로 검색
def search_kofic_index_by_title_and_director(title: str, director_list: list) -> dict:

    logger.info(f"[CACHE] Title {title} & Director: {director_list}")

    if not title or not director_list:
        return {}

    best_match = None
    for kofic_code, data in _cached_kofic_by_kofic_code.items():
        # 제목 완전 일치
        if data.get("movieNm") != title:
            continue

        logger.info(f"[CACHE] Title Correct: {director_list}")
        logger.info(f"[CACHE] Title {data.get("movieNm", [])} & Director IN KOFIC: {data.get("directors", [])}")
        # 감독 일치율 계산
        cached_directors = data.get("directors", [])
        if not cached_directors:
            continue

        logger.info(f"[CACHE] Director Correct: {director_list}")
        matched = any(d in cached_directors for d in director_list)
        if matched:
            best_match = data
            break  # 첫 매칭 결과 반환 (또는 일치율 높은 결과를 탐색할 수도 있음)

    return best_match if best_match else {}

# kopis-index 캐싱
def load_all_kopis_into_cache(index_name="kopis-index"):
    from elasticsearch import helpers

    global _cached_kopis_by_kopis_code
    es = get_es_client()
    _cached_kopis_by_kopis_code.clear()

    try:
        scroll = helpers.scan(
            client=es,
            index=index_name,
            query={"query": {"match_all": {}}},
            scroll="5m",            # scroll 유지 시간
            size=1000               # batch size
        )

        count = 0
        for hit in scroll:
            src = hit["_source"]
            kopis_code = src.get("code")
            if kopis_code:
                _cached_kopis_by_kopis_code[kopis_code] = {
                    **src,
                    "_id": hit["_id"]
                }
                count += 1

        logger.info(f"[CACHE] kopis 캐시 적재 완료: {count}편")
    except Exception as e:
        logger.warning(f"[CACHE] kopis-index 캐싱 실패: {e}")

# kopis-index kopis 기반 exist 검색
def exists_kopis_by_kopis_code(kopis_code: str) -> bool:
    if not kopis_code:
        return False
    return kopis_code in _cached_kopis_by_kopis_code

# movie-index 캐싱
def load_all_movies_into_cache(index_name="movie-index"):
    global _cached_movies_by_kofic_code, _cached_movies_by_title

    es = get_es_client()
    _cached_movies_by_kofic_code.clear()
    _cached_movies_by_title.clear()

    try:
        response = es.search(index=index_name, body={"query": {"match_all": {}}}, size=10000)
        for hit in response.get("hits", {}).get("hits", []):
            src = hit["_source"]
            doc_id = hit["_id"]

            kofic_code = src.get("KOFICCode", "")
            title = src.get("movieNm", "").strip()

            if kofic_code:
                _cached_movies_by_kofic_code[kofic_code] = {**src, "_id": doc_id}
                print(_cached_movies_by_kofic_code[kofic_code])
            elif title:
                _cached_movies_by_title[title] = {**src, "_id": doc_id}
                print(_cached_movies_by_title[title])

        logger.info(f"[CACHE] 영화 캐시 적재 완료: {len(_cached_movies_by_kofic_code)}편")
        logger.info(f"[CACHE] 영화 캐시 적재 완료: {len(_cached_movies_by_title)}편")
        logger.info(f"[CACHE] 영화 캐시 전체 적재 완료: {len(_cached_movies_by_title) + len(_cached_movies_by_kofic_code)}편")
    except Exception as e:
        logger.warning(f"[CACHE] movie-index 캐싱 실패: {e}")

# movie-index kofic 기반 exist 검색
def exists_movie_by_kofic_code(kofic_code: str) -> bool:

    logger.info(f"[CACHE] 영화 캐시에서 검색, KOFIC_CODE : {kofic_code}")
    if kofic_code in _cached_movies_by_kofic_code:
        logger.info(f"[CACHE] ✅ 캐시 HIT: {_cached_movies_by_kofic_code[kofic_code]}")
    else:
        logger.info(f"[CACHE] ❌ 캐시 MISS: {kofic_code}")

    return kofic_code in _cached_movies_by_kofic_code if kofic_code else False

# movie_index nm 기준 exist 검색
def exists_movie_by_nm(nm: str):

    logger.info(f"[CACHE] 영화 캐시에서 검색, 제목 : {nm}")
    if nm in _cached_movies_by_title:
        logger.info(f"[CACHE] ✅ 캐시 HIT: {_cached_movies_by_title[nm]}")
    else:
        logger.info(f"[CACHE] ❌ 캐시 MISS: {nm}")

    return nm in _cached_movies_by_title if nm else False

# movie-index kofic 기반 검색
def get_movie_document_id_by_kofic_code(kofic_code: str) -> str | None:
    doc = _cached_movies_by_kofic_code.get(kofic_code)
    return doc.get("_id") if doc else None

# movie-index nm 기반 검색
def get_movie_document_id_by_nm(nm: str) -> str | None:
    doc = _cached_movies_by_title.get(nm)
    return doc.get("_id") if doc else None

def split_comma(s: str | None) -> list[str]:
    if not s or not isinstance(s, str):
        return []
    return [item.strip() for item in s.split(",") if item.strip()]