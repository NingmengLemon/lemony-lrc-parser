class LyricsParserError(Exception):
    pass


class InvalidLyricsError(LyricsParserError):
    pass


class TimestampUnderflowError(LyricsParserError):
    pass


class ProgrammingError(Exception):
    pass
