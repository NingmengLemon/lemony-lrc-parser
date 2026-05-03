import os

from .models import Lyrics


def standardize(inp: os.PathLike, float_part_length: int = 3):
    with open(inp, "r", encoding="utf-8") as fp:
        content = fp.read()
    lyrics = Lyrics.loads(content)
    with open(inp, "w", encoding="utf-8") as fp:
        fp.write(lyrics.dumps())
    return lyrics


def main():
    pass
