from domino.domain.services import Service
from domino.domain.uow import AbstractUnitOfWork
from domino.domain.repositories import AbstractCRUDRepository
from domino.adapters.mocks.kv import MockedKVRepository
from domino.domain.models.pydantic import DomainModel, DTO


class UserNotFound(Exception):
    pass


class UserAlreadyActivated(Exception):
    pass


class User(DomainModel):
    """BaseUser model. Used as base for doc representation"""
    id: int
    login: str
    is_activated: bool = False


class UserCreate(DTO):
    """CreateUser model. Used for User Creation"""
    login: str


class UserUpdate(DTO):
    """UpdateUser model. Used for User Update"""
    login: str | None = None
    is_activated: bool | None = None


class AbstractUserRepository(
    AbstractCRUDRepository[
        User,
        UserCreate,
        UserUpdate
    ]
):
    """Full CRUD Repository"""
    pass


class MockedKVTestUserRepository(
    MockedKVRepository[User,UserCreate,UserUpdate],
    AbstractUserRepository,

):
    """Full CRUD Repository, as Mocked KeyValue Repo"""
    primary_key_property = "id"
    base_model = User


class UserUnitOfWork(AbstractUnitOfWork):
    test_user_repository: AbstractUserRepository


class UserService(Service[UserUnitOfWork]):
    def get_user(self, user_id: int) -> User:
        with self.unit_of_work as uow:
            user = uow.test_user_repository.get(user_id)

        if user is None:
            raise UserNotFound

        return user

    def list_users(self) -> list[User]:
        with self.unit_of_work as uow:
            return uow.test_user_repository.list({})[:20]

    def create_user(self, data: UserCreate) -> User:
        with self.unit_of_work as uow:
            return uow.test_user_repository.create(data)

    def update_user(self, user_id: int, data: UserUpdate) -> User:
        with self.unit_of_work as uow:
            return uow.test_user_repository.update(user_id, data)

    def delete_user(self, user_id: int) -> None:
        with self.unit_of_work as uow:
            return uow.test_user_repository.delete(user_id)

    def activate_user(self, user_id: int) -> User:
        with self.unit_of_work as uow:
            user = self.get_user(user_id)
            if user.is_activated:
                raise UserAlreadyActivated

            user = uow.test_user_repository.update(
                user_id,
                UserUpdate(is_activated=True)
            )

        return user

#################
# Tests         #
#################


class TestEndToEnd:
    def setup_method(self):
        self.unit_of_work = UserUnitOfWork(
            test_user_repository=MockedKVTestUserRepository
        )

        self.service = UserService(unit_of_work=self.unit_of_work)

        self.service.create_user(UserCreate(login="hello"))
        self.service.create_user(UserCreate(login="world"))
        self.service.create_user(UserCreate(login="wavery"))

    def test_e2e(self):
        self.service.create_user(UserCreate(login="new User"))
        assert (
            self.service.get_user(4)
            == User(id=4, login="new User")
        )

        activated_user = self.service.activate_user(2)
        assert activated_user.is_activated is True
