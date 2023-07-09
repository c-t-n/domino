from datetime import datetime
from pydantic import BaseModel

from typing import Generic, TypeVar

KeyT = TypeVar('KeyT', bound=BaseModel)
ValueT = TypeVar('ValueT', bound=BaseModel)


class KafkaMessageMock(BaseModel, Generic[KeyT, ValueT]):
    timestamp: datetime
    offset: int
    key: KeyT
    value: ValueT | None

    class Config:
        allow_arbitrary_types = True







class MockKafkaClusterRepository(Generic[KeyT, ValueT]):
    
    topics: list[str] = []

    def __init__(self):
        self.__cluster: dict[str, list[KafkaMessageMock[KeyT, ValueT]]] = { 
            topic: [] 
            for topic in self.topics
        }


    def produce(self, topic: str, key: KeyT, value: ValueT | None):
        if topic not in self.__cluster.keys():
            raise ValueError("topic not in cluster")
        
        msg = KafkaMessageMock(
            timestamp=datetime.utcnow(),
            offset=len(self.__cluster[topic]),
            key=key,
            value=value
        )

        self.__cluster[topic].append(msg)
