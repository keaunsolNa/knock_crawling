from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
import asyncio
from crawling.services.kopis import KOPISCrawler
from crawling.services.kofic import KOFICCrawler
import os
from dotenv import load_dotenv

load_dotenv()

async def run_kopis():

    one_year_ago_january_first = date.today().replace(year=date.today().year - 1, month=1, day=1)

    config = {
        "url": os.getenv("KOPIS_API_URL"),
        "params": {
            "service": os.getenv("KOPIS_API_KEY"),
            "stdate": one_year_ago_january_first.strftime("%Y%m%d"),
            "eddate": "29991231",
            "cpage": "1",
            "rows": "100"
        }
    }
    crawler = KOPISCrawler(config)
    results = crawler.crawl()
    print(f"[SCHEDULER] KOPIS crawled {len(results)} items")

async def run_kofic():
    start_date = date.today().replace(year=date.today().year - 1).strftime("%Y")
    config = {
        "url": os.getenv("KOFIC_API_URL"),
        "params": {
            "key": os.getenv("KOFIC_API_KEY"),
            "openStartDt": start_date,
            "itemPerPage": "10"
        }
    }
    crawler = KOFICCrawler(config)
    results = crawler.crawl()
    print(f"[SCHEDULER] KOFIC crawled {len(results)} items")

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_kopis, CronTrigger(second="*/30"))
    scheduler.add_job(run_kofic, CronTrigger(second="*/30"))
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())