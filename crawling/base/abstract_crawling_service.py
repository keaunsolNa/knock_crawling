from abc import ABC, abstractmethod
from typing import List, Any

class AbstractCrawlingService(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def get_crawling_data(self) -> List[dict]:
        pass

    @abstractmethod
    def create_dto(self, item: dict) -> dict:
        pass

    @abstractmethod
    def crawl(self) -> List[Any]:
        pass