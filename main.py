import asyncio

from dotenv import load_dotenv
from jobs.scheduler import main as scheduler_main

load_dotenv()

if __name__ == "__main__":
    print("🔍 [MAIN] 스케줄러 실행됨")
    asyncio.run(scheduler_main())
