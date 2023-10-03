from abc import ABC, abstractmethod


class AbstractValueObject(ABC):
    @abstractmethod
    def dump(self) -> dict:
        raise NotImplementedError

    def __hash__(self) -> int:
        return hash(frozenset(self.dump()))

    def __eq__(self, other):
        if isinstance(other, AbstractValueObject):
            return hash(self) == hash(other)
        return False


class AbstractEntity(ABC):
    id: int

    @abstractmethod
    def dump(self) -> dict:
        pass

    def __eq__(self, other):
        if isinstance(other, AbstractEntity):
            return self.id == other.id
        return False


class AbstractDTO(ABC):
    @abstractmethod
    def dump(self) -> dict:
        pass


class AbstractAggregate(ABC):
    @abstractmethod
    def dump(self) -> dict:
        pass
