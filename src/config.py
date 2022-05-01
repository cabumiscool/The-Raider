from ast import literal_eval
from configparser import ConfigParser

from dependencies.exceptions import RaiderBaseException


class ConfigBaseException(RaiderBaseException):
    """
    Base exception for all errors related to the config file
    """
    MESSAGE = "Config Base Exception"
    ERROR_CODE = 100


class MissingConfiguration(ConfigBaseException):
    """
    Is raised when the config file is missing information
    """
    MESSAGE = "Missing Configuration in ConfigReader file"
    ERROR_CODE = 101

    def __init__(self, missing_section: str, details: str = ''):
        super().__init__(self.MESSAGE)
        self.missing_section = missing_section
        self.details = details

    def __str__(self):
        return f"<{self.__class__.__name__}: MISSING_SECTION={self.missing_section}, DETAILS={self.details} >"


class ConfigNotFound(ConfigBaseException):
    """
    Raised when the config file is empty or just created
    """
    MESSAGE = "ConfigReader file missing or empty"
    ERROR_CODE = 102


class ConfigReader:
    def __read_settings_file(self):
        config = self.config
        config.read('../settings.ini')
        self.__test_settings()

    def __test_settings(self):
        """
        Checks if the config file is missing any values, and if it is, it writes the default values
        to the config file.
        """
        settings_file = self.config
        try:
            database_section = settings_file['database']
        except KeyError:
            self.__write_default_settings_values()
            raise ConfigNotFound
        if database_section['host'] == '' or database_section['password'] == '' or database_section['user'] == '':
            raise MissingConfiguration('database')
        misc_section = settings_file['misc']
        try:
            use_test = literal_eval(misc_section['use-test'])
            if type(use_test) != bool:
                raise MissingConfiguration('use-test', 'The value is not a bool')
        except ValueError:
            raise MissingConfiguration('use-test', 'The value is not a selection of "True" or "False"')
        self.use_test = use_test
        if use_test is False:
            bot_section = settings_file['main bot']
        else:
            bot_section = settings_file['test bot']
        self.bot_section = bot_section
        if bot_section['token'] == '':
            raise MissingConfiguration('token', 'Corresponding Bot Token is missing')

    def __write_default_settings_values(self):
        """
        Writes the default settings to the settings.ini file
        """
        config = self.config
        config['main bot'] = {'token': '', 'prefix': '!', 'description': 'A bot'}
        config['test bot'] = {'token': '', 'prefix': '?', 'description': 'A test bot'}
        config['database'] = {'host': '', 'name': '', 'user': '', 'port': '3306', 'password': '', 'min conns': '1',
                              'max conns': '5'}
        config['misc'] = {'use-test': 'False', 'auto-start-background': 'True'}
        with open('../settings.ini', 'w') as settings_file:
            config.write(settings_file)

    def __load_values_to_attribute(self):
        """
        Loads the values from the config file into the attributes of the class
        """
        config_file = self.config
        bot_section = self.bot_section
        self.bot_token = bot_section['token']
        self.bot_prefix = bot_section['prefix']
        self.bot_description = bot_section['description']
        db_section = config_file['database']
        self.db_host = db_section['host']
        self.db_name = db_section['name']
        self.db_user = db_section['user']
        self.db_password = db_section['password']
        self.db_port: int = literal_eval(db_section['port'])
        self.min_db_conns: int = literal_eval(db_section['min conns'])
        self.max_db_conns: int = literal_eval(db_section['max conns'])

    def __init__(self):
        """
        Reads a config file and loads the values into the class attributes.
        """
        self.bot_section = None  # this might be wrong
        self.config = ConfigParser()
        self.__read_settings_file()
        self.use_test: bool = literal_eval(self.config['misc']['use-test'])
        self.auto_start_background = literal_eval(self.config['misc']['auto-start-background'])
        self.bot_token = ''
        self.bot_description = ''
        self.bot_prefix = ''
        self.db_host = ''
        self.db_name = ''
        self.db_user = ''
        self.db_port = 5342
        self.db_password = ''
        self.min_db_conns = 0
        self.max_db_conns = 0
        self.__load_values_to_attribute()
