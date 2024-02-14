from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from domino.domain.models.abstract import AbstractDTO, AbstractEntity

BaseT = TypeVar("BaseT", bound=AbstractEntity)
CreateT = TypeVar("CreateT", bound=AbstractDTO)
UpdateT = TypeVar("UpdateT", bound=AbstractDTO)


class AbstractRepository():
    pass


# Crud Abstract Mixins
class GetRepositoryMixin(AbstractRepository, Generic[BaseT], ABC):
    """Mixin that implements the get function to a repository

    `get(id: Any) -> BaseT` should be used to retrieve a document data
    from a datasource. If the document does not exist, it should raise
    an ItemNotFound exception
    """

    @abstractmethod
    def get(self, id: Any) -> BaseT:
        return NotImplemented


class ListRepositoryMixin(AbstractRepository, Generic[BaseT], ABC):
    """Mixin that implements the list function to a repository

    `list(filter_data: Any) -> tuple[int, list[BaseT]]` should be used to retrieve
    a tuple with the total count of documents from the filter and a list of
    documents data from a datasource
    """

    @abstractmethod
    def list(self, filter_data: Any) -> tuple[int, list[BaseT]]:
        return NotImplemented


class CreateRepositoryMixin(AbstractRepository, Generic[BaseT, CreateT], ABC):
    """Mixin that implements the create function to a repository

    `create(data: CreateT) -> BaseT` should be used to save a document in
    datasource and return the created entity
    """

    @abstractmethod
    def create(self, data: CreateT) -> BaseT:
        return NotImplemented


class UpdateRepositoryMixin(AbstractRepository, Generic[BaseT, UpdateT], ABC):
    """Mixin that implements the create function to a repository

    `update(self, id: Any, data: UpdateT) -> BaseT:` should be used to update
    a document in datasource and return the updated entity
    """

    @abstractmethod
    def update(self, id: Any, data: UpdateT) -> BaseT:
        return NotImplemented


class DeleteRepositoryMixin(AbstractRepository, Generic[BaseT], ABC):
    """Mixin that implements the delete function to a repository

    `delete(id: Any) -> None` should be used to delete a document from a
    datasource
    """

    @abstractmethod
    def delete(self, id: Any) -> None:
        raise NotImplementedError


class SaveRepositoryMixin(AbstractRepository, Generic[BaseT], ABC):
    """Mixin that implements the save function to a repository

    `save(data: BaseT) -> BaseT` should be used to save a document in
    datasource and return the saved entity
    """

    @abstractmethod
    def save(self, data: BaseT) -> BaseT:
        raise NotImplementedError


# Abstract Crud Repositories
class AbstractReadOnlyRepository(
    GetRepositoryMixin[BaseT],
    ListRepositoryMixin[BaseT],
    ABC,
):
    """Abstract repository that implements the read only operations"""

    pass


class AbstractWriteOnlyRepository(
    CreateRepositoryMixin[BaseT, CreateT],
    UpdateRepositoryMixin[BaseT, UpdateT],
    DeleteRepositoryMixin[BaseT],
    ABC,
):
    """Abstract repository that implements the write only operations"""

    pass


class AbstractCRUDRepository(
    AbstractReadOnlyRepository[BaseT],
    AbstractWriteOnlyRepository[BaseT, CreateT, UpdateT],
    ABC,
):
    """
    Abstract repository that implements the CRUD operations
    """

    pass
