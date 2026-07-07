"""数据模型.

定义 LRC 歌词的核心数据结构: :class:`LyricToken`、:class:`LyricLine` 和
作为顶层容器的 :class:`Lyrics`.

本模块只承载数据层语义; 解析 (LRC 文本 → :class:`Lyrics`) 与序列化
 (:class:`Lyrics` → LRC 文本) 的实现分别位于 :mod:`.parser` 与
:mod:`.serializer`, 这里仅通过延迟导入把它们暴露成 :class:`Lyrics` 的方法.
"""

from __future__ import annotations

import re
import sys
from collections import UserList
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import (
    Any,
    SupportsIndex,
    TextIO,
    TypedDict,
    overload,
)

from typing_extensions import Self, override

from .exceptions import ProgrammingError, TimestampUnderflowError

if sys.version_info >= (3, 10):
    from types import NotImplementedType
else:
    NotImplementedType = type(NotImplemented)

__all__ = [
    "BasicLyricLine",
    "LyricLine",
    "LyricToken",
    "Lyrics",
    "ParseOptions",
    "SerializationOptions",
    "SubtitleOptions",
]
_DC_ARGS_SLOTS = (
    {
        "slots": True,
        "weakref_slot": True,
    }
    if sys.version_info >= (3, 11)
    else {"slots": True}
    if sys.version_info >= (3, 10)
    else {}
)


@dataclass
class ParseOptions:
    """解析选项.

    Attributes:
        fill_implicit_line_end: 若为 ``True``, 则当某行没有显式结束时间时,
            自动用下一行的开始时间作为其结束时间.
        line_filter: 黑名单过滤. 若为字符串, 则匹配 lyrics 文本中包含该子串的行;
            若为已编译的正则, 则用 ``pattern.search`` 匹配行文本.
            匹配到的行在解析时会被丢弃. ``None`` 表示不过滤.
    """

    fill_implicit_line_end: bool = False
    line_filter: str | re.Pattern | None = None


@dataclass
class SerializationOptions:
    """序列化选项.

    Attributes:
        with_metadata: 是否输出 metadata 段.
        use_bracket_for_byword_tag: 逐字标签使用 ``[...]`` 而非 ``<...>``. 在 foobar2000 等老式播放器上可能会有用.
        line_tag_decimal_length: 行标签毫秒位数 (默认 3), 使用更小的值会损失精度.
        word_tag_decimal_length: 逐字标签毫秒位数 (默认 3), 使用更小的值会损失精度.
        line_separator: 行间分隔字符串 (默认 ``"\\n"`` 表示行间插入空行).
            设为 ``""`` 可省去空行.
    """

    with_metadata: bool = True
    use_bracket_for_byword_tag: bool = False
    line_tag_decimal_length: int = 3
    word_tag_decimal_length: int = 3
    line_separator: str = "\n"

    def __post_init__(self) -> None:
        """校验参数合法性."""
        from .timetag import MAX_TAIL_DIGITS, MIN_TAIL_DIGITS

        for f in ("line_tag_decimal_length", "word_tag_decimal_length"):
            val = getattr(self, f)
            if not MIN_TAIL_DIGITS <= val <= MAX_TAIL_DIGITS:
                raise ProgrammingError(
                    f"{f} must be between {MIN_TAIL_DIGITS} and {MAX_TAIL_DIGITS}, got {val}"
                )


@dataclass
class SubtitleOptions:
    """字幕 (SRT / WebVTT) 转换选项.

    仅在 :class:`Lyrics` 与字幕格式互转时使用, 见 :mod:`.subtitle`.

    Attributes:
        fill_end_from_next: 当某行缺少结束时间时, 是否用下一行的开始时间
            作为其结束时间. 为 ``False`` 或已是最后一行时, 改用
            ``start + default_duration_ms``.
        default_duration_ms: 无法推断结束时间时使用的默认时长 (毫秒).
            也用于修正 ``end <= start`` 的非法区间.
        include_reference_lines: 导出字幕时是否把参考行 (翻译/音译) 作为
            cue 内的附加文本行一并输出.
    """

    fill_end_from_next: bool = True
    default_duration_ms: int = 5000
    include_reference_lines: bool = True

    def __post_init__(self) -> None:
        """校验参数合法性."""
        if self.default_duration_ms <= 0:
            raise ProgrammingError(
                f"default_duration_ms must be positive, got {self.default_duration_ms}"
            )


@dataclass(**_DC_ARGS_SLOTS)
class LyricToken:
    """一个歌词词元 (可以是一个字、一个词, 或整行纯文本) .

    Attributes:
        content: 词元的文本内容.
        start: 开始时间 (毫秒) , 未知时为 ``None``.
        end: 结束时间 (毫秒) , 未知时为 ``None``.
    """

    content: str = ""
    start: int | None = None
    end: int | None = None

    def __str__(self) -> str:
        return self.content

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return key in self.content
        return False

    def copy(self) -> LyricToken:
        return LyricToken(content=self.content, start=self.start, end=self.end)

    def to_dict(self) -> _LyricTokenDict:
        return _LyricTokenDict(content=self.content, start=self.start, end=self.end)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LyricToken":
        return cls(
            content=data.get("content", ""),
            start=data["start"],
            end=data.get("end"),
        )


#: 一行歌词主体 (由若干 :class:`LyricToken` 组成的线性序列) .
#:
#: 对于单段整行歌词, 此列表长度通常为 1; 对于逐字歌词, 长度为各词元数量.
class BasicLyricLine(UserList[LyricToken]):
    __slots__ = ()

    def __init__(self, tokens: Iterable[LyricToken] | None = None) -> None:
        super().__init__((t.copy() for t in tokens) if tokens is not None else None)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self.text
        return super().__contains__(item)

    def __str__(self) -> str:
        return self.text

    @property
    def text(self) -> str:
        return "".join(token.content for token in self)

    def copy(self) -> BasicLyricLine:
        return BasicLyricLine(self)

    def to_dict(self) -> list[_LyricTokenDict]:
        return [token.to_dict() for token in self]

    @classmethod
    def from_dict(cls, data: list[dict[str, Any]]) -> BasicLyricLine:
        return BasicLyricLine([LyricToken.from_dict(token_data) for token_data in data])


@dataclass(**_DC_ARGS_SLOTS)
class LyricLine:
    """一行歌词.

    Attributes:
        start: 行开始时间 (毫秒) .
        end: 行结束时间 (毫秒) .
        content: 主语言行内容, 见 :data:`BasicLyricLine`.
        reference_lines: 参考行列表, 常用于存放翻译/音译等辅助行.
    """

    start: int
    end: int | None = None
    content: BasicLyricLine = field(default_factory=BasicLyricLine)
    reference_lines: list[BasicLyricLine] = field(default_factory=list)

    def __post_init__(self):
        if self.start is None:
            raise TypeError("LyricLine.start cannot be None")

    def copy(self) -> "LyricLine":
        return LyricLine(
            start=self.start,
            end=self.end,
            content=self.content.copy(),
            reference_lines=[rl.copy() for rl in self.reference_lines],
        )

    @property
    def text(self) -> str:
        return self.content.text

    def __len__(self) -> int:
        return len(self.content)

    def __iter__(self) -> Iterator[LyricToken]:
        return iter(self.content)

    @overload
    def __getitem__(self, index: int) -> LyricToken: ...

    @overload
    def __getitem__(self, index: slice) -> BasicLyricLine: ...

    def __getitem__(self, index: int | slice) -> LyricToken | BasicLyricLine:
        return self.content[index]

    def to_dict(self) -> _LyricLineDict:
        return _LyricLineDict(
            start=self.start,
            end=self.end,
            content=self.content.to_dict(),
            reference_lines=[rl.to_dict() for rl in self.reference_lines],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LyricLine":
        return cls(
            start=data["start"],
            end=data.get("end"),
            content=BasicLyricLine.from_dict(data["content"]),
            reference_lines=[
                BasicLyricLine.from_dict(rl) for rl in data.get("reference_lines", [])
            ],
        )


class Lyrics(UserList[LyricLine]):
    """一份完整的歌词.

    Attributes:
        lines: 按时间顺序排列的歌词行.
        metadata: 元数据键值对 (如 ``ti``、``ar``、``offset`` 等) .

    :class:`Lyrics` 同时是序列容器, 可直接 ``for line in lyrics`` 迭代、
    ``len(lyrics)`` 取行数, 或通过下标/切片访问具体行.
    """

    __slots__ = ("metadata",)

    def __init__(
        self,
        lines: Iterable[LyricLine] | None = None,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        super().__init__((i.copy() for i in lines) if lines is not None else None)
        self.metadata: dict[str, str] = metadata.copy() if metadata is not None else {}

    @property
    def lines(self) -> Self:
        return self

    @lines.setter
    def lines(self, value: Iterable[LyricLine]) -> None:
        self.clear()
        self.extend((t.copy() for t in value))

    @override
    def __add__(self, other: Lyrics) -> Lyrics:  # type: ignore[override]
        if not isinstance(other, Lyrics):
            return NotImplemented
        return self.combine(other)

    @override
    def __iadd__(self, value: Lyrics) -> Self:  # type: ignore[override]
        if not isinstance(value, Lyrics):
            return NotImplemented
        self.combine_inplace(value)
        return self

    @override
    def __radd__(self, other: Any) -> NotImplementedType:
        return NotImplemented

    @override
    def __mul__(self, value: SupportsIndex) -> NotImplementedType:
        return NotImplemented

    @override
    def __rmul__(self, value: SupportsIndex) -> NotImplementedType:
        return NotImplemented

    @override
    def __imul__(self, value: SupportsIndex) -> NotImplementedType:
        return NotImplemented

    def combine_inplace(
        self,
        other: Lyrics | Iterable[LyricLine],
        *,
        other_as_refline_only: bool = True,
    ) -> None:
        # metadata 以 self 为准, other 作为补充
        if isinstance(other, Lyrics):
            for k, v in other.metadata.items():
                self.metadata.setdefault(k, v)
        elif isinstance(other, Iterable):
            pass
        else:
            raise TypeError(
                "Lyrics or Iterable[LyricLine] is expected as combine argument",
            )
        other = [lyline for lyline in other if isinstance(lyline, LyricLine)]

        pool: dict[int, LyricLine] = {}
        for line in self:
            pool[line.start] = line
        for line in other:
            if line.start in pool:
                pool[line.start].reference_lines.append(line.content.copy())
                pool[line.start].reference_lines.extend(
                    rl.copy() for rl in line.reference_lines
                )
            elif not other_as_refline_only:
                pool[line.start] = line.copy()

        self.lines = sorted(pool.values(), key=lambda line: line.start)

    def combine(
        self, other: Lyrics | Iterable[LyricLine], *, other_as_refline_only: bool = True
    ) -> Lyrics:
        """将另一份 :class:`Lyrics` 合并进当前对象, 返回新实例.

        常见用途是把翻译版本合并到主歌词: 翻译的每一行会被挂在 ``self`` 中
        同 ``start`` 行的 :attr:`LyricLine.reference_lines` 列表里.

        Args:
            other: 要合并进来的另一份 :class:`Lyrics` 或
                :class:`LyricLine` 可迭代对象.
            other_as_refline_only: 若为 ``True`` (默认) , ``other`` 中在
                ``self`` 里找不到对应时间点的行会被丢弃; 若为 ``False``,
                这些行会被保留为新行.

        Returns:
            合并后的新 :class:`Lyrics` 对象; ``self`` 与 ``other`` 均不受影响.
        """
        new = self.copy()
        new.combine_inplace(other, other_as_refline_only=other_as_refline_only)
        return new

    def copy(self) -> Lyrics:
        return Lyrics(self, metadata=self.metadata)

    @classmethod
    def load(cls, fp: TextIO, *, options: ParseOptions | None = None) -> "Lyrics":
        """从文件加载 LRC 内容.

        Args:
            fp: LRC 文件指针.
            options: 解析选项.
        """
        parsed = cls.loads(fp.read(), options=options)
        return parsed

    def dump(self, fp: TextIO, *, options: SerializationOptions | None = None) -> None:
        """将当前对象写入文件.

        Args:
            fp: LRC 文件指针.
            options: 序列化选项.
        """
        fp.write(self.dumps(options=options))

    @classmethod
    def loads(cls, s: str, *, options: ParseOptions | None = None) -> Lyrics:
        """从 LRC 字符串解析出一份 :class:`Lyrics`.

        Args:
            s: LRC 源文本.
            options: 解析选项.
        """
        from .parser import parse_lrc

        return parse_lrc(s, options=options)

    def dumps(self, *, options: SerializationOptions | None = None) -> str:
        """把当前对象序列化为 LRC 字符串.

        Args:
            options: 序列化选项.
        """
        from .serializer import dump_lrc

        return dump_lrc(self, options=options)

    def to_srt(self, *, options: SubtitleOptions | None = None) -> str:
        """把当前对象转换为 SRT (SubRip) 字幕文本.

        Args:
            options: 字幕转换选项.
        """
        from .subtitle import dump_srt

        return dump_srt(self, options=options)

    def to_webvtt(self, *, options: SubtitleOptions | None = None) -> str:
        """把当前对象转换为 WebVTT 字幕文本.

        Args:
            options: 字幕转换选项.
        """
        from .subtitle import dump_webvtt

        return dump_webvtt(self, options=options)

    @classmethod
    def from_srt(cls, s: str) -> Lyrics:
        """从 SRT (SubRip) 字幕文本解析出一份 :class:`Lyrics`.

        Args:
            s: SRT 源文本.
        """
        from .subtitle import parse_srt

        return parse_srt(s)

    @classmethod
    def from_webvtt(cls, s: str) -> Lyrics:
        """从 WebVTT 字幕文本解析出一份 :class:`Lyrics`.

        Args:
            s: WebVTT 源文本.
        """
        from .subtitle import parse_webvtt

        return parse_webvtt(s)

    def apply_delta(self, ms: int) -> Lyrics:
        """深拷贝当前对象并在新副本上应用时间偏移, 返回新对象.

        该方法**不修改**原始对象, 而是返回一个时间戳已被整体偏移的新
        :class:`Lyrics`.

        这里的 ms 直接加在时间戳上, 所以用了 delta 这个词而不是 offset.

        若偏移后存在任何时间戳 < 0, 直接抛出 :class:`TimestampUnderflowError`,
        由调用方自行处理 (例如先从 ``metadata.offset`` 读取值再传入).

        Args:
            ms: 要加到每个时间戳上的毫秒数.

        Returns:
            应用了偏移后的新 :class:`Lyrics` 对象.

        Raises:
            TimestampUnderflowError: 偏移后会导致某个时间戳变为负数.
        """
        from .offset import apply_delta, iter_all_timestamps

        if ms == 0:
            return self.copy()

        # 先做下溢检测, 避免异常路径上的 deepcopy 浪费
        all_times = list(iter_all_timestamps(self))
        if all_times:
            min_time = min(all_times)
            if min_time + ms < 0:
                raise TimestampUnderflowError(
                    f"Applying offset={ms}ms would make minimum "
                    f"timestamp {min_time}ms negative"
                )

        result = self.copy()
        apply_delta(result, ms)
        return result

    def __lshift__(self, ms: int) -> Lyrics:
        """左移运算符: ``lyrics << ms`` 等价于 ``lyrics.apply_delta(-ms)``.

        语义: 正数 → 歌词提前出现.
        """
        if not isinstance(ms, int):
            return NotImplemented
        return self.apply_delta(-ms)

    def __rshift__(self, ms: int) -> Lyrics:
        """右移运算符: ``lyrics >> ms`` 等价于 ``lyrics.apply_delta(ms)``.

        语义: 正数 → 歌词延后出现.
        """
        if not isinstance(ms, int):
            return NotImplemented
        return self.apply_delta(ms)

    def __str__(self) -> str:
        return self.dumps()

    def to_dict(self) -> _LyricsDict:
        return _LyricsDict(
            metadata=self.metadata.copy(),
            lines=[line.to_dict() for line in self.lines],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lyrics":
        metadata = data.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
        return cls(
            lines=[
                LyricLine.from_dict(line_data) for line_data in data.get("lines", [])
            ],
            metadata=metadata,
        )


class _LyricTokenDict(TypedDict):
    start: int | None
    end: int | None
    content: str


class _LyricLineDict(TypedDict):
    start: int
    end: int | None
    content: list[_LyricTokenDict]
    reference_lines: list[list[_LyricTokenDict]]


class _LyricsDict(TypedDict):
    metadata: dict[str, str]
    lines: list[_LyricLineDict]
