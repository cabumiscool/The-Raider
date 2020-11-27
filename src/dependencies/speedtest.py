import timeit
import aiohttp
import datetime
import gzip
import sys
import math
import typing
import os
import platform
import asyncio

from urllib.parse import urlparse
from io import BytesIO, StringIO
import io

import xml
import xml.etree.ElementTree as ET
etree_iter = ET.Element.iter

module_version = '2.1.2'

# def printer(string, quiet=False, debug=False, error=False, **kwargs):
#     """Helper function print a string with various features"""
#
#     if debug and not DEBUG:
#         return
#
#     if debug:
#         if sys.stdout.isatty():
#             out = '\033[1;30mDEBUG: %s\033[0m' % string
#         else:
#             out = 'DEBUG: %s' % string
#     else:
#         out = string
#
#     if error:
#         kwargs['file'] = sys.stderr
#
#     if not quiet:
#         print_(out, **kwargs)

# HTTP_ERRORS = (
#         (HTTPError, URLError, socket.error, ssl.SSLError, BadStatusLine, CERT_ERROR)

class SpeedtestException(Exception):
    """Base exception for this module"""


class SpeedtestCLIError(SpeedtestException):
    """Generic exception for raising errors during CLI operation"""


class SpeedtestHTTPError(SpeedtestException):
    """Base HTTP exception for this module"""


class SpeedtestConfigError(SpeedtestException):
    """Configuration XML is invalid"""


class SpeedtestServersError(SpeedtestException):
    """Servers XML is invalid"""


class ConfigRetrievalError(SpeedtestHTTPError):
    """Could not retrieve config.php"""


class ServersRetrievalError(SpeedtestHTTPError):
    """Could not retrieve speedtest-servers.php"""


class InvalidServerIDType(SpeedtestException):
    """Server ID used for filtering was not an integer"""


class NoMatchedServers(SpeedtestException):
    """No servers matched when filtering"""


class SpeedtestMiniConnectFailure(SpeedtestException):
    """Could not connect to the provided speedtest mini server"""


class InvalidSpeedtestMiniServer(SpeedtestException):
    """Server provided as a speedtest mini server does not actually appear
    to be a speedtest mini server
    """


class ShareResultsConnectFailure(SpeedtestException):
    """Could not connect to speedtest.net API to POST results"""


class ShareResultsSubmitFailure(SpeedtestException):
    """Unable to successfully POST results to speedtest.net API after
    connection
    """


class SpeedtestUploadTimeout(SpeedtestException):
    """testlength configuration reached during upload
    Used to ensure the upload halts when no additional data should be sent
    """


class SpeedtestBestServerFailure(SpeedtestException):
    """Unable to determine best server"""


class SpeedtestMissingBestServer(SpeedtestException):
    """get_best_server not called or not able to determine best server"""


def do_nothing(*args, **kwargs):
    pass


def build_user_agent():
    """Build a Mozilla/5.0 compatible User-Agent string"""

    ua_tuple = (
        'Mozilla/5.0',
        '(%s; U; %s; en-us)' % (platform.platform(),
                                platform.architecture()[0]),
        'Python/%s' % platform.python_version(),
        '(KHTML, like Gecko)',
        'speedtest-cli/%s' % module_version
    )
    user_agent = ' '.join(ua_tuple)
    # printer('User-Agent: %s' % user_agent, debug=True)
    return user_agent


def get_exception():
    """Helper function to work with py2.4-py3 for getting the current
    exception in a try/except block
    """
    return sys.exc_info()[1]


class FakeShutdownEvent(object):
    """Class to fake a threading.Event.isSet so that users of this module
    are not required to register their own threading.Event()
    """

    @staticmethod
    def isSet():
        "Dummy method to always return false"""
        return False


class HTTPUploaderData(io.IOBase):
    """File like object to improve cutting off the upload once the timeout
    has been reached
    """

    def __init__(self, length, start, timeout, shutdown_event=None):
        self.length = length
        self.start = start
        self.timeout = timeout

        if shutdown_event:
            self._shutdown_event = shutdown_event
        else:
            self._shutdown_event = FakeShutdownEvent()

        self._data = None

        self.total = [0]

    def pre_allocate(self):
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        multiplier = int(round(int(self.length) / 36.0))
        IO = BytesIO or StringIO
        try:
            self._data = IO(
                ('content1=%s' %
                 (chars * multiplier)[0:int(self.length) - 9]
                 ).encode()
            )
        except MemoryError:
            raise SpeedtestCLIError(
                'Insufficient memory to pre-allocate upload data. Please '
                'use --no-pre-allocate'
            )

    @property
    def data(self):
        if not self._data:
            self.pre_allocate()
        return self._data

    def read(self, n=10240):
        default = timeit.default_timer()
        first_time = timeit.default_timer() - self.start
        if ((timeit.default_timer() - self.start) <= self.timeout and
                not self._shutdown_event.isSet()):
            chunk = self.data.read(n)
            self.total.append(len(chunk))
            return chunk
        else:
            raise SpeedtestUploadTimeout()

    def __len__(self):
        return self.length


def distance(origin, destination):
    """Determine distance between 2 sets of [lat,lon] in km"""

    lat1, lon1 = origin
    lat2, lon2 = destination
    radius = 6371  # km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon / 2) *
         math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = radius * c

    return d


def build_request(url, data=None, headers=None, bump='0', secure=False, timeout: int = 30):
    """Build a urllib2 request object

    This function automatically adds a User-Agent header to all requests

    """

    if not headers:
        headers = {}

    if url[0] == ':':
        scheme = ('http', 'https')[bool(secure)]
        schemed_url = '%s%s' % (scheme, url)
    else:
        schemed_url = url

    if '?' in url:
        delim = '&'
    else:
        delim = '?'

    # WHO YOU GONNA CALL? CACHE BUSTERS!
    final_url = '%s%sx=%s.%s' % (schemed_url, delim,
                                 int(timeit.time.time() * 1000),
                                 bump)

    headers.update({
        'Cache-Control': 'no-cache',
    })

    # printer('%s %s' % (('GET', 'POST')[bool(data)], final_url),
    #         debug=True)

    request_object = aiohttp.request(('GET', 'POST')[bool(data)], final_url, data=data, headers=headers,
                                     timeout=aiohttp.ClientTimeout(timeout))
    # return Request(final_url, data=data, headers=headers)
    return request_object


async def await_request(request, limited_read: int = 0) -> typing.Tuple[aiohttp.ClientResponse, bytes]:
    """returns a resp obj and a bin_content"""
    async with request as resp:
        resp: aiohttp.ClientResponse
        if limited_read == 0:
            response_bin = await resp.read()
            return resp, response_bin
        else:
            # response_partial_bin = await resp.content.read(limited_read)
            # return resp, response_partial_bin
            content = b''
            try:
                while True:
                    read = await resp.content.read(limited_read)
                    content = read + content
                    if not read:
                        break
            except asyncio.TimeoutError:
                pass
            finally:
                return resp, content


async def catch_request(request, limited_read: int = 0):
    """Helper function to catch common exceptions encountered when
    establishing a connection with a HTTP/HTTPS request

    if successful returns a tuple as the first object in the return which contains the bin_content followed by the
    resp obj
    """

    try:
        response, binary_content = await await_request(request, limited_read=limited_read)
        # async with request as resp:
        #     binary_content = await resp.read()
        #     response = resp
        # if request.get_full_url() != uh.geturl():
        #     # printer('Redirected to %s' % uh.geturl(), debug=True)
        #     pass
        return (binary_content, response), False
    # except HTTP_ERRORS:
    except Exception:
        # TODO check exceptions
        e = get_exception()
        return (None, None), e



class SpeedtestResults(object):
    """Class for holding the results of a speedtest, including:

    Download speed
    Upload speed
    Ping/Latency to test server
    Data about server that the test was run against

    Additionally this class can return a result data as a dictionary or CSV,
    as well as submit a POST of the result data to the speedtest.net API
    to get a share results image link.
    """

    def __init__(self, download=0, upload=0, ping=0, server=None, client=None,
                 opener=None, secure=False):
        self.download = download
        self.upload = upload
        self.ping = ping
        if server is None:
            self.server = {}
        else:
            self.server = server
        self.client = client or {}

        self._share = None
        self.timestamp = '%sZ' % datetime.datetime.utcnow().isoformat()
        self.bytes_received = 0
        self.bytes_sent = 0

        # if opener:
        #     self._opener = opener
        # else:
        #     self._opener = build_opener()

        self._secure = secure

    def __repr__(self):
        return repr(self.dict())

    def dict(self):
        """Return dictionary of result data"""

        return {
            'download': self.download,
            'upload': self.upload,
            'ping': self.ping,
            'server': self.server,
            'timestamp': self.timestamp,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'share': self._share,
            'client': self.client,
        }


class Speedtest(object):
    """Class for performing standard speedtest.net testing operations"""

    def __init__(self, config=None, source_address=None, timeout=10,
                 secure=False, shutdown_event=None, proxy_obj=None):
        self.config = {}

        self._source_address = source_address
        self._timeout = timeout
        # self._opener = build_opener(source_address, timeout)

        self._secure = secure

        if shutdown_event:
            self._shutdown_event = shutdown_event
        else:
            self._shutdown_event = FakeShutdownEvent()

        if proxy_obj is not None:
            self.proxy = proxy_obj
            self.proxy_connector = aiohttp.TCPConnector(enable_cleanup_closed=True)
        else:
            self.proxy = None
            self.proxy_connector = aiohttp.TCPConnector(enable_cleanup_closed=True)

        if config is not None:
            self.config.update(config)

        self.servers = {}
        self.closest = []
        self._best = {}
        self.results = None

    async def async_init(self):
        await self.get_config()
        self.results = SpeedtestResults(
            client=self.config['client'],
            # opener=self._opener,
            secure=self._secure,
        )
        await self.get_config()
        await self.get_servers()
        await self.get_best_server()


    @property
    def best(self):
        if not self._best:
            self.get_best_server()
        return self._best

    async def get_config(self):
        """Download the speedtest.net configuration and return only the data
        we are interested in
        """

        headers = {}
        if gzip:
            headers['Accept-Encoding'] = 'gzip'
        request = build_request('://www.speedtest.net/speedtest-config.php',
                                headers=headers, secure=self._secure)
        response_tuple, e = await catch_request(request)
        bin_content, response_obj = response_tuple
        if e:
            raise ConfigRetrievalError(e)
        # configxml_list = []
        #
        # stream = get_response_stream(uh)
        #
        # while 1:
        #     try:
        #         configxml_list.append(stream.read(1024))
        #     except (OSError, EOFError):
        #         raise ConfigRetrievalError(get_exception())
        #     if len(configxml_list[-1]) == 0:
        #         break
        # stream.close()
        # uh.close()

        if int(response_tuple[1].status) != 200:
            return None

        # configxml = ''.encode().join(configxml_list)
        configxml = bin_content
        # printer('Config XML:\n%s' % configxml, debug=True)

        try:
            try:
                root = ET.fromstring(configxml)
            except ET.ParseError:
                e = get_exception()
                raise SpeedtestConfigError(
                    'Malformed speedtest.net configuration: %s' % e
                )
            server_config = root.find('server-config').attrib
            download = root.find('download').attrib
            upload = root.find('upload').attrib
            # times = root.find('times').attrib
            client = root.find('client').attrib

        # except AttributeError:
        #     try:
        #         root = DOM.parseString(configxml)
        #     except ExpatError:
        #         e = get_exception()
        #         raise SpeedtestConfigError(
        #             'Malformed speedtest.net configuration: %s' % e
        #         )
        #     server_config = get_attributes_by_tag_name(root, 'server-config')
        #     download = get_attributes_by_tag_name(root, 'download')
        #     upload = get_attributes_by_tag_name(root, 'upload')
        #     # times = get_attributes_by_tag_name(root, 'times')
        #     client = get_attributes_by_tag_name(root, 'client')
        except Exception:
            raise Exception('the code upstairs might be important')

        ignore_servers = list(
            map(int, server_config['ignoreids'].split(','))
        )

        ratio = int(upload['ratio'])
        upload_max = int(upload['maxchunkcount'])
        up_sizes = [32768, 65536, 131072, 262144, 524288, 1048576, 7340032]
        sizes = {
            'upload': up_sizes[ratio - 1:],
            'download': [350, 500, 750, 1000, 1500, 2000, 2500,
                         3000, 3500, 4000]
        }

        size_count = len(sizes['upload'])

        upload_count = int(math.ceil(upload_max / size_count))

        counts = {
            'upload': upload_count,
            'download': int(download['threadsperurl'])
        }

        threads = {
            'upload': int(upload['threads']),
            'download': int(server_config['threadcount']) * 2
        }

        length = {
            'upload': int(upload['testlength']),
            'download': int(download['testlength'])
        }

        self.config.update({
            'client': client,
            'ignore_servers': ignore_servers,
            'sizes': sizes,
            'counts': counts,
            'threads': threads,
            'length': length,
            'upload_max': upload_count * size_count
        })

        try:
            self.lat_lon = (float(client['lat']), float(client['lon']))
        except ValueError:
            raise SpeedtestConfigError(
                'Unknown location: lat=%r lon=%r' %
                (client.get('lat'), client.get('lon'))
            )

        # printer('Config:\n%r' % self.config, debug=True)

        return self.config

    async def get_servers(self, servers=None, exclude=None):
        """Retrieve a the list of speedtest.net servers, optionally filtered
        to servers matching those specified in the ``servers`` argument
        """
        if servers is None:
            servers = []

        if exclude is None:
            exclude = []

        self.servers.clear()

        for server_list in (servers, exclude):
            for i, s in enumerate(server_list):
                try:
                    server_list[i] = int(s)
                except ValueError:
                    raise InvalidServerIDType(
                        '%s is an invalid server type, must be int' % s
                    )

        urls = [
            '://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            '://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php',
        ]

        headers = {}
        if gzip:
            headers['Accept-Encoding'] = 'gzip'

        errors = []
        for url in urls:
            try:
                request = build_request(
                    '%s?threads=%s' % (url,
                                       self.config['threads']['download']),
                    headers=headers,
                    secure=self._secure
                )
                response_tuple, e = await catch_request(request)
                response_binary_content, response_obj = response_tuple
                if e:
                    errors.append('%s' % e)
                    raise ServersRetrievalError()

                # stream = get_response_stream(uh)

                # serversxml_list = []
                # while 1:
                #     try:
                #         serversxml_list.append(stream.read(1024))
                #     except (OSError, EOFError):
                #         raise ServersRetrievalError(get_exception())
                #     if len(serversxml_list[-1]) == 0:
                #         break
                #
                # stream.close()
                # uh.close()

                if int(response_obj.status) != 200:
                    raise ServersRetrievalError()

                # serversxml = ''.encode().join(serversxml_list)
                serversxml = response_binary_content
                # printer('Servers XML:\n%s' % serversxml, debug=True)

                try:
                    try:
                        try:
                            root = ET.fromstring(serversxml)
                        except ET.ParseError:
                            e = get_exception()
                            raise SpeedtestServersError(
                                'Malformed speedtest.net server list: %s' % e
                            )
                        elements = etree_iter(root, 'server')
                    # except AttributeError:
                    #     try:
                    #         root = DOM.parseString(serversxml)
                    #     except ExpatError:
                    #         e = get_exception()
                    #         raise SpeedtestServersError(
                    #             'Malformed speedtest.net server list: %s' % e
                    #         )
                    #     elements = root.getElementsByTagName('server')
                    except Exception:
                        raise Exception('Might be needed the upstairs code')
                except (SyntaxError, xml.parsers.expat.ExpatError):
                    raise ServersRetrievalError()

                for server in elements:
                    try:
                        attrib = server.attrib
                    except AttributeError:
                        attrib = dict(list(server.attributes.items()))

                    if servers and int(attrib.get('id')) not in servers:
                        continue

                    if (int(attrib.get('id')) in self.config['ignore_servers']
                            or int(attrib.get('id')) in exclude):
                        continue

                    try:
                        d = distance(self.lat_lon,
                                     (float(attrib.get('lat')),
                                      float(attrib.get('lon'))))
                    except Exception:
                        continue

                    attrib['d'] = d

                    try:
                        self.servers[d].append(attrib)
                    except KeyError:
                        self.servers[d] = [attrib]

                break

            except ServersRetrievalError:
                continue

        if (servers or exclude) and not self.servers:
            raise NoMatchedServers()

        return self.servers

    # def set_mini_server(self, server):
    #     """Instead of querying for a list of servers, set a link to a
    #     speedtest mini server
    #     """
    #
    #     urlparts = urlparse(server)
    #
    #     name, ext = os.path.splitext(urlparts[2])
    #     if ext:
    #         url = os.path.dirname(server)
    #     else:
    #         url = server
    #
    #     request = build_request(url)
    #     response_tuple, e = catch_request(request)
    #     response_bin_content, response_obj = response_tuple
    #     if e:
    #         raise SpeedtestMiniConnectFailure('Failed to connect to %s' %
    #                                           server)
    #     else:
    #         text = response_bin_content.decode()
    #
    #     extension = re.findall('upload_?[Ee]xtension: "([^"]+)"',
    #                            text.decode())
    #     if not extension:
    #         for ext in ['php', 'asp', 'aspx', 'jsp']:
    #             try:
    #                 f = self._opener.open(
    #                     '%s/speedtest/upload.%s' % (url, ext)
    #                 )
    #             except Exception:
    #                 pass
    #             else:
    #                 data = f.read().strip().decode()
    #                 if (f.code == 200 and
    #                         len(data.splitlines()) == 1 and
    #                         re.match('size=[0-9]', data)):
    #                     extension = [ext]
    #                     break
    #     if not urlparts or not extension:
    #         raise InvalidSpeedtestMiniServer('Invalid Speedtest Mini Server: '
    #                                          '%s' % server)
    #
    #     self.servers = [{
    #         'sponsor': 'Speedtest Mini',
    #         'name': urlparts[1],
    #         'd': 0,
    #         'url': '%s/speedtest/upload.%s' % (url.rstrip('/'), extension[0]),
    #         'latency': 0,
    #         'id': 0
    #     }]
    #
    #     return self.servers

    def get_closest_servers(self, limit=5):
        """Limit servers to the closest speedtest.net servers based on
        geographic distance
        """

        if not self.servers:
            self.get_servers()

        for d in sorted(self.servers.keys()):
            for s in self.servers[d]:
                self.closest.append(s)
                if len(self.closest) == limit:
                    break
            else:
                continue
            break

        # printer('Closest Servers:\n%r' % self.closest, debug=True)
        return self.closest

    async def get_best_server(self, servers=None):
        """Perform a speedtest.net "ping" to determine which speedtest.net
        server has the lowest latency
        """

        if not servers:
            if not self.closest:
                servers = self.get_closest_servers()
            servers = self.closest

        if self._source_address:
            source_address_tuple = (self._source_address, 0)
        else:
            source_address_tuple = None

        user_agent = build_user_agent()

        results = {}
        for server in servers:
            cum = []
            url = os.path.dirname(server['url'])
            stamp = int(timeit.time.time() * 1000)
            latency_url = '%s/latency.txt?x=%s' % (url, stamp)
            for i in range(0, 3):
                # this_latency_url = '%s.%s' % (latency_url, i)
                # printer('%s %s' % ('GET', this_latency_url),
                #         debug=True)
                urlparts = urlparse(latency_url)
                try:
                    # if urlparts[0] == 'https':
                    #     h = SpeedtestHTTPSConnection(
                    #         urlparts[1],
                    #         source_address=source_address_tuple
                    #     )
                    # else:
                    #     h = SpeedtestHTTPConnection(
                    #         urlparts[1],
                    #         source_address=source_address_tuple
                    #     )
                    headers = {'User-Agent': user_agent}
                    path = '%s?%s' % (urlparts[2], urlparts[4])
                    start = timeit.default_timer()

                    #  Tends to fail when used with asyncio.run() outside of an async def
                    async with aiohttp.request('GET', latency_url, connector=self.proxy_connector,
                                               headers=headers) as resp:
                        response_bin_content = await resp.read()
                        response_code = resp.status
                    # h.request("GET", path, headers=headers)
                    # r = h.getresponse()
                    total = (timeit.default_timer() - start)
                except Exception:
                    # except HTTP_ERRORS:
                    # TODO look for exceptions and define them
                    e = get_exception()
                    print(f'There was an error {e}')
                    # printer('ERROR: %r' % e, debug=True)
                    cum.append(3600)
                    raise e
                    continue

                # text = r.read(9)
                text = response_bin_content[0:9]
                if response_code == 200 and text == 'test=test'.encode():
                    cum.append(total)
                else:
                    cum.append(3600)
                # h.close()

            avg = round((sum(cum) / 6) * 1000.0, 3)
            results[avg] = server

        try:
            fastest = sorted(results.keys())[0]
        except IndexError:
            raise SpeedtestBestServerFailure('Unable to connect to servers to '
                                             'test latency.')
        best = results[fastest]
        best['latency'] = fastest

        self.results.ping = fastest
        self.results.server = best

        self._best.update(best)
        # printer('Best Server:\n%r' % best, debug=True)
        return best

    async def download(self, callback=do_nothing, threads=None):
        """Test download speed against speedtest.net

        A ``threads`` value of ``None`` will fall back to those dictated
        by the speedtest.net configuration
        """

        urls = []
        for size in self.config['sizes']['download']:
            for _ in range(0, self.config['counts']['download']):
                urls.append('%s/random%sx%s.jpg' %
                            (os.path.dirname(self.best['url']), size, size))

        request_count = len(urls)
        requests = []
        for i, url in enumerate(urls):
            requests.append(
                build_request(url, bump=i, secure=self._secure, timeout=self.config['length']['download'])
            )

        max_threads = threads or self.config['threads']['download']
        in_flight = {'threads': 0}
        # await resp.content.read(10240)

        # def producer(q, requests, request_count):
        #     for i, request in enumerate(requests):
        #         thread = HTTPDownloader(
        #             i,
        #             request,
        #             start,
        #             self.config['length']['download'],
        #             opener=self._opener,
        #             shutdown_event=self._shutdown_event
        #         )
        #         while in_flight['threads'] >= max_threads:
        #             timeit.time.sleep(0.001)
        #         thread.start()
        #         q.put(thread, True)
        #         in_flight['threads'] += 1
        #         callback(i, request_count, start=True)

        finished = []

        async def consumer():
            results = await asyncio.gather(*[await_request(request, 10240) for request in requests])
            result_numbers = [len(result[1]) for result in results]
            finished.append(sum(result_numbers))
            # for request in requests:
            #     response, response_bin = await await_request(request, 10240)
            #     part1 = len(response_bin)
            #     part2 = sum(part1)
            #     finished.append(sum(len(response_bin)))

        # def consumer_(q, request_count):
        #     _is_alive = thread_is_alive
        #     while len(finished) < request_count:
        #         thread = q.get(True)
        #         while _is_alive(thread):
        #             thread.join(timeout=0.001)
        #         in_flight['threads'] -= 1
        #         finished.append(sum(thread.result))
        #         callback(thread.i, request_count, end=True)

        # q = Queue(max_threads)
        # prod_thread = threading.Thread(target=producer,
        #                                args=(q, requests, request_count))
        # cons_thread = threading.Thread(target=consumer,
        #                                args=(q, request_count))
        start = timeit.default_timer()
        # prod_thread.start()
        # cons_thread.start()
        # _is_alive = thread_is_alive
        # while _is_alive(prod_thread):
        #     prod_thread.join(timeout=0.001)
        # while _is_alive(cons_thread):
        #     cons_thread.join(timeout=0.001)
        await consumer()
        stop = timeit.default_timer()
        self.results.bytes_received = sum(finished)
        self.results.download = (
            (self.results.bytes_received / (stop - start)) * 8.0
        )
        if self.results.download > 100000:
            self.config['threads']['upload'] = 8
        return self.results.download

    async def upload(self, callback=do_nothing, pre_allocate=True, threads=None):
        """Test upload speed against speedtest.net

        A ``threads`` value of ``None`` will fall back to those dictated
        by the speedtest.net configuration
        """

        sizes = []

        for size in self.config['sizes']['upload']:
            for _ in range(0, self.config['counts']['upload']):
                sizes.append(size)

        # request_count = len(sizes)
        request_count = self.config['upload_max']

        requests = []
        for i, size in enumerate(sizes):
            # We set ``0`` for ``start`` and handle setting the actual
            # ``start`` in ``HTTPUploader`` to get better measurements
            data = HTTPUploaderData(
                size,
                timeit.default_timer(),
                self.config['length']['upload'],
                shutdown_event=self._shutdown_event
            )
            if pre_allocate:
                data.pre_allocate()

            headers = {'Content-length': str(size)}
            requests.append(
                (
                    build_request(self.best['url'], data, secure=self._secure,
                                  headers=headers),
                    size,
                    data
                )
            )
            # async with requests[0][0] as resp:
            #     print(resp)

        # max_threads = threads or self.config['threads']['upload']
        # in_flight = {'threads': 0}

        # def producer(q, requests, request_count):
        #     for i, request in enumerate(requests[:request_count]):
        #         thread = HTTPUploader(
        #             i,
        #             request[0],
        #             start,
        #             request[1],
        #             self.config['length']['upload'],
        #             opener=self._opener,
        #             shutdown_event=self._shutdown_event
        #         )
        #         while in_flight['threads'] >= max_threads:
        #             timeit.time.sleep(0.001)
        #         thread.start()
        #         q.put(thread, True)
        #         in_flight['threads'] += 1
        #         callback(i, request_count, start=True)

        finished = []

        async def consumer():
            requests_only = [catch_request(request) for request, data_size, data_object in requests]
            data_only = [data_object for request, data_size, data_object in requests]
            await asyncio.gather(*requests_only)
            for data_obj in data_only:
                finished.append(sum(data_obj.total))
        # def consumer(q, request_count):
        #     _is_alive = thread_is_alive
        #     while len(finished) < request_count:
        #         thread = q.get(True)
        #         while _is_alive(thread):
        #             thread.join(timeout=0.001)
        #         in_flight['threads'] -= 1
        #         finished.append(thread.result)
        #         callback(thread.i, request_count, end=True)

        # q = Queue(threads or self.config['threads']['upload'])
        # prod_thread = threading.Thread(target=producer,
        #                                args=(q, requests, request_count))
        # cons_thread = threading.Thread(target=consumer,
        #                                args=(q, request_count))
        start = timeit.default_timer()
        # prod_thread.start()
        # cons_thread.start()
        # _is_alive = thread_is_alive
        # while _is_alive(prod_thread):
        #     prod_thread.join(timeout=0.1)
        # while _is_alive(cons_thread):
        #     cons_thread.join(timeout=0.1)
        await consumer()

        stop = timeit.default_timer()
        self.results.bytes_sent = sum(finished)
        self.results.upload = (
            (self.results.bytes_sent / (stop - start)) * 8.0
        )
        return self.results.upload

    async def test_speeds(self):
        await self.download()
        await self.upload()


async def shell():
    """Run the full speedtest.net test"""

    # printer('Retrieving speedtest.net configuration...', quiet)
    try:
        speedtest = Speedtest()
        await speedtest.async_init()
    except Exception:
        raise Exception('Unknown')
    # except (ConfigRetrievalError,) + HTTP_ERRORS:
    #     printer('Cannot retrieve speedtest configuration', error=True)
    #     raise SpeedtestCLIError(get_exception())

    # if args.list:
    #     try:
    #         speedtest.get_servers()
    #     except (ServersRetrievalError,) + HTTP_ERRORS:
    #         printer('Cannot retrieve speedtest server list', error=True)
    #         raise SpeedtestCLIError(get_exception())
    #
    #     for _, servers in sorted(speedtest.servers.items()):
    #         for server in servers:
    #             line = ('%(id)5s) %(sponsor)s (%(name)s, %(country)s) '
    #                     '[%(d)0.2f km]' % server)
    #             try:
    #                 printer(line)
    #             except IOError:
    #                 e = get_exception()
    #                 if e.errno != errno.EPIPE:
    #                     raise
    #     sys.exit(0)

    # printer('Testing from %(isp)s (%(ip)s)...' % speedtest.config['client'],
    #         quiet)


    # printer('Retrieving speedtest.net server list...', quiet)
    try:
        await speedtest.get_servers()
    except NoMatchedServers:
        raise Exception('Unknown')
    except (ServersRetrievalError,):  # + HTTP_ERRORS:
        # printer('Cannot retrieve speedtest server list', error=True)
        raise SpeedtestCLIError(get_exception())
    except InvalidServerIDType:
        raise Exception('Unknown')
        # raise SpeedtestCLIError(
        #     '%s is an invalid server type, must '
        #     'be an int' % ', '.join('%s' % s for s in args.server)
        # )

    # if args.server and len(args.server) == 1:
    #     printer('Retrieving information for the selected server...', quiet)
    # else:
    #     printer('Selecting best server based on ping...', quiet)
    await speedtest.get_best_server()


    results = speedtest.results

    # printer('Hosted by %(sponsor)s (%(name)s) [%(d)0.2f km]: '
    #         '%(latency)s ms' % results.server, quiet)

    # if args.download:
    print('Testing download speed', end='\n')
    await speedtest.download()
    print('Download: %0.2f M%s/s' % ((results.download / 1000.0 / 1000.0) / 1, 'bit'))
    # else:
    #     printer('Skipping download test', quiet)

    print('Testing upload speed', end='\n')
    await speedtest.upload()
    print('Upload: %0.2f M%s/s' %((results.upload / 1000.0 / 1000.0) / 1, 'bit'))

    print('Results:\n%r' % results.dict())

    # if not args.simple and args.share:
    #     results.share()

    print('Ping: %s ms\nDownload: %0.2f M%s/s\nUpload: %0.2f M%s/s' %(results.ping,(results.download / 1000.0 / 1000.0)
                                                                      / 1, 'bit',(results.upload / 1000.0 / 1000.0) / 1,
                                                                      'bit'))
    # elif args.csv:
    #     printer(results.csv(delimiter=args.csv_delimiter))
    # elif args.json:
    #     printer(results.json())

    # if args.share and not machine_format:
    #     printer('Share results: %s' % results.share())


if __name__ == '__main__':
    asyncio.run(shell())