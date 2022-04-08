import abc
import io
import json
import os
from abc import ABC
from typing import Dict, List, Union

import imagehash
from PIL import ImageFont, Image, ImageDraw
from fontTools import ttLib

from .utils import DistComparable


class DecoderBase(ABC):
    SCORE_CUTOFF = 0

    def __init__(self, filename: Union[str, io.BytesIO]):
        self.filename = filename
        filename.seek(0)
        self.bytes = filename.read()
        filename.seek(0)
        self.tt = ttLib.TTFont(self.filename)
        self._font_cache = {}
        self._trans_map = None

        # ident: true_char
        self._dec_info = {}

    # region Utils
    @property
    def cmap(self) -> Dict[int, str]:
        self.tt.ensureDecompiled()
        return self.tt.tables["cmap"].tables[0].cmap

    def _get_pil_font(self, size: int):
        if size not in self._font_cache:
            self._font_cache[size] = ImageFont.truetype(io.BytesIO(self.bytes), size)

        return self._font_cache[size]

    def get_glyph_image(self, character: str, size: int = 30):
        font = self._get_pil_font(size)

        im = Image.new("RGBA", (800, 600))
        draw = ImageDraw.Draw(im)

        draw.text((0, 0), character, font=font)

        return im.crop(im.getbbox())

    def save_glyph_image(self, filename: str, character: str, size: int = 30):
        im = self.get_glyph_image(character, size)
        new_image = Image.new("RGBA", im.size, "BLACK")
        new_image.paste(im, (0, 0), im)
        return new_image
        # im.save(filename)

    def dump_all(self, dest: str, size: int = 30):
        os.makedirs(dest, exist_ok=True)

        for char, glyph in self.cmap.items():
            image = self.get_glyph_image(chr(char), size)
            char_ident = self._get_glyph_key(image, chr(char), size)
            image.save(os.path.join(dest, f"{char_ident}.png"))

            # print(glyph, char_ident)

    # endregion

    def get_glyph_key(self, character: str, size: int = 30):
        image = self.get_glyph_image(character)

        return self._get_glyph_key(image, character, size)

    @abc.abstractmethod
    def _get_glyph_key(self, image: Image, character: str, size: int):
        pass

    def add_sample(self, filename: Union[str, io.BytesIO], char_map: Union[str, List[str]]):
        if type(char_map) is str:
            char_map = list(char_map)

        sample = self.__class__(filename)

        self._add_sample(sample, char_map)

    def _add_sample(self, sample: "DecoderBase", char_map: List[str]):
        real_glyph_names = set(sample.cmap.values())
        order_map = {x: idx for idx, x in enumerate(filter(lambda x: x in real_glyph_names, sample.tt.glyphOrder))}

        for char, glpyh_name in sample.cmap.items():
            true_char = char_map[order_map[glpyh_name]]
            if true_char is None:
                continue

            ident = sample.get_glyph_key(chr(char))

            existing = self._dec_info.get(ident, None)
            if existing is not None and existing != true_char:
                raise ValueError(f"Glyph ident collision! have {ident!r}={existing!r}, tried to map it to {true_char!r}!")

            self._dec_info[ident] = true_char

    def _build_map(self):
        real_glyph_names = set(self.cmap.values())
        order_map = {x: idx for idx, x in enumerate(filter(lambda x: x in real_glyph_names, self.tt.glyphOrder))}

        char_map = {}
        order_tl = {}
        unknown_glyphs = {}

        for char, glyph_name in self.cmap.items():
            char_ident = self.get_glyph_key(chr(char))
            order_num = order_map[glyph_name]

            if char_ident not in self._dec_info:
                options = [(self._compare_idents(char_ident, cand_ident), cand_ident) for cand_ident, cand_char in self._dec_info.items()]
                options = sorted(options, key=lambda x: x[0])
                if len(options) == 0:
                    print(f"No match found!!")
                    io_byte = io.BytesIO()
                    im = self.save_glyph_image(f"{str(char_ident)}.png", chr(char))
                    im.save(io_byte, "PNG")
                    unknown_glyphs[order_num] = (chr(char), io_byte)
                elif options[0][0] <= self.SCORE_CUTOFF:
                    # print(f"Matched with score {options[0][0]}")
                    char_ident = options[0][1]

                    char_map[chr(char)] = self._dec_info[char_ident]
                    order_tl[order_num] = self._dec_info[char_ident]
                else:
                    print(f"Closest was {self._dec_info[options[0][1]]!r} with a score of {options[0][0]}")
                    io_byte = io.BytesIO()
                    im = self.save_glyph_image(f"{str(char_ident)}.png", chr(char))
                    im.save(io_byte, "PNG")
                    unknown_glyphs[order_num] = (chr(char), io_byte)
                    # im.save(f"{str(char_ident)}.png")
                    # raise ValueError(f"Unknown character {str(char_ident)!r} at index {order_map[glyph_name]}")

        return str.maketrans(char_map), order_tl, unknown_glyphs

    def decode(self, text: str):
        pass

    def _compare_idents(self, a, b):
        return a - b

    def serialise(self) -> str:
        return json.dumps(self._dec_info)

    def deserialise(self, state: str):
        self._dec_info = json.loads(state)


class HashBasedDecoder(DecoderBase):
    SCORE_CUTOFF = 10

    def _get_glyph_key(self, image: Image, character: str, size: int):
        return imagehash.average_hash(image)


class MetricsBasedDecoder(DecoderBase):
    SCORE_CUTOFF = 10

    def _get_glyph_key(self, image: Image, character: str, size: int):
        glyph_name = self.cmap[ord(character)]

        glyph = self.tt.tables["glyf"].glyphs[glyph_name]
        hmtx = self.tt.tables["hmtx"].metrics[glyph_name]
        return DistComparable((glyph.xMin, glyph.xMax, glyph.yMin, glyph.yMax, hmtx[0], hmtx[1]))
