from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from llm_gym.logging_broker.messages import Message

T = TypeVar("T")


class MessageSubscriberIF(ABC, Generic[T]):

    @abstractmethod
    def consume_message(self, message: Message[T]):
        raise NotImplementedError
    
