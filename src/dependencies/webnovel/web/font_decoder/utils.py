import io
import json
import os
import re
import tempfile
from collections import defaultdict
from io import BytesIO

import bs4
from bs4 import BeautifulSoup

PAT_CSS_ORDER_RULE = re.compile(r"(\w+){order:(\d+);}")
PAT_CSS_ATTR_RULE = re.compile(r"(\._p\w+) (\w+)::(before|after){content:attr\((\w+)\)}")


class DistComparable:
    def __init__(self, items):
        self._items = items

    def __sub__(self, other):
        if not hasattr(other, "_items"):
            raise ValueError("other item doesn't have _items")
        if len(self._items) != len(other._items):
            raise ValueError("Must compare items with same length")

        dist = 0
        for a, b in zip(self._items, other._items):
            dist += abs(a - b)

        return dist

    def __str__(self):
        return str(hash(self._items))


class ContentInfo:
    def __init__(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._tmp_dir = "temps"
        # self.path_font = os.path.join(self._tmp_dir.name, "font.ttf")
        self.path_font = os.path.join(self._tmp_dir, "font.ttf")
        self.content = None
        self.css = None
        self.raw = None
        self._font = None
        self._bytes = None

    def get_font(self):
        # return copy.deepcopy(self._font)
        # return self._bytes
        data = io.BytesIO()
        data.write(self._bytes)
        data.seek(0)
        return data

    @classmethod
    def from_api_data(cls, filename: str):
        with open(filename, "r") as f:
            api_data = json.load(f)

        return cls.from_chapter_info(api_data["data"]["chapterInfo"])

    @classmethod
    def from_page_data(cls, filename: str):
        with open(filename, "r") as f:
            dec_data = json.load(f)

        return cls.from_chapter_info(dec_data["chapterInfo"])

    @classmethod
    def from_chapter_info(cls, chap_info):
        assert chap_info["encryptType"] == 2

        inst = cls()

        if '{"code":' in chap_info["contents"][0]["content"]:
            content = chap_info["contents"][0]["content"].split(" && ", maxsplit=1)[1][:-4]
            content = json.loads(content)["data"]
        else:
            content = chap_info

        inst.raw = content
        inst.content = content["contents"]
        inst.css = content["css"]

        font = BytesIO()
        for x in content["font"]:
            font.write(x.to_bytes(1, "big"))

        bytes_ = font.getbuffer().tobytes()
        inst._bytes = bytes_
        font = BytesIO(bytes_)
        inst._font = BytesIO(bytes_)

        # with open(inst.path_font, "wb") as f:
        #     f.write(font.getbuffer())

        return inst

    @classmethod
    def from_content_info(cls, content_str: str):
        # assert chap_info["encryptType"] == 2

        inst = cls()
        content = content_str.split(" && ", maxsplit=1)[1][:-4]
        content = json.loads(content)["data"]
        # if '{"code":' in chap_info["contents"][0]["content"]:
        #     content = chap_info["contents"][0]["content"].split(" && ", maxsplit=1)[1][:-4]
        #     content = json.loads(content)["data"]
        # else:
        #     content = chap_info

        inst.raw = content
        inst.content = content["contents"]
        inst.css = content["css"]

        font = BytesIO()
        for x in content["font"]:
            font.write(x.to_bytes(1, "big"))

        bytes_ = font.getbuffer().tobytes()
        inst._bytes = bytes_
        font = BytesIO(bytes_)
        inst._font = BytesIO(bytes_)

        # with open(inst.path_font, "wb") as f:
        #     f.write(font.getbuffer())

        return inst

    def _parse_css(self):
        rules = self.css.split(" ", maxsplit=1)[1].split("WN_CHAPTER ")

        order_map = {}
        attr_map = defaultdict(lambda: defaultdict(dict))
        """paragraph class -> word tag -> before/after -> attr name"""

        for rule in rules:
            if match := PAT_CSS_ORDER_RULE.fullmatch(rule):
                order_map[match.group(1)] = int(match.group(2))
            elif match := PAT_CSS_ATTR_RULE.fullmatch(rule):
                attr_map[match.group(1)[1:]][match.group(2)][match.group(3)] = match.group(4)
            # else:
            #     raise ValueError(f"Unhandled css rule: {rule!r}")

        return order_map, attr_map

    def unscramble(self):
        order_map, attr_map = self._parse_css()

        doc = []

        for par_obj in self.content:
            soup = BeautifulSoup(par_obj["content"], "html.parser")

            try:
                assert len(soup.contents) == 1 or type(soup.contents[1]) is bs4.element.NavigableString
            except AssertionError:
                raise AssertionError

            paragraph = soup.contents[0]
            paragraph = soup.contents[0]
            if paragraph.name == "annotations":
                # hope that it isn't word scrambled
                doc.append(str(paragraph))
                continue
            p_tag = paragraph.attrs["class"][0]

            words = [x.extract() for x in paragraph.contents.copy()]
            words = sorted(words, key=lambda x: order_map.get(x.name, 0))

            for word in words:
                if (before := attr_map[p_tag][word.name].get("before", None)) is not None:
                    paragraph.insert(len(paragraph.contents), word.attrs[before])

                paragraph.insert(len(paragraph.contents), word)
                if hasattr(word, "contents") and word.name in order_map:
                    word.replace_with_children()

                if (after := attr_map[p_tag][word.name].get("after", None)) is not None:
                    paragraph.insert(len(paragraph.contents), word.attrs[after])

            paragraph.attrs.clear()
            doc.append(str(paragraph))

        return "\n\n".join(doc)
