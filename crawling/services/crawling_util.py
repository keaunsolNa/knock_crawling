import requests
import ssl
import logging
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from urllib3 import PoolManager
from requests.adapters import HTTPAdapter

from crawling.base.webdriver_config import create_driver

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

def get_detail_data_with_selenium(url: str, timeout: int = 10) -> BeautifulSoup:
    driver = create_driver()
    try:
        driver.get(url)

        # 실제 내용을 담고 있는 React 컨테이너가 로딩될 때까지 대기
        WebDriverWait(driver, timeout).until(
            expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "div.movi_tab_info1"))  # 또는 "ul.detail_info2"
        )

        # 동적으로 로딩된 div의 innerHTML 가져오기
        content_element = driver.find_element(By.CSS_SELECTOR, "div.movi_tab_info1")
        inner_html = content_element.get_attribute("innerHTML")
        return BeautifulSoup(inner_html, "html.parser")
    except Exception as e:
        logger.warning(f"[LOTTE] 상세 페이지 로딩 실패: {e}")
        return None
    finally:
        driver.quit()
