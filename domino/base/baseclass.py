import logging


class DominoBaseClass:
    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
