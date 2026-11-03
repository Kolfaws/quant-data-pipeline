from abc import ABC, abstractmethod


class BaseConnector(ABC):
    @abstractmethod
    def fetch(self, *args, **kwargs):
        """获取数据的抽象方法"""
        pass
