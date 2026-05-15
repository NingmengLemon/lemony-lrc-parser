"""数据模型.

定义 LRC 歌词的核心数据结构: :class:`LyricToken`、:class:`LyricLine` 和
作为顶层容器的 :class:`Lyrics`.

本模块只承载数据层语义; 解析 (LRC 文本 → :class:`Lyrics`) 与序列化
 (:class:`Lyrics` → LRC 文本) 的实现分别位于 :mod:`.parser` 与
:mod:`.serializer`, 这里仅通过延迟导入把它们暴露成 :class:`Lyrics` 的方法.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TextIO, overload

from .exceptions import ProgrammingError, TimestampUnderflowError

__all__ = [
    "BasicLyricLine",
    "LyricLine",
    "LyricToken",
    "Lyrics",
    "ParseOptions",
    "SerializationOptions",
]


@dataclass
class ParseOptions:
    """解析选项.

    Attributes:
        fill_implicit_line_end: 若为 ``True``, 则当某行没有显式结束时间时,
            自动用下一行的开始时间作为其结束时间.
    """

    fill_implicit_line_end: bool = False


@dataclass
class SerializationOptions:
    """序列化选项.

    Attributes:
        with_metadata: 是否输出 metadata 段.
        use_bracket_for_byword_tag: 逐字标签使用 ``[...]`` 而非 ``<...>``. 在 foobar2000 等老式播放器上可能会有用.
        line_tag_decimal_length: 行标签毫秒位数 (默认 2).
        word_tag_decimal_length: 逐字标签毫秒位数 (默认 2).
        line_separator: 行间分隔字符串 (默认 ``"\n"`` 表示行间插入空行).
            设为 ``""`` 可省去空行.
    """

    with_metadata: bool = True
    use_bracket_for_byword_tag: bool = False
    line_tag_decimal_length: int = 2
    word_tag_decimal_length: int = 2
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

    def __repr__(self) -> str:
        return f"LyricToken({self.content!r}, {self.start!r}, {self.end!r})"

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return key in self.content
        return False

    def copy(self) -> LyricToken:
        return LyricToken(content=self.content, start=self.start, end=self.end)


#: 一行歌词主体 (由若干 :class:`LyricToken` 组成的线性序列) .
#:
#: 对于单段整行歌词, 此列表长度通常为 1; 对于逐字歌词, 长度为各词元数量.
class BasicLyricLine(list[LyricToken]):
    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return key in self.text
        return super().__contains__(key)

    def __str__(self) -> str:
        return self.text

    @property
    def text(self) -> str:
        return "".join(token.content for token in self)

    def copy(self) -> BasicLyricLine:
        return BasicLyricLine([token.copy() for token in self])


@dataclass
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
    def __getitem__(self, index: slice) -> list[LyricToken]: ...

    def __getitem__(self, index: int | slice) -> LyricToken | list[LyricToken]:
        return self.content[index]


@dataclass
class Lyrics:
    """一份完整的歌词.

    Attributes:
        lines: 按时间顺序排列的歌词行.
        metadata: 元数据键值对 (如 ``ti``、``ar``、``offset`` 等) .

    :class:`Lyrics` 同时是序列容器, 可直接 ``for line in lyrics`` 迭代、
    ``len(lyrics)`` 取行数, 或通过下标/切片访问具体行.
    """

    lines: list[LyricLine] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def __iter__(self) -> Iterator[LyricLine]:
        return iter(self.lines)

    def __len__(self) -> int:
        return len(self.lines)

    @overload
    def __getitem__(self, index: int) -> LyricLine: ...

    @overload
    def __getitem__(self, index: slice) -> list[LyricLine]: ...

    def __getitem__(self, index: int | slice) -> LyricLine | list[LyricLine]:
        return self.lines[index]

    def __add__(self, other: Lyrics) -> Lyrics:
        if not isinstance(other, Lyrics):
            return NotImplemented
        return self.combine(other)

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
        new = Lyrics()
        # metadata 以 self 为准, other 作为补充
        if isinstance(other, Lyrics):
            new.metadata.update(other.metadata)
        new.metadata.update(self.metadata)

        pool: dict[int, LyricLine] = {}
        for line in self.lines:
            pool[line.start] = line.copy()
        for line in other:
            if line.start in pool:
                pool[line.start].reference_lines.append(line.content.copy())
                pool[line.start].reference_lines.extend(
                    rl.copy() for rl in line.reference_lines
                )
            elif not other_as_refline_only:
                pool[line.start] = line.copy()

        new.lines = sorted(pool.values(), key=lambda line: line.start)
        return new

    def copy(self) -> Lyrics:
        return Lyrics(
            lines=[line.copy() for line in self.lines], metadata=self.metadata.copy()
        )

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
