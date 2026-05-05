# Lemony LRC Parser

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/lemony-lrc-parser)](https://pypi.org/project/lemony-lrc-parser/)

柠檬味的 Python LRC 歌词解析器.

Lemon-flavored LRC Parser for Python.

## Features

- 解析标准 LRC 歌词文件
- 支持 EnhancedLRC / SPL 的逐字歌词标签
- 支持 metadata 标签
- 支持折叠时间标签
- 支持参照行
- 支持歌词合并
- 完整的类型注解

## Installation

推荐使用 [uv](https://docs.astral.sh/uv/).

It's recommend to use [uv](https://docs.astral.sh/uv/).

```bash
uv add lemony-lrc-parser
```

用 pip 也行.

It's okay to use pip.

```bash
pip install lemony-lrc-parser
```

## Usage

### Quick Start

```python
import lemony_lrc_parser as llp

lrc_text = """[ti: Never Gonna Give You Up]
[ar: Rick Astley]

[00:18.684]We're no strangers to love
[00:18.684]我们都是情场老手

[00:22.657]You know the rules and so do I
[00:22.657]你和我都知道爱情的规则

[00:27.070]A full commitment's what I'm thinking of
[00:27.070]我在想的正是一份实打实的承诺

[00:31.459]You wouldn't get this from any other guy
[00:31.459]你从其他人那里得不到的
"""

# 解析
lyrics = llp.loads(lrc_text)

# 访问 metadata
print(lyrics.metadata["ti"])  # "Never Gonna Give You Up"
print(lyrics.metadata["ar"])  # "Rick Astley"

# 遍历歌词行
for line in lyrics:
    print(f"{line.start}ms: {line.text}")

# 序列化回 LRC 文本
output = llp.dumps(lyrics)
```

### OOP Interface

`Lyrics` 类提供面向对象的解析和序列化入口:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# Lyrics 同时是序列容器
print(len(lyrics))    # 行数
print(lyrics[0].text) # 第一行文本
print(lyrics[-1].text)

# 切片访问
first_three = lyrics[0:3]

# 序列化
lrc_output = lyrics.dumps()

# __str__ 等价于 dumps()
print(lyrics)
```

### Word-level Lyrics

解析逐字 (Enhanced LRC / SPL) 歌词:

```python
lrc_text = "[00:01.00]<00:01.00>Never <00:01.50>gonna <00:02.00>give <00:02.50>you <00:03.00>up[00:03.50]"

lyrics = llp.loads(lrc_text)
line = lyrics[0]

for word in line.content:
    print(f"  [{word.start} -> {word.end}] {word.content!r}")
    # [1000 -> 1500] 'Never '
    # [1500 -> 2000] 'gonna '
    # [2000 -> 2500] 'give '
    # [2500 -> 3000] 'you '
    # [3000 -> None] 'up'

# 行级时间: line.start=1000, line.end=3500
```

### Reference Lines (Translation / Transliteration)

LRC 文件中, 紧跟在带时间标签行后面的无标签行, 或与主行的时间戳相同的行, 会被解析为参考行, 常用于存放翻译或音译:

```python
lrc_text = """[00:01.00]Hello
    你好
[00:02.00]World
[00:02.00]世界
"""

lyrics = llp.loads(lrc_text)

line = lyrics[0]
print(line.text)                              # "Hello"
print(line.reference_lines[0][0].content)     # "你好"
```

### Combining Lyrics

将两份歌词 (如原文和翻译) 按时间标签合并:

```python
main = llp.loads("[00:01.00]Hello\n[00:02.00]World\n")
translation = llp.loads("[00:01.00]你好\n[00:02.00]世界\n")

# combine 方法: 翻译行挂到同时间点的 reference_lines 中
combined = main.combine(translation)

# 也可以用 + 运算符
combined = main + translation

for line in combined:
    print(line.text)  # 主歌词
    for ref in line.reference_lines:
        ref_text = "".join(w.content for w in ref)
        print(f"  -> {ref_text}")  # 参考行

# other_as_refline_only=False 时, 翻译中找不到对应时间点的行会作为新行保留
combined = main.combine(translation, other_as_refline_only=False)
```

### Implicit Line End

当歌词行没有显式结束时间时, 可以自动用下一行的开始时间填充:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import ParseOptions

lyrics = Lyrics.loads(lrc_text, options=ParseOptions(fill_implicit_line_end=True))

# lyrics[0].end == lyrics[1].start
```

### Parsing Options

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import ParseOptions

lyrics = Lyrics.loads(
    lrc_text,
    options=ParseOptions(
        fill_implicit_line_end=False,       # 是否填充隐式行尾时间
    ),
)
```

### Serialization Options

通过 `SerializationOptions` 控制序列化行为:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import SerializationOptions

output = lyrics.dumps(
    options=SerializationOptions(
        with_metadata=True,                     # 是否输出 metadata 段
        use_bracket_for_byword_tag=False,       # 逐字标签使用 [...] 还是 <...> (默认)
        skip_empty_metadata=True,               # 跳过空值的 metadata 键
        line_tag_decimal_length=2,              # 行标签毫秒位数 (默认 2)
        word_tag_decimal_length=2,              # 逐字标签毫秒位数 (默认 2)
    ),
)
```

#### Offset 语义

- `positive_delays` (默认): `display_time = tag_time + offset`, 正 offset → 歌词延后显示.
- `positive_advances`: `display_time = tag_time - offset`, 正 offset → 歌词提前显示.

如果应用 offset 会导致时间戳变为负数, 则只应用"安全"的部分, 剩余量写回 `metadata["offset"]`.

#### 小数位数

默认 `line_tag_decimal_length=2`、`word_tag_decimal_length=2`, 输出格式如 `[00:01.00]`、`<00:01.05>`.
毫秒值不足 2 位时自动补齐, 超过 2 位时不截断 (例如 `500`ms 仍显示为 `[00:01.500]`).

### Applying Offset

通过 `Lyrics.apply_offset()` 应用 `metadata.offset` 偏移, 返回一个新对象:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import OffsetSemantics

lyrics = Lyrics.loads(lrc_text)

# 默认 positive_delays 语义: display_time = tag_time + offset
shifted = lyrics.apply_offset()

# 也可以指定语义方向
shifted = lyrics.apply_offset(offset_semantics=OffsetSemantics.positive_advances)

# shifted 的时间戳已被整体偏移, 原始 lyrics 不受影响
```

序列化时不会再自动应用 offset；如需在序列化前偏移时间戳, 请先调用 `apply_offset()` 再序列化返回的副本.

### Skip Empty Metadata

默认跳过空值的 metadata 键:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import SerializationOptions

lyrics = Lyrics.loads('[ti: Test]\n[empty: ]\n[00:01.00]Hello\n')

# 默认跳过空值
print(lyrics.dumps())  # 不含 [empty: ]

# 保留空值
print(lyrics.dumps(options=SerializationOptions(skip_empty_metadata=False)))
```

## References

[LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_(file_format))

[SPL Specification](https://moriafly.com/standards/spl.html)

## UwU?

UwU!

## License

MIT License
