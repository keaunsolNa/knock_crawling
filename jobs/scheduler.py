from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import os
from dotenv import load_dotenv
from datetime import date
from crawling.services import CGVCrawler, MEGABOXCrawler, LOTTECrawler, KOFICCrawler, KOPISCrawler
from infra.es_utils import save_to_es, load_all_movies_into_cache
from infra.discord_notify import send_discord_message

load_dotenv()

async def run_scheduler():

    one_year_ago_january_first = date.today().replace(year=date.today().year - 1, month=1, day=1)
    start_date = date.today().replace(year=date.today().year - 1).strftime("%Y")

    kopis_config = {
        "url": os.getenv("KOPIS_API_URL"),
        "params": {
            "service": os.getenv("KOPIS_API_KEY"),
            "stdate": one_year_ago_january_first.strftime("%Y%m%d"),
            "eddate": "29991231",
            "cpage": "1",
            "rows": "100"
        }
    }
    kofic_config = {
        "url": os.getenv("KOFIC_API_URL"),
        "url_sub": os.getenv("KOFIC_API_URL_SUB"),
        "params": {
            "key": os.getenv("KOFIC_API_KEY"),
            "openStartDt": start_date,
            "itemPerPage": "100",
            "curPage": "1",
            "rows": "100"
        }
    }

    megabox_config = {
        "url": os.getenv("MEGABOX_API_URL"),
        "url_sub": os.getenv("MEGABOX_API_URL_SUB")
    }

    cgv_config = {
        "url": os.getenv("CGV_API_URL"),
        "url_sub": os.getenv("CGV_API_URL_SUB")
    }

    lotte_config = {
        "url": os.getenv("LOTTE_API_URL"),
        "url_sub": os.getenv("LOTTE_API_URL_SUB")
    }

    try:
        kopis = KOPISCrawler(kopis_config)
        result = kopis.crawl()
        print("📦 KOPIS 결과 총 수량", len(result))
        save_to_es("kopis-index", result, dedup_keys=["name", "start_date"])
        send_discord_message(f"✅ KOPIS 크롤링 완료! 수량: {len(result)}개")

    except Exception as e:
        print("❌ KOPIS 실패:", e)
        send_discord_message(f"✅ KOPIS 크롤링 실패! {str(e)}")

    try:
        kofic = KOFICCrawler(kofic_config)
        result = kofic.crawl()
        print("📦 KOFIC 결과 총 수량", len(result))
        save_to_es("kofic-index", result, dedup_keys=["movieNm", "openDt"])
        send_discord_message(f"✅ KOFIC 크롤링 완료! 수량: {len(result)}개")

    except Exception as e:
        print("❌ KOFIC 실패:", e)
        send_discord_message(f"✅ KOFIC 크롤링 실패! {str(e)}")

    load_all_movies_into_cache()
    try:
        megabox = MEGABOXCrawler(megabox_config)
        result = megabox.crawl()
        print("📦 MEGABOX 결과 총 수량", len(result))
        print(result)
        send_discord_message(f"✅ MEGABOX 크롤링 완료! 수량: {len(result)}개")

        save_to_es("movie-index", result, dedup_keys=["movieNm", "openDt"])
    except Exception as e:
        print("❌ MEGABOX 실패:", e)
        send_discord_message(f"✅ MEGABOX 크롤링 실패! {str(e)}")

    load_all_movies_into_cache()
    try:
        cgv = CGVCrawler(cgv_config)
        result = cgv.crawl()
        print("📦 CGV 결과 총 수량", len(result))
        print(result)

        save_to_es("movie-index", result, dedup_keys=["movieNm", "openDt"])
        send_discord_message(f"✅ CGV 크롤링 완료! 수량: {len(result)}개")

    except Exception as e:
        print("❌ CGV 실패:", e)
        send_discord_message(f"✅ CGV 크롤링 실패! {str(e)}")


    load_all_movies_into_cache()
    try:
        lotte = LOTTECrawler(lotte_config)
        result = lotte.crawl()
        print("📦 LOTTE 결과 총 수량", len(result))
        print(result)

        save_to_es("movie-index", result, dedup_keys=["movieNm", "openDt"])
        send_discord_message(f"✅ LOTTE 크롤링 완료! 수량: {len(result)}개")

    except Exception as e:
        print("❌ LOTTE 실패:", e)
        send_discord_message(f"✅ LOTTE 크롤링 실패! {str(e)}")

async def main():
    scheduler = AsyncIOScheduler()
    trigger = CronTrigger(minute='0', timezone='Asia/Seoul')
    scheduler.add_job(run_scheduler, trigger)
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())