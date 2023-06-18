from abc import abstractmethod
from typing import Any, TypeVar, Generic
from domino.base.baseclass import DominoBaseClass

T = TypeVar('T')


class AbstractRepository(DominoBaseClass):

    def start_transaction(self):
        return
    
    def commit_transaction(self):
        return

    def rollback_transaction(self):
        return


# Crud Abstract Mixins
class GetRepositoryMixin(AbstractRepository, Generic[T]):
    """Mixin that implements the get function to a repository

    `get(id: Any) -> Any` should be used to retrieve a document data
    from a datasource
    """ 
    @abstractmethod
    def get(self, id: Any) -> T:
        return NotImplemented
    
class ListRepositoryMixin(DominoBaseClass, Generic[T]):
    """Mixin that implements the list function to a repository

    `list(filter_data: Any) -> Any` should be used to retrieve
    a list of documents based on a filter.
    """ 
    @abstractmethod
    def list(self, filter_data: Any) -> T:
        return NotImplemented
    
class CreateRepositoryMixin(DominoBaseClass, Generic[T]):
    """Mixin that implements the create function to a repository

    `create(data: Any) -> Any` should be used to save a document in
    datasource
    """ 
    @abstractmethod
    def create(self, data: T) -> T:
        return NotImplemented
    
class UpdateRepositoryMixin(DominoBaseClass, Generic[T]):
    """Mixin that implements the create function to a repository

    `create(data: Any) -> Any` should be used to save a document in
    datasource
    """ 
    @abstractmethod
    def update(self, id: Any, data: T) -> T:
        return NotImplemented
    
class DeleteRepositoryMixin(DominoBaseClass, Generic[T]):
    """Mixin that implements the delete function to a repository

    `delete(id: Any) -> None` should be used to delete a document from a
    datasource
    """ 
    @abstractmethod
    def delete(self, id: Any) -> None:
        return NotImplemented
    

# Abstract Crud Repositories
class AbstractReadOnlyRepository(
    GetRepositoryMixin[T],
    ListRepositoryMixin[T]
):
    pass

class AbstractWriteOnlyRepository(
    CreateRepositoryMixin[T],
    UpdateRepositoryMixin[T],
    DeleteRepositoryMixin[T]
):
    pass

class AbstractCRUDRepository(
    AbstractReadOnlyRepository,
    AbstractWriteOnlyRepository,
    Generic[T]
):
    pass