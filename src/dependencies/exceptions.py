class RaiderBaseException(Exception):
    """
    Base exception for all errors raised by Raider
    """
    MESSAGE = "Raider Base Exception"
    ERROR_CODE = 0

    def get_message(self) -> str:
        return self.MESSAGE

# Error code map:
# 100 : Config Exceptions - config.py
# 200 : Webnovel Exceptions - dependencies/webnovel
# 300 : Mail Agent Exceptions - dependencies/mail_agent
# 900 : Daemon Exceptions - background_process/background_objections.py
