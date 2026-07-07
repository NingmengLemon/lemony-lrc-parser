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
- 与简单字幕格式 (SRT / WebVTT) 互转
- 时间偏移 (`apply_delta` / `<<` / `>>` 运算符)
- 字典序列化 (`to_dict()` / `from_dict()`)
- 深拷贝方法链 (`.copy()`)
- 可配置解析与序列化选项
- 完整的类型注解

## Installation

推荐使用 [uv](https://docs.astral.sh/uv/).

It's recommended to use [uv](https://docs.astral.sh/uv/).

```bash
uv add lemony-lrc-parser
```

用 pip 也行.

It's okay to use pip.

```bash
pip install lemony-lrc-parser
```

可以使用 git 仓库来源来第一时间体验到最新最热的 ~~bug~~ feature.

You can use git repo as a source to catch the newest ~~bugs~~ features.

```bash
uv add https://github.com/NingmengLemon/lemony-lrc-parser.git
```

## Usage

### Quick Start

json, marshal or pickle -like usages

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

# 序列化回 LRC 格式
output = llp.dumps(lyrics)
```

### OOP Interface

`Lyrics` 类提供面向对象的解析和序列化入口, 也推荐使用面向对象接口:

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

### Dict Serialization (to_dict / from_dict)

所有数据模型都支持字典序列化, 方便 JSON 传输和 API 对接:

```python
import lemony_lrc_parser as llp

lyrics = llp.loads("[00:01.00]Hello\n[00:02.00]World\n")

# Lyrics → dict
data = lyrics.to_dict()
# {"metadata": {}, "lines": [{"start": 1000, ...}, ...]}

# dict → Lyrics
restored = Lyrics.from_dict(data)

# 也可以对单行、单行内容、单个词元分别操作
line = lyrics[0]
line_dict = line.to_dict()
token_dict = line.content[0].to_dict()
```

### Copy

所有数据模型都提供 `.copy()` 深拷贝方法, 返回独立的副本:

```python
import lemony_lrc_parser as llp

lyrics = llp.loads("[00:01.00]Hello\n")

# 深拷贝
clone = lyrics.copy()
clone.metadata["ti"] = "New Title"

# 原始对象不受影响
print(lyrics.metadata.get("ti"))  # None
```

### Options

#### Parsing Options

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import ParseOptions

lrc_text = "[00:01.000]Hello\n[00:05.000]World\n"

lyrics = Lyrics.loads(
    lrc_text,
    options=ParseOptions(
        fill_implicit_line_end=True,        # 是否填充隐式行尾时间
        line_filter="纯音乐, 请欣赏",                    # 黑名单过滤：丢弃包含该子串的行
        # line_filter=re.compile(r"纯音乐.*?请欣赏"),  # 也支持已编译的正则
    ),
)

# lyrics[0].end == lyrics[1].start == 5000
```

#### Serialization Options

通过 `SerializationOptions` 控制序列化行为:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import SerializationOptions

output = lyrics.dumps(
    options=SerializationOptions(
        with_metadata=True,                     # 是否输出 metadata 段
        use_bracket_for_byword_tag=False,       # 逐字标签使用 [...] 还是 <...> (默认)
        line_tag_decimal_length=3,              # 行标签毫秒位数 (默认 3)
        word_tag_decimal_length=3,              # 逐字标签毫秒位数 (默认 3)
        line_separator="\n",                    # 行间分隔字符串 (默认 "\n", 设为 "" 可省去空行)
    ),
)
```

#### Length of Decimal Part

默认 `line_tag_decimal_length=3`、`word_tag_decimal_length=3`, 输出格式如 `[00:01.000]`、`<00:01.050>`, 保留完整的毫秒精度.
若设为 `2`, 小数部分表示百分秒 (如 `[00:01.00]`), 属于**有损截断** (例如 555ms 会被截断为 55, 解析回来变成 550ms), 需要按需权衡 (部分老软件可能只支持百分秒).

### Offset

使用 `Lyrics.apply_delta(ms)` 应用时间偏移, ms 会*直接加到*每个标签的时间戳上,
这意味着传入*正数*偏移值会导致歌词整体*延后*出现, 反之同理.

也可以使用重载的 `>>` / `<<` 运算, 私以为这样会更好理解一些.

如果应用 offset 会导致时间戳变为负数, 将抛出 `TimestampUnderflowError`, 由调用方自行处理.

#### Applying Offset

通过 `Lyrics.apply_delta(ms)` 对时间戳应用偏移, 返回一个新对象:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# 正数 → 歌词延后出现 (等价于 lyrics >> 500)
shifted = lyrics.apply_delta(500)

# 负数 → 歌词提前出现 (等价于 lyrics << 500)
shifted = lyrics.apply_delta(-500)

# 使用 << / >> 运算符
shifted = lyrics >> 500   # 延后 500ms
shifted = lyrics << 500   # 提前 500ms

# shifted 的时间戳已被整体偏移, 原始 lyrics 不受影响
```

如果偏移会导致时间戳变为负数, 将抛出 `TimestampUnderflowError`.

如需在序列化前偏移时间戳, 请先调用 `apply_delta()` 再序列化返回的副本.
如果你的偏移量来自歌词文件元数据, 你可能还需要记得手动清理 `lyrics.metadata` 中的偏移值.

### Subtitle Conversion (SRT / WebVTT)

`Lyrics` 可与常见的简单字幕格式互相转换, 便于把歌词用于视频字幕制作,
或把已有字幕导入为歌词:

```python
from lemony_lrc_parser import Lyrics
from lemony_lrc_parser.models import SubtitleOptions

lyrics = Lyrics.loads("[00:01.000]Hello\n[00:03.000]World\n")

# LRC → SRT / WebVTT
srt_text = lyrics.to_srt()
vtt_text = lyrics.to_webvtt()

# SRT / WebVTT → LRC
lyrics2 = Lyrics.from_srt(srt_text)
lyrics3 = Lyrics.from_webvtt(vtt_text)

# 顶层便捷函数也可用
import lemony_lrc_parser as llp

srt_text = llp.dump_srt(lyrics)
vtt_text = llp.dump_webvtt(lyrics)
lyrics2 = llp.parse_srt(srt_text)
lyrics3 = llp.parse_webvtt(vtt_text)
```

字幕以 `[start, end]` 时间区间为单位, 与 LRC 存在语义差异, 转换时的行为可通过
`SubtitleOptions` 控制:

```python
options = SubtitleOptions(
    fill_end_from_next=True,       # 缺少行尾时间时, 用下一行的 start 补齐
    default_duration_ms=5000,      # 无法推断时长时使用的默认时长 (也用于修正非法区间)
    include_reference_lines=True,  # 是否把参考行 (翻译/音译) 作为 cue 附加文本输出
)

srt_text = lyrics.to_srt(options=options)
```

转换注意事项:

- LRC 的逐字标签与 metadata 不会写入字幕 (会被拍平/丢弃).
- 导出时若某行缺少 `end`, 会依次尝试用下一行 `start` 或
  `default_duration_ms` 补齐; `end <= start` 的非法区间也会被修正.
- 一条字幕 cue 可含多行文本: 导出时主行在前、参考行在后;
  解析时 cue 首行作为主行, 其余行作为参考行.
- 解析会自动跳过 WebVTT 的 `WEBVTT` 头部以及 `NOTE` / `STYLE` / `REGION` 块.

## References

[LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29)

[SPL Specification](https://moriafly.com/standards/spl.html)

## UwU?

UwU!

## License

MIT License
