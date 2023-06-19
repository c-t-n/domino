from domino.domain.services import Service
from domino.domain.uow import AbstractUnitOfWork
from domino.domain.repositories import AbstractCRUDRepository
from domino.domain.repositories.mocks import MockedKVRepository
from domino.domain.models.pydantic import DomainModel


class UserNotFound(Exception):
    pass


class UserAlreadyActivated(Exception):
    pass


class TestUserModel(DomainModel):
    """BaseUser model. Used as base for doc representation"""
    id: int
    login: str
    is_activated: bool = False


class TestUserCreateModel(DomainModel):
    """CreateUser model. Used for User Creation"""
    login: str


class TestUserUpdateModel(DomainModel):
    """UpdateUser model. Used for User Update"""
    login: str | None = None
    is_activated: bool | None = None


class AbstractTestUserRepository(
    AbstractCRUDRepository[
        TestUserModel,
        TestUserCreateModel,
        TestUserUpdateModel
    ]
):
    """Full CRUD Repository"""
    pass


class MockedKVTestUserRepository(
    MockedKVRepository[
        TestUserModel,
        TestUserCreateModel,
        TestUserUpdateModel
    ]
):
    """Full CRUD Repository, as Mocked KeyValue Repo"""
    primary_key_property = "id"
    base_model = TestUserModel


class TestUserUnitOfWork(AbstractUnitOfWork):
    test_user_repository: AbstractTestUserRepository


class TestUserService(Service[TestUserUnitOfWork]):
    def get_user(self, user_id: int) -> TestUserModel:
        with self.unit_of_work as uow:
            user = uow.test_user_repository.get(user_id)

        if user is None:
            raise UserNotFound

        return user

    def list_users(self) -> list[TestUserModel]:
        with self.unit_of_work as uow:
            return uow.test_user_repository.list({})[:20]

    def create_user(self, data: TestUserCreateModel) -> TestUserModel:
        with self.unit_of_work as uow:
            return uow.test_user_repository.create(data)

    def update_user(self, user_id: int, data: TestUserUpdateModel) -> TestUserModel:
        with self.unit_of_work as uow:
            return uow.test_user_repository.update(user_id, data)

    def delete_user(self, user_id: int) -> None:
        with self.unit_of_work as uow:
            return uow.test_user_repository.delete(user_id)

    def activate_user(self, user_id: int) -> TestUserModel:
        with self.unit_of_work as uow:
            user = self.get_user(user_id)
            if user.is_activated:
                raise UserAlreadyActivated

            user = uow.test_user_repository.update(
                user_id,
                TestUserUpdateModel(is_activated=True)
            )

        return user

#################
# Tests         #
#################


class TestEndToEnd:
    def setup_method(self):
        self.unit_of_work = TestUserUnitOfWork(
            test_user_repository=MockedKVTestUserRepository
        )

        self.service = TestUserService(unit_of_work=self.unit_of_work)

        self.service.create_user(TestUserCreateModel(login="hello"))
        self.service.create_user(TestUserCreateModel(login="world"))
        self.service.create_user(TestUserCreateModel(login="wavery"))

    def test_e2e(self):
        self.service.create_user(TestUserCreateModel(login="new User"))
        assert (
            self.service.get_user(4)
            == TestUserModel(id=4, login="new User")
        )

        activated_user = self.service.activate_user(2)
        assert activated_user.is_activated is True
