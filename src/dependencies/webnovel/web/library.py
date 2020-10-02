import asyncio
import aiohttp
import typing
from dependencies import qi_classes


main_api_url = "https://www.webnovel.com/apiajax/Library/LibraryAjax"


def parse_library_page(library_page_list: typing.List[dict]):
    pass


async def retrieve_library_page(page_index: int = 1, session: aiohttp.ClientSession = None,
                                account: qi_classes.Account = None) -> (typing.List[dict], bool):
    """Retrieves a page from the library
        :arg page_index is the page number that will be requested from the library
        :arg session receives a session object from aiohttp that already contains the cookies for the respective
        account
        :arg account receives an account object, will be ignored if a session object is given; if a session object is
        not given it will use the account object to generate a request
        :returns a tuple containing a list which containing a dict for every book present in the library page and a
        bool representing if this is the last page on the library
    """


async def add_item_to_library(book_or_comic_id: int, is_book: bool, session: aiohttp.ClientSession = None,
                              account: qi_classes.Account = None) -> bool:
    """Add an item to the library
        :arg book_or_comic_id accepts a book or comic id to add to the library
        :arg is_book is a bool argument that tells the func if the item it is adding is a book or comic
        :arg session receives an aiohttp session object that includes the cookies of the account, if empty will use the
        account arg to generate a request
        :arg account receives an account object to generate a request with it, will be ignored if a session object is
        given

        :returns a bool value representing if the request was completed successfully
    """


async def remove_item_from_library():
    pass

