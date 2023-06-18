import logging

from abc import ABC

class DominoBaseClass(ABC):

    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)