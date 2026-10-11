"""metadata 容器.

LRC 的 ID 标签 (``[ti: 标题]`` 这类) 是**同名可重复**的: ``[ti: A]`` 与
``[ti: B]`` 出现在同一份文件里是合法的 (真实文件里少见但存在, 例如同时写
``[ti: 标题]`` 与 ``[ti: 标题 (Live)]``)。用裸 ``dict`` 承载会静默丢掉先出现的值,
这与本库"不静默丢数据"的取向冲突, 因此改用 :class:`Metadata`。

容器形态的取舍调研见 ``docs/research/metadata.md`` 的"重复 key 与类 headers 容器":
HTTP 头这类"同名可重复"的成熟容器 (werkzeug ``Headers`` / ``httpx.Headers`` /
``multidict.CIMultiDict``) 走的都是"有序 + dict 式读取 + 全量枚举"这第三条路,
既不像裸 ``dict`` 那样丢重复, 也不像 ``list[tuple[str, str]]`` 那样丢掉
``meta["ti"]`` / ``.get()`` / ``.update()`` 这些直觉操作。本类照这个形态实现。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Literal, TypedDict, overload

from typing_extensions import Self

from .exceptions import ProgrammingError

__all__ = [
    "COMMON_METADATA_KEYS",
    "Metadata",
    "MetadataDict",
    "MetadataKey",
]


#: LRC 里最常见的 ID 标签 key (标准集见 LRC 文档: ``ar`` / ``al`` / ``ti`` /
#: ``au`` / ``length`` / ``by`` / ``re`` / ``ve`` / ``offset``).
#:
#: 仅作为**类型提示**与文档用途: :class:`Metadata` 运行时就是普通的
#: ``str -> str`` 映射, 库不会校验、也不会拒绝其它 key (真实语料里常见
#: ``ly`` / ``mu`` / ``total`` / ``tool`` 这类非标准 key).
MetadataKey = Literal["ar", "al", "ti", "au", "length", "by", "re", "ve", "offset"]

#: :data:`MetadataKey` 的运行时形态, 便于遍历 / 做模板.
COMMON_METADATA_KEYS: tuple[MetadataKey, ...] = (
    "ar",
    "al",
    "ti",
    "au",
    "length",
    "by",
    "re",
    "ve",
    "offset",
)


class MetadataDict(TypedDict, total=False):
    """常见 ID 标签的类型提示 (``total=False``, 允许只出现其中几个).

    Note:
        这是给调用方**可选**使用的类型别名 (例如写自己的函数签名时用
        ``def f(meta: MetadataDict)``), 库内部把 metadata 当普通映射,
        不做任何强制校验或补全.
    """

    ar: str
    al: str
    ti: str
    au: str
    length: str
    by: str
    re: str
    ve: str
    offset: str


class Metadata(MutableMapping[str, str]):
    """有序、可重复的 metadata 容器.

    三种读法各有明确口径, 不会互相"顺手"改变语义:

    * ``Mapping`` 协议 (``meta["ti"]`` / ``get()`` / ``keys()`` / ``values()`` /
      ``items()`` / ``len()`` / ``dict(meta)``): **有损的 dict 视角**, 每个 key
      一条, 取**最后**一次出现的值 (与 0.4.x 的裸 ``dict`` 行为一致, 所以升级
      不会让既有代码读到不一样的值).
    * :meth:`to_pairs`: **无损视角**, 按出现顺序给出全部 ``(key, value)``,
      含重复. ``dumps()`` 走的就是这条.
    * :meth:`getlist`: 单个 key 的全部取值, 顺序同上.

    Note:
        ``Mapping`` 协议的每个方法都严格守 dict 语义, 无损读取只有
        :meth:`to_pairs` / :meth:`getlist` 两个显式入口. 这样把 ``Metadata``
        当普通 ``Mapping`` 消费的代码 (``for k, v in meta.items()``) 不会因为
        重复项拿到同一个 key 两次. 要数全部条目用 ``len(meta.to_pairs())``.

    Note:
        ``meta == dict`` 比较**去重后**的 dict 视角 (保持升级前的写法可用);
        ``meta == meta2`` 比较**全部条目**, 所以两份重复项不同的 metadata 不会
        被判为相等 (往返测试正是靠这一点抓丢重复). Python 的反射比较会让
        ``dict == meta`` 也落到同一套规则上.
    """

    __slots__ = ("_pairs",)

    def __init__(
        self,
        initial: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    ) -> None:
        """从 ``dict`` / 另一个 :class:`Metadata` / ``(key, value)`` 序列构造.

        Args:
            initial: 初始内容. ``None`` 表示空. 传 :class:`Metadata` 也走这里
                (它本身就是 ``Mapping``).

        Note:
            传 :class:`Metadata` 时会**拷贝**它的全部条目 (含重复项), 不是共享.
        """
        self._pairs: list[tuple[str, str]] = []
        if initial is not None:
            self.extend(initial)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> str:
        """取 ``key`` 最后一次出现的值 (dict 视角, 有损)."""
        for existing_key, value in reversed(self._pairs):
            if existing_key == key:
                return value
        raise KeyError(key)

    def getlist(self, key: str) -> list[str]:
        """取 ``key`` 的全部取值, 按出现顺序; 不存在时返回 ``[]``."""
        return [value for existing_key, value in self._pairs if existing_key == key]

    def __iter__(self) -> Iterator[str]:
        """按**首次出现**顺序迭代不同的 key (``Mapping`` 协议要求 key 唯一)."""
        seen: set[str] = set()
        for key, _ in self._pairs:
            if key not in seen:
                seen.add(key)
                yield key

    def __len__(self) -> int:
        """不同 key 的个数 (不是条目数, 见类文档)."""
        return len({key for key, _ in self._pairs})

    def to_pairs(self) -> list[tuple[str, str]]:
        """无损导出: 全部 ``(key, value)`` 的副本, 按出现顺序, 含重复.

        与 :meth:`to_dict` 配对使用 —— 需要 JSON 友好又不想丢重复项时用它.
        ``items()`` 是 ``Mapping`` 协议的 dict 视角, 每个 key 只有一条.
        """
        return list(self._pairs)

    def to_dict(self) -> dict[str, str]:
        """有损导出: 同名 key 只留最后一次出现的值.

        与 :meth:`~.models.Lyrics.to_dict` 的口径一致; 无损导出见
        :meth:`to_pairs`.
        """
        return dict(self)

    # ------------------------------------------------------------------
    # 变更
    # ------------------------------------------------------------------

    def __setitem__(self, key: str, value: str) -> None:
        """替换 ``key``: 保留首次出现的位置, 丢掉其余同名条目."""
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        """删除 ``key`` 的全部条目; 不存在时抛 ``KeyError``."""
        if key not in self:
            raise KeyError(key)
        self._pairs = [(k, v) for k, v in self._pairs if k != key]

    def add(self, key: str, value: str) -> None:
        """追加一条, **不去重** (保真路径)."""
        self._pairs.append((key, value))

    def set(self, key: str, value: str) -> None:
        """替换式写入: 同名条目合并成一条, 位置取首次出现处.

        等价于 ``meta[key] = value``; 名字与 :meth:`add` 成对, 便于并排阅读.
        """
        first_index: int | None = None
        kept: list[tuple[str, str]] = []
        for existing_key, existing_value in self._pairs:
            if existing_key == key:
                if first_index is None:
                    first_index = len(kept)
                continue
            kept.append((existing_key, existing_value))
        if first_index is None:
            kept.append((key, value))
        else:
            kept.insert(first_index, (key, value))
        self._pairs = kept

    @overload
    def extend(self, other: Mapping[str, str]) -> None: ...

    @overload
    def extend(self, other: Iterable[tuple[str, str]]) -> None: ...

    def extend(self, other: object) -> None:
        """逐条 :meth:`add` (不是 ``dict.update`` 那种覆盖语义).

        Args:
            other: 另一个 :class:`Metadata` 取它的全部条目 (含重复); 其它
                ``Mapping`` 取它的键值; ``(key, value)`` 序列原样追加.

        Note:
            这是解析器累积 metadata 用的入口: 每读到一行 metatag 就 ``extend``,
            于是 ``[ti: A]`` 与 ``[ti: B]`` 都能留下.

        Raises:
            ProgrammingError: ``other`` 既不是映射, 也不是 ``(key, value)`` 序列
                (含传进来一串裸字符串的情况).
        """
        # 实现签名写成 object + 重载, 而不是直接写联合类型: ty 对
        # "Mapping | Iterable[tuple[...]]" 这种联合做 isinstance 收窄时会算错
        # (把 Mapping 的分支算成 Mapping[tuple[str, str], ...]), 这里绕开它.
        if isinstance(other, Metadata):
            self._pairs.extend(other.to_pairs())
        elif isinstance(other, Mapping):
            for key, value in other.items():
                self._pairs.append((key, value))
        elif isinstance(other, Iterable) and not isinstance(other, (str, bytes)):
            for key, value in other:
                self._pairs.append((key, value))
        else:
            raise ProgrammingError(
                "Metadata.extend expects a Mapping or an iterable of (key, value) "
                f"pairs, got {type(other).__name__}"
            )

    def copy(self) -> Self:
        """返回内容相同、彼此独立的副本 (含重复项)."""
        return type(self)(self)

    # ------------------------------------------------------------------
    # 比较与展示
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        """``Metadata`` 比全部条目, 其它 ``Mapping`` 比去重后的 dict 视角."""
        if isinstance(other, Metadata):
            return self._pairs == other._pairs
        if isinstance(other, Mapping):
            return dict(self) == dict(other)
        return NotImplemented

    def __repr__(self) -> str:
        """没有重复项时用 dict 形式, 否则列出全部条目."""
        if len(self._pairs) == len(self):
            return f"Metadata({dict(self._pairs)!r})"
        return f"Metadata({self._pairs!r})"
