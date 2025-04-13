import requests
import ssl
import logging
from bs4 import BeautifulSoup
from urllib3 import PoolManager
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")  # 핵심
        self.poolmanager = PoolManager(*args, ssl_context=ctx, **kwargs)

def get_detail_data(url: str) -> BeautifulSoup | None:
    try:
        session = requests.Session()
        session.mount("https://", SSLAdapter())

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = session.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    except Exception as e:
        logger.warning(f"[HTML_UTILS] 상세 페이지 요청 실패: {e}")
        return None
