from dotenv import load_dotenv
load_dotenv()

from elasticsearch import Elasticsearch
import os

def get_es_client():
    es = Elasticsearch(
        os.getenv("BONSAI_URL"),
        verify_certs=True,
        ssl_show_warn=False,
        request_timeout=60,
        headers={"X-Elastic-Product": "Elasticsearch"}
    )
    # 👇 이 줄이 핵심: 검증 로직 강제로 통과시킴
    es.transport._verified_elasticsearch = True
    return es
