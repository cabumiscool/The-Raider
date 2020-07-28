import re
import math
from typing import Union


def look_for_user_id(user_id_or_mention: Union[int, str]):
    if type(user_id_or_mention) == int:
        if abs(int(math.log10(user_id_or_mention) + 1)) == 18:
            return user_id_or_mention
        else:
            return None
    elif type(user_id_or_mention) == str:
        # TODO create a regex to extract a user id from a mention
        raise NotImplementedError("Mentions not supported yet")
    else:
        return None
