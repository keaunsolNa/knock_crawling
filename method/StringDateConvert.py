import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class StringDateConvertLongTimeStamp:

    @staticmethod
    def string_to_epoch(date_string: str) -> int:
        if not date_string:
            logger.warning("parameter is null")
            return 0

        if date_string == "오픈런":
            date_string = "99991231"

        formats = {
            4: "%Y",
            6: "%Y%m",
            7: "%Y.%m",
            8: "%Y%m%d",
            10: "%Y.%m.%d"
        }

        fmt = formats.get(len(date_string))
        if not fmt:
            logger.warning(f"parameter is Illegal: {date_string} ({len(date_string)})")
            return 0

        try:
            dt = datetime.strptime(date_string, fmt)
            # Convert to epoch in milliseconds (KST assumed)
            return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        except Exception as e:
            logger.warning(f"파싱 중 에러 발생: {str(e)}")
            return 0

    @staticmethod
    def epoch_to_string(epoch_millis: int) -> str:
        if epoch_millis == 0:
            logger.warning("parameter is null")
            return "개봉 예정"

        try:
            dt = datetime.fromtimestamp(epoch_millis / 1000, tz=timezone.utc)
            return dt.strftime("%Y.%m.%d")
        except Exception as e:
            logger.warning(f"변환 중 에러 발생: {str(e)}")
            return "개봉 예정"
