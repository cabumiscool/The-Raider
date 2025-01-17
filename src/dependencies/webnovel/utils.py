import json
from typing import List, Union, Tuple

from fuzzywuzzy import process

SELECTION_SCORE_CUTOFF: int = 3
SELECTION_SCORE_MIN: int = 80


def decode_qi_content(binary_content: bytes) -> dict:
    """Decodes the Qi response into a JSON object"""
    content_str = binary_content.decode()
    return json.loads(content_str)


async def book_string_to_book_id(all_books_ids_names_sub_names_dict: dict, book_string, limit: int = 5, *,
                                 base_score: int = SELECTION_SCORE_MIN, selection_diff: int = SELECTION_SCORE_CUTOFF
                                 ) -> Union[None, List[Tuple[int, int]]]:
    choices_list = [choice for choice in all_books_ids_names_sub_names_dict]
    matches = process.extractBests(book_string, choices_list, limit=limit)

    if len(matches) == 0:
        return None
    if len(matches) == 1 or (matches[0][1] > matches[1][1] + selection_diff and matches[0][1] > base_score):
        return [(all_books_ids_names_sub_names_dict[matches[0][0]], matches[0][1])]
    matched_book_ids_and_score = [(all_books_ids_names_sub_names_dict[match], score) for match, score in matches]
    return matched_book_ids_and_score
