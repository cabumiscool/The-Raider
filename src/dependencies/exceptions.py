class RaiderBaseException(Exception):
    """
    Base exception for all errors raised by Raider
    """
    MESSAGE = "Raider Base Exception"
    ERROR_CODE = 0

    def get_message(self) -> str:
        return self.MESSAGE