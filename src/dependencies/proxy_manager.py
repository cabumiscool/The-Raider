import aiohttp
import aiohttp_socks


class InvalidIpAddress(Exception):
    """Raised when a given ip address is invalid"""


class Proxy:
    connection_types = {'http': aiohttp_socks.ProxyType.HTTP, 'socks4': aiohttp_socks.ProxyType.SOCKS4,
                        'socks5': aiohttp_socks.ProxyType.SOCKS5}

    def __init__(self, ip: str, port: str, connection_type: str, uptime: int, latency: int, speed: int):
        if isinstance(ip, str):
            ip_parts = ip.split('.')
            if len(ip_parts) == 4:
                for part in ip_parts:
                    try:
                        int(part)
                    except ValueError:
                        raise InvalidIpAddress(f'The Ip address of {ip} is invalid')
            else:
                raise InvalidIpAddress(f'The Ip address of {ip} is invalid')
        else:
            raise ValueError(f"Was expecting an object of type 'str' instead received a type '{type(ip).__name__}'")
        self._ip = ip
        self._port = port
        try:
            self._type = self.connection_types[connection_type.lower()]
        except KeyError:
            raise ValueError(f'Invalid proxy type was input')
        self.uptime = uptime
        self.latency = latency
        self.speed = speed

    def generate_connector(self, **kwargs):
        return aiohttp_socks.ProxyConnector(self._type, self._ip, self._port, **kwargs)


class ProxyManager:
    pass
