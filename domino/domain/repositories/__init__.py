from abc import abstractmethod
from typing import Any, TypeVar, Generic
from domino.base.baseclass import DominoBaseClass
from domino.domain.models.pydantic import DomainModel, DTO

BaseT = TypeVar('BaseT', bound=DomainModel)
CreateT = TypeVar('CreateT', bound=DTO)
UpdateT = TypeVar('UpdateT', bound=DTO)


class AbstractRepository(DominoBaseClass):

    def start_transaction(self):
        return
    
    def commit_transaction(self):
        return

    def rollback_transaction(self):
        return


# Crud Abstract Mixins
class GetRepositoryMixin(AbstractRepository, Generic[BaseT]):
    """Mixin that implements the get function to a repository

    `get(id: Any) -> Any` should be used to retrieve a document data
    from a datasource
    """ 
    @abstractmethod
    def get(self, id: Any) -> BaseT | None:
        return NotImplemented
    
class ListRepositoryMixin(AbstractRepository, Generic[BaseT]):
    """Mixin that implements the list function to a repository

    `list(filter_data: Any) -> Any` should be used to retrieve
    a list of documents based on a filter.
    """ 
    @abstractmethod
    def list(self, filter_data: Any) -> list[BaseT]:
        return NotImplemented
    
class CreateRepositoryMixin(AbstractRepository, Generic[BaseT, CreateT]):
    """Mixin that implements the create function to a repository

    `create(data: Any) -> Any` should be used to save a document in
    datasource
    """ 
    @abstractmethod
    def create(self, data: CreateT) -> BaseT:
        return NotImplemented
    
class UpdateRepositoryMixin(AbstractRepository, Generic[BaseT, UpdateT]):
    """Mixin that implements the create function to a repository

    `create(data: Any) -> Any` should be used to save a document in
    datasource
    """ 
    @abstractmethod
    def update(self, id: Any, data: UpdateT) -> BaseT:
        return NotImplemented
    
class DeleteRepositoryMixin(AbstractRepository, Generic[BaseT]):
    """Mixin that implements the delete function to a repository

    `delete(id: Any) -> None` should be used to delete a document from a
    datasource
    """ 
    @abstractmethod
    def delete(self, id: Any) -> None:
        raise NotImplementedError
    

# Abstract Crud Repositories
class AbstractReadOnlyRepository(
    GetRepositoryMixin[BaseT],
    ListRepositoryMixin[BaseT]
):
    pass

class AbstractWriteOnlyRepository(
    CreateRepositoryMixin[BaseT, CreateT],
    UpdateRepositoryMixin[BaseT, UpdateT],
    DeleteRepositoryMixin[BaseT]
):
    pass

class AbstractCRUDRepository(
    AbstractReadOnlyRepository[BaseT],
    AbstractWriteOnlyRepository[BaseT, CreateT, UpdateT],
):
    pass
