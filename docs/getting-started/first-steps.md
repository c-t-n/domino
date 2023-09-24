## Writing your first service

For our first domain, we will create a simple todo list application. We will have a `Todo` entity, and a `TodoService` service that hold all the business logic of our application.

Services in DDD meant to be only business logic and abstractions. They should not be aware of the infrastructure or the framework you are using. Let's build our first service:

```python
from domino.domain import Service

class TodoService(Service):
    def create_todo(self):
        pass

    def retrieve_all_todos(self):
        pass

    def set_todo_as_done(self):
        pass
```

This should be our base of what our application should do: create todos, get the list of todos, and set a todo as done.

## UnitOfWork and Repositories

Services are meant to be initiated with a `UnitOfWork` object. This object is the one that will handle the database connection and the transaction. It will also be used to retrieve the repositories.

The `Service` class holds an `unit_of_work` attribute that we can use to access the `UnitOfWork` object.
When a service is used, it must be initialized with a `UnitOfWork` object.

The `Service` class has a Generic type to take an `UnitOfWork` class. It will be used to type the `unit_of_work` attribute of the `Service` class, that we will see later.

```python
from domino.domain import Service, UnitOfWork

class AbstractTodoUnitOfWork(UnitOfWork):
    pass

class TodoService(Service[AbstractTodoUnitOfWork]):
    def create_todo(self):
        pass

    def retrieve_all_todos(self):
        pass

    def set_todo_as_done(self):
        pass
```

See that we don't use the `unit_of_work` attribute yet. Because we need a contract to manipulate a todo.

`UnitOfWork` is a class that embeds all `AbstractRepository` objects. `AbstractRepository` is an abstract class which link the Service to the models it handles. They are meant to be used by the services to retrieve and persist data, but for now, we just create the interface.

```python
from domino.domain import Service, UnitOfWork, AbstractRepository

class AbstractTodoRepository(AbstractRepository):
    pass

class AbstractTodoUnitOfWork(UnitOfWork):
    todo: AbstractTodoRepository

class TodoService(Service[AbstractTodoUnitOfWork]):
    def create_todo(self):
        pass

    def retrieve_all_todos(self):
        pass

    def set_todo_as_done(self):
        pass
```

## Business Logic

So now we have the framework to build something, let's add our business logic to our service.

```python
from domino.domain import Service, UnitOfWork, AbstractRepository

class AbstractTodoRepository(AbstractRepository):
    def find_by_id(self, todo_id: int) -> dict:
        pass

    def list(self) -> list[dict]:
        pass

    def save(self, data: dict) -> dict:
        pass


class AbstractTodoUnitOfWork(UnitOfWork):
    todo: AbstractTodoRepository

class TodoService(Service[AbstractTodoUnitOfWork]):
    def create_todo(self, data: dict):
        with self.unit_of_work as uow:
            return uow.todo.save(data)

    def retrieve_all_todos(self):
        return self.unit_of_work.todo.list()

    def set_todo_as_done(self, todo_id: int):
        with self.unit_of_work as uow:
            todo = uow.todo.find_by_id(todo_id)
            todo.set_as_done()
            return uow.todo.save(todo)
```

We have now a service that can create todos, get the list of todos, and set a todo as done.

But notice on the `set_todo_as_done` method, we have a `todo` variable that we need to fetch from our repository, then updates it and save it via our TodoRepository.

As written earlier, `UnitOfWork` embed either repositories and transaction logic.
Transactions in the scope of a database, is a way to ensure that all the operations are done, or none of them are. It is a way to ensure data integrity.

`UnitOfWork` classes are meant to be used as context managers.
When the context is entered, the transaction is started. When the context is exited, the transaction is committed. If an exception is raised, the transaction is rollbacked.

We strongly suggest to use transactions in your services, as it is a good practice to ensure data integrity.

It is mandatory for mutation operations, but you can do it without for read operations.

## Entities and DTO

Now that we have our business logic, we need to create our Todo Entity.

```python
from domino.domain import Service, UnitOfWork, AbstractRepository
from domino.domain.models import Entity

class Todo(Entity):
    id: int
    title: str
    done: bool

    def set_as_done(self):
        if self.done:
            raise Exception("Todo already done")
        self.done = True
        return self


class AbstractTodoRepository(AbstractRepository):
    def find_by_id(self, todo_id: int) -> Todo:
        pass

    def list(self) -> list[Todo]:
        pass

    def save(self, data: Todo) -> Todo:
        pass


class AbstractTodoUnitOfWork(UnitOfWork):
    todo: AbstractTodoRepository

class TodoService(Service[AbstractTodoUnitOfWork]):
    def create_todo(self, data: dict):
        with self.unit_of_work as uow:
            return uow.todo.save(data)

    def retrieve_all_todos(self):
        return self.unit_of_work.todo.list()

    def set_todo_as_done(self, todo_id: int):
        with self.unit_of_work as uow:
            todo = uow.todo.find_by_id(todo_id)
            todo.set_as_done()
            return uow.todo.save(todo)
```

Entities are the representation of a business object. They are meant to be used by the services to manipulate data.
As setting as done is a business logic that only targets the todo Entity, we can put it in the Entity class and use it in our service.

Note that unless we call the `.save()` method of the repository, the data is not persisted.

But we have a problem here. Our `TodoService` is meant to be used by an adapter such as a REST API or such, and we don't want to expose our Entity to it.

We need to create a DTO (Data Transfer Object) to expose our data.

```python
from domino.domain import Service, UnitOfWork, AbstractRepository
from domino.domain.models import Entity, DTO

class Todo(Entity):
    id: int
    title: str
    done: bool

    def set_as_done(self):
        if self.done:
            raise Exception("Todo already done")
        self.done = True
        return self

class TodoCreate(DTO):
    title: str


class AbstractTodoRepository(AbstractRepository):
    def find_by_id(self, todo_id: int) -> Todo:
        pass

    def list(self) -> list[Todo]:
        pass

    def create(self, data: TodoCreate) -> Todo:
        pass

    def save(self, data: Todo) -> Todo:
        pass


class AbstractTodoUnitOfWork(UnitOfWork):
    todo: AbstractTodoRepository

class TodoService(Service[AbstractTodoUnitOfWork]):
    def create_todo(self, data: TodoCreate):
        with self.unit_of_work as uow:
            return uow.todo.create(data)

    def retrieve_all_todos(self):
        return self.unit_of_work.todo.list()

    def set_todo_as_done(self, todo_id: int):
        with self.unit_of_work as uow:
            todo = uow.todo.find_by_id(todo_id)
            todo.set_as_done()
            return uow.todo.save(todo)
```

## Putting it all together

Now that we have our business logic, our DTO and our repositories, we can create our concrete implementation of our service.
We took all our file above and put them in a `todo_example` package.

What we want as a first implementation of our repository is to store our data in memory.
We will use a list to store our todos, and a counter to generate the id of our todos.

```python
from domino.exceptions import ItemNotFound
from todo_example.domain import (
    TodoService,
    AbstractTodoUnitOfWork,
    AbstractTodoRepository,
    TodoCreate,
    Todo
)

class InMemoryTodoRepository(AbstractTodoRepository):
    db: list[Todo] = []
    index = 1

    def find_by_id(self, todo_id: int) -> Todo:
        for todo in self.db:
            if todo.id == todo_id:
                return todo
        raise ItemNotFound

    def list(self) -> list[Todo]:
        return db

    def create(self, data: TodoCreate) -> Todo:
        todo = Todo(
            id=self.index,
            title=data.title,
            done=False
        )
        self.db.append(todo)
        self.index += 1
        return todo

    def save(self, data: Todo) -> Todo:
        for i, todo in enumerate(self.db):
            if todo.id == data.id:
                self.db[i] = data
                return data
        raise ItemNotFound

class TodoUnitOfWork(AbstractTodoUnitOfWork):
    todo = InMemoryTodoRepository()

# Now we can use our service
svc = TodoService(TodoUnitOfWork())

# Create a todo
todo = svc.create_todo(TodoCreate(title="My first todo"))

# Get the list of todos
todos = svc.retrieve_all_todos()
# >>> [Todo(id=1, title='Do the dishes', done=False)]

# Set a todo as done
todo = svc.set_todo_as_done(1)
print(todo)
# >>> Todo(id=1, title='Do the dishes', done=True)
```
