"""数据模型.

定义 LRC 歌词的核心数据结构: :class:`LyricWord`、:class:`LyricLine` 和
作为顶层容器的 :class:`Lyrics`.

本模块只承载数据层语义; 解析 (LRC 文本 → :class:`Lyrics`) 与序列化
 (:class:`Lyrics` → LRC 文本) 的实现分别位于 :mod:`.parser` 与
:mod:`.serializer`, 这里仅通过延迟导入把它们暴露成 :class:`Lyrics` 的方法.
"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field
from typing import overload

__all__ = [
    "BasicLyricLine",
    "LyricLine",
    "LyricWord",
    "Lyrics",
]


@dataclass
class LyricWord:
    """一个歌词词元 (可以是一个字、一个词, 或整行纯文本) .

    Attributes:
        content: 词元的文本内容.
        start: 开始时间 (毫秒) , 未知时为 ``None``.
        end: 结束时间 (毫秒) , 未知时为 ``None``.
    """

    content: str = ""
    start: int | None = None
    end: int | None = None


#: 一行歌词主体 (由若干 :class:`LyricWord` 组成的线性序列) .
#:
#: 对于单段整行歌词, 此列表长度通常为 1; 对于逐字歌词, 长度为各词元数量.
BasicLyricLine = list[LyricWord]


@dataclass
class LyricLine:
    """一行歌词.

    Attributes:
        start: 行开始时间 (毫秒) .
        end: 行结束时间 (毫秒) .
        content: 主语言行内容, 见 :data:`BasicLyricLine`.
        reference_lines: 参考行列表, 常用于存放翻译/音译等辅助行.
    """

    start: int | None = None
    end: int | None = None
    content: BasicLyricLine = field(default_factory=list)
    reference_lines: list[BasicLyricLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        """拼接整行主语言的纯文本 (便于日志与简单展示) ."""
        return "".join(word.content for word in self.content)


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

    def combine(self, other: Lyrics, *, other_as_refline_only: bool = True) -> Lyrics:
        """将另一份 :class:`Lyrics` 合并进当前对象, 返回新实例.

        常见用途是把翻译版本合并到主歌词: 翻译的每一行会被挂在 ``self`` 中
        同 ``start`` 行的 :attr:`LyricLine.reference_lines` 列表里.

        Args:
            other: 要合并进来的另一份歌词.
            other_as_refline_only: 若为 ``True`` (默认) , ``other`` 中在
                ``self`` 里找不到对应时间点的行会被丢弃; 若为 ``False``,
                这些行会被保留为新行.

        Returns:
            合并后的新 :class:`Lyrics` 对象; ``self`` 与 ``other`` 均不受影响.
        """
        new = Lyrics()
        # metadata 以 self 为准, other 作为补充
        new.metadata.update(other.metadata)
        new.metadata.update(self.metadata)

        pool: dict[int, LyricLine] = {}
        for line in self.lines:
            if line.start is None:
                continue
            # 深拷贝 self 的行, 避免污染原始对象
            pool[line.start] = deepcopy(line)
        for line in other.lines:
            if line.start is None:
                continue
            if line.start in pool:
                # 深拷贝 other 的行内容, 避免共享引用
                pool[line.start].reference_lines.append(deepcopy(line.content))
                pool[line.start].reference_lines.extend(
                    deepcopy(rl) for rl in line.reference_lines
                )
            elif not other_as_refline_only:
                pool[line.start] = deepcopy(line)

        new.lines = list(pool.values())
        return new

    @classmethod
    def loads(cls, s: str, *, fill_implicit_line_end: bool = False) -> Lyrics:
        """从 LRC 字符串解析出一份 :class:`Lyrics`.

        Args:
            s: LRC 源文本.
            fill_implicit_line_end: 若为 ``True``, 则当某行没有显式结束时间时,
                自动用下一行的开始时间作为其结束时间.
        """
        from .parser import parse_lrc

        return parse_lrc(s, fill_implicit_line_end=fill_implicit_line_end)

    def dumps(
        self,
        *,
        with_metadata: bool = True,
        use_bracket_for_byword_tag: bool = False,
        apply_offset_from_metadata: bool = False,
    ) -> str:
        """把当前对象序列化为 LRC 字符串.

        Args:
            with_metadata: 是否写出 metadata 段.
            use_bracket_for_byword_tag: 逐字标签是否使用 ``[...]``
                 (默认 ``False`` 使用 ``<...>``) .
            apply_offset_from_metadata: 是否读取并应用 ``metadata.offset``;
                见 :func:`.serializer.dump_lrc` 的完整语义说明.
        """
        from .serializer import dump_lrc

        return dump_lrc(
            self,
            with_metadata=with_metadata,
            use_bracket_for_byword_tag=use_bracket_for_byword_tag,
            apply_offset_from_metadata=apply_offset_from_metadata,
        )

    def __str__(self) -> str:
        return self.dumps()
