from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

import time
import logging

logger = logging.getLogger(__name__)

def create_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-notifications")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def scroll_until_loaded(driver: webdriver.Chrome, selector: str, max_scroll: int = 50, wait_sec: int = 1):
    prev_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0

    while scroll_count < max_scroll:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(wait_sec)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == prev_height:
            break
        prev_height = new_height
        scroll_count += 1

def click_until_disappear(driver, css_selector: str, timeout: int = 10):
    try:
        wait = WebDriverWait(driver, timeout)

        while True:
            try:
                next_btn = wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, css_selector)))

                if next_btn.is_displayed():
                    next_btn.click()
                    # 클릭한 버튼이 stale 상태가 될 때까지 대기
                    wait.until(expected_conditions.staleness_of(next_btn))
                else:
                    break
            except Exception:
                break  # 버튼이 더 이상 없거나 비활성화된 경우

    except Exception as e:
        logger.warning(f"다음 페이지 버튼 클릭 중 에러 발생: {e}")