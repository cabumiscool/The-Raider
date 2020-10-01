import typing


class BaseService:
    """The base class from where all the services will inherit"""
    def __init__(self, name: str = None):
        if name is None:
            self.name = self.__class__.__name__
        else:
            self.name = name

    def add_to_queue(self, *input_data):
        pass

    def retrieve_completed_cache(self) -> typing.Iterable:
        pass
