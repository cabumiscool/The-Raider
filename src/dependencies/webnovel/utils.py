import json
from typing import List, Union, Tuple, TYPE_CHECKING

from fuzzywuzzy import process

from dependencies.database import Database

if TYPE_CHECKING:
    from dependencies.webnovel.classes import Book

SELECTION_SCORE_DIFF: int = 3
SELECTION_SCORE: int = 80


def decode_qi_content(binary_content: bytes) -> dict:
    """Decodes the Qi response into a JSON object"""
    content_str = binary_content.decode()
    return json.loads(content_str)


async def book_string_matcher(database: Database, book_string, limit: int = 5, *, base_score: int = SELECTION_SCORE,
                              selection_diff: int = SELECTION_SCORE_DIFF) -> Union[None, List[Tuple['Book', int]]]:
    all_valid_book_strings = await database.get_all_books_ids_names_sub_names_dict()
    matches = process.extractBests(book_string, all_valid_book_strings, limit=limit)

    if len(matches) == 0:
        return None
    if len(matches) == 1 or (matches[0][1] > matches[1][1] + selection_diff and matches[0][1] > base_score):
        return matches[:1]
    return matches
