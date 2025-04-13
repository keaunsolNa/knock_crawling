from abc import ABC, abstractmethod

class CrawlingInterface(ABC):
    @abstractmethod
    def crawl(self):
        pass