# Lemony LRC Parser

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/lemony-lrc-parser)](https://pypi.org/project/lemony-lrc-parser/)

**简体中文** | [English](README.en.md)

柠檬味的 Python LRC 歌词解析器.

## 特性

- 解析标准 LRC 歌词文件
- 支持 EnhancedLRC / SPL 的逐字歌词标签
- 支持 metadata 标签
- 支持折叠时间标签
- 支持参考行
- 支持歌词合并
- 与简单字幕格式 (SRT / WebVTT) 互转
- 时间偏移 (`apply_delta` / `<<` / `>>` 运算符)
- 字典序列化 (`to_dict()` / `from_dict()`)
- 深拷贝方法 (`.copy()`)
- 可配置解析与序列化选项
- 数据一致性验证 API (`validate_lyrics` / `Lyrics.validate()`)
- 文本查找 (`contains_text()` / `find_text()`)
- 往返保真度不变量测试 (`解析结果必过校验` / `dumps 一轮收敛` / `行结构稳定`)
- CLI 命令行工具 (`python -m lemony_lrc_parser`)
- 解析错误附带行号与原始行 (`InvalidLyricsError.line_no` / `.raw_line`)
- 完整的类型注解

## 安装

推荐使用 [uv](https://docs.astral.sh/uv/).

```bash
uv add lemony-lrc-parser
```

用 pip 也行.

```bash
pip install lemony-lrc-parser
```

可以使用 git 仓库来源来第一时间体验到最新最热的 ~~bug~~ feature.

```bash
uv add https://github.com/NingmengLemon/lemony-lrc-parser.git
```

## 用法

### 快速开始

用法参考 json, marshal, pickle 等库

```python
import lemony_lrc_parser as llp

lrc_text = """[ti: 凉雨]
[ar: COP,洛天依]

[00:00.000]风透过人潮渐渐停歇的下雨天
[00:02.740]将平凡的故事翻到末页
[00:05.290]并未留下浓重的墨点
[00:08.150]在字里行间流连
"""

# 解析
lyrics = llp.loads(lrc_text)

# 访问 metadata
print(lyrics.metadata["ti"])  # "凉雨"
print(lyrics.metadata["ar"])  # "COP,洛天依"

# 遍历歌词行
for line in lyrics:
    print(f"{line.start}ms: {line.text}")

# 序列化回 LRC 格式
output = llp.dumps(lyrics)
```

### 面向对象接口

`Lyrics` 类提供面向对象的解析和序列化入口, 推荐优先使用:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# Lyrics 同时是序列容器
print(len(lyrics))  # 行数
print(lyrics[0].text)  # 第一行文本
print(lyrics[-1].text)

# 切片访问
first_three = lyrics[0:3]

# 序列化
lrc_output = lyrics.dumps()

# __str__ 等价于 dumps()
print(lyrics)
```

### 逐字歌词

解析逐字 (Enhanced LRC / SPL) 歌词:

```python
lrc_text = "[00:00.000]<00:00.249>风<00:00.467>透<00:00.617>过<00:00.689>人<00:01.078>潮<00:01.217>渐<00:01.408>渐<00:01.556>停<00:01.716>歇<00:01.867>的<00:02.016>下<00:02.339>雨<00:02.459>天[00:02.740]"

lyrics = llp.loads(lrc_text)
line = lyrics[0]

for word in line.content:
    print(f"  [{word.start} -> {word.end}] {word.content!r}")
    # [249 -> 467] '风'
    # [467 -> 617] '透'
    # [617 -> 689] '过'
    # [689 -> 1078] '人'
    # [1078 -> 1217] '潮'
    # [1217 -> 1408] '渐'
    # [1408 -> 1556] '渐'
    # [1556 -> 1716] '停'
    # [1716 -> 1867] '歇'
    # [1867 -> 2016] '的'
    # [2016 -> 2339] '下'
    # [2339 -> 2459] '雨'
    # [2459 -> 2740] '天'

# 行级时间: line.start=0, line.end=2740
# (行尾的 [00:02.740] 会被当作该行的结束时间, 并反写到最后一个词元的 end)
```

### 内容搜索 (contains_text / find_text)

按文本查找请使用显式方法: `in` 在四个模型上的历史语义各不相同
(`LyricToken` / `BasicLyricLine` 是子串, `LyricLine` 是词元相等, `Lyrics` 是行相等),
`"xxx" in <模型>` 保留旧行为但会发 `DeprecationWarning`:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

lyrics.contains_text("雨")  # 任一行 (含参考行) 是否包含该子串
matching = lyrics.find_text("雨")  # 命中的行对象列表
line = lyrics[0]
line.contains_text("雨")  # 只搜主行
line.contains_text("积雨云", include_reference_lines=True)  # 连参考行一起搜
```

子串判定区分大小写; 需要忽略大小写时请自行 `casefold()` 后再比较.

### 参考行 (Translation / Transliteration)

LRC 文件中, 紧跟在带时间标签行后面的无标签行, 或与主行的时间戳相同的行, 会被解析为参考行, 常用于存放翻译或音译:

```python
lrc_text = """
[00:01.910]歌に形はないけれど
[00:01.910]虽然歌声无形
"""

lyrics = llp.loads(lrc_text)

line = lyrics[0]
print(line.text)  # "歌に形はないけれど"
print(line.reference_lines[0][0].content)  # "虽然歌声无形"
```

### 合并歌词

将两份歌词 (如原文和翻译) 按时间标签合并:

```python
main = llp.loads("[00:33.810]帰り道は夕日を背に\n[00:39.580]君の少し後ろを歩く\n")
translation = llp.loads(
    "[00:33.810]背着夕阳走在返家的路上\n[00:39.580]跟在你的后面一起走着\n"
)

# combine 方法: 翻译行挂到同时间点的 reference_lines 中
combined = main.combine(translation)

# 也可以用 + 运算符; 注意 + 固定使用 other_as_refline_only=False,
# 即另一方中时间戳对不上的行会作为新行保留, 不会被丢弃
combined = main + translation

for line in combined:
    print(line.text)  # 主歌词
    for ref in line.reference_lines:
        ref_text = "".join(w.content for w in ref)
        print(f"  -> {ref_text}")  # 参考行

# other_as_refline_only=False 时, 翻译中找不到对应时间点的行会作为新行保留
combined = main.combine(translation, other_as_refline_only=False)
```

### 字典序列化 (to_dict / from_dict)

所有数据模型都支持字典序列化, 方便 JSON 传输和 API 对接:

```python
import lemony_lrc_parser as llp
from lemony_lrc_parser import Lyrics

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

### 拷贝

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

### 选项

#### 解析选项

```python
import re
from lemony_lrc_parser import Lyrics, ParseOptions

lrc_text = "[00:01.000]Hello\n[00:05.000]World\n"

lyrics = Lyrics.loads(
    lrc_text,
    options=ParseOptions(
        fill_implicit_line_end=True,  # 是否填充隐式行尾时间
        line_filter=r"纯音乐.*?请欣赏",  # 黑名单过滤 (统一按正则理解, str 会被自动 compile)
        # line_filter=re.compile(r"纯音乐.*?请欣赏"),  # 也可直接传入已编译的正则
    ),
)

# lyrics[0].end == lyrics[1].start == 5000
```

`line_filter` 的内容是正则表达式: 传入的字符串会被 `re.compile` 编译, 之后用
`pattern.search` 匹配每行文本, 命中的行会被丢弃. 若需要精确的子串匹配 (而非正则),
请用 `re.escape(...)` 包一层, 例如 `line_filter=re.escape("a.c")`.

过滤只按**主行**文本判定: 与主行同一时间戳的参考行 (翻译/音译) 会随主行一起被
丢弃, 即使它自身的文本并不匹配.

#### 序列化选项

通过 `SerializationOptions` 控制序列化行为:

```python
from lemony_lrc_parser import Lyrics, SerializationOptions

output = lyrics.dumps(
    options=SerializationOptions(
        with_metadata=True,  # 是否输出 metadata 段
        use_bracket_for_byword_tag=False,  # 逐字标签使用 [...] 还是 <...> (默认; True 不保证往返, 见下)
        line_tag_decimal_length=3,  # 行标签毫秒位数 (默认 3)
        word_tag_decimal_length=3,  # 逐字标签毫秒位数 (默认 3)
        line_separator="\n",  # 行间分隔字符串 (默认 "\n", 设为 "" 可省去空行)
    ),
)
```

#### 小数位长

默认 `line_tag_decimal_length=3`、`word_tag_decimal_length=3`, 输出格式如
`[00:01.000]`、`<00:01.050>`, 保留完整的毫秒精度.
若设为 `2`, 小数部分表示百分秒 (如 `[00:01.00]`), 属于**有损截断** (例如 555ms
会被截断为 55, 解析回来变成 550ms), 需要按需权衡 (部分老软件可能只支持百分秒).

#### 往返保真度

`dumps()` 的输出在重新解析后应当还原原对象. 已知的有损写法有两类 (见下表): 属于选项
自身代价的照常写出并 warning (与 metadata 的处理一致), 确实无法用 LRC 表达的则跳过
并记 debug 日志.

| 情形 | 写出的文本 | 重新解析的结果 |
| --- | --- | --- |
| `use_bracket_for_byword_tag=True` 且首词元晚于行首 | `[00:01.000][00:01.500]hello` | 两行, 文本重复 |
| 无正文的参考行 (逐字时间也一起丢) | 不写出, 只有 debug 日志 | 该参考行消失 |

`dumps` 的输出是"最多一轮之后的不动点": `d2 = dumps(loads(d1))` 与
`d3 = dumps(loads(d2))` 必定相等. 当前实现下 (含 2 万份随机语料与 6622 份真实
文件) 首轮就已经是不动点.

另外, 行尾时间若由逐字标签推断而来且与行首时间矛盾 (`end <= start`), 该推断会被
丢弃 (`line.end` 置回 `None`) 并产生 warning —— 解析器不会产出 `validate()` 判为
error 的行.

### 关于 SPL

[SPL (Salt Player Lyrics)](https://moriafly.com/standards/spl.html) 是目前唯一把
"LRC 家族多年踩到的兼容性问题"写成条文的文档, 本库把它当作 LRC 语义的参照物.
逐条对照的用例在 [`tests/test_spl_conformance.py`](tests/test_spl_conformance.py),
语料统计与调研过程在 [`docs/research.md`](docs/research.md).

解析端完全按 SPL 的地方:

- 时间戳数字规范 (分 1-3 位 / 秒 1-2 位 / 毫秒 1-6 位; 不足 3 位视为在后位省略 `0`,
  即 `[00:01.5]` 是 1.5 秒、`[00:01.02]` 是 1.02 秒).
- 显式行尾: 同行内的 `[start]text[end]`, 以及独立的空标记行 `[end]`.
- 空正文行是"纯结束标记": 它不产生歌词行, 也不参与翻译识别, 只给上一行补 `end`.
  因此 `[00:20.82]` + `[00:20.82]lyrics` 得到的是"上一行在 20.82s 结束"加"一句正常
  歌词", 而不是"一条空行 + 它的翻译".
- 重复行简写 `[t1][t2]text`; 翻译的同时间戳识别 (可不紧挨) 与省略时间戳写法 (可多行).
- 逐字标记 `[...]` 与 `<...>` 两种写法, 以及 2026-09-19 修订新增的"延迟首字"
  `[行标签]<首字标签>文本`.
- 逐字标记必须递增且落在 `[行首, 行尾]` 内, 越界或乱序的标记被忽略 (两侧文本合并,
  不丢字) 并记 warning.

有意偏离 / 标准未覆盖的地方:

- 分 4 位 (`[1234:00.000]`) 比标准宽松地接受; 秒 ≥ 60 按字面折算并 warning.
- 毫秒写 4-6 位时按"秒的小数部分"截断到毫秒 (`[00:01.450000]` → 1450ms), 而不是
  按标准的字面读成 450000 毫秒. 标准内部对这两种读法有歧义, 真实语料里 4-6 位出现
  0 次.
- 标签之后只剩空白算正文 (见上面的往返保真度), 标准只说了"不接任何文本内容".
- `[行标签][首字标签]文本` 在整行标签非递减、且正文里还有其它时间标签时, 按"首字延迟"
  读成一行 (如 `[00:05.650][00:05.730]徘[00:06.130]徊[00:06.450]`; 标准"局限性"一节
  按重复行读); 正文里没有其它时间标签的 `[t1][t2]text` 仍按重复行简写读成两行.
  真实语料里 199 行这种写法有 197 行的两个标签只差 0.1-1.3 秒.
- 整行只有尖括号标签 (如 `<00:01.000><00:02.000>`) 保留为一条空正文行, 用于承载
  空字幕 cue; `dumps` 也用同一形式写回.
- 默认不填充隐式行尾 (`end=None` 表示"未知"), 需要 SPL 的"持续到下一行开始"语义时
  用 `ParseOptions(fill_implicit_line_end=True)`; 字幕导出默认就是这种语义.

### 元数据语法

`[key: value]` 只有**整行**都由该形式构成时才算 metadata: 正文中间的
`[key: value]` 不会把整行吞掉 (例如 `Return [to: sender] now` 仍是一行歌词或参考行).

value 里的方括号必须**配对**:

```python
import lemony_lrc_parser as llp

llp.loads("[al: Album [Deluxe]]\n[00:01.000]x\n").metadata
# {'al': 'Album [Deluxe]'}   ← 原样保留 (取"配对的第一个 ]"作为边界)
```

不平衡的写法 (如 `[ti: 50% ]off]`、`[ti: a [b]`) 无法确定 value 边界, 整行按普通
正文处理, 写出这类 value 时也会 warning.

常见 key 的类型提示见 `MetadataKey` / `MetadataDict` / `COMMON_METADATA_KEYS` ——
它们只是提示: 库不限制 key 的取值集合 (真实语料里常见 `ly`、`mu`、`total`、`tool`),
只有 `validate()` 会按 `[A-Za-z][A-Za-z0-9]{0,15}` 检查 key 格式.

### 偏移

使用 `Lyrics.apply_delta(ms)` 应用时间偏移, ms 会*直接加到*每个标签的时间戳上,
这意味着传入*正数*偏移值会导致歌词整体*延后*出现, 反之同理.

也可以使用重载的 `>>` / `<<` 运算对歌词进行偏移.

如果应用 offset 会导致任意时间戳变为负数, 将抛出 `TimestampUnderflowError`, 由调用方自行处理.

#### 应用偏移

通过 `Lyrics.apply_delta(ms)` 对时间戳应用偏移, 返回一个新对象:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads(lrc_text)

# 正数 → 歌词延后出现 (等价于 lyrics >> 500)
shifted = lyrics.apply_delta(500)

# 负数 → 歌词提前出现 (等价于 lyrics << 500)
shifted = lyrics.apply_delta(-500)

# 使用 << / >> 运算符
shifted = lyrics >> 500  # 延后 500ms
shifted = lyrics << 500  # 提前 500ms

# shifted 的时间戳已被整体偏移, 原始 lyrics 不受影响
```

如需在序列化前偏移时间戳, 请先调用 `apply_delta()` 再序列化返回的副本.
如果你的偏移量来自歌词文件元数据, 你可能还需要记得手动清理 `lyrics.metadata` 中的偏移值.

#### 与 LRC offset 元数据的符号差异

LRC 没有一个标准的符号语义, 但:

- LRC 的 `[offset: +N]` 按社区文档与*主流*实现是"歌词整体**提前** N 毫秒",
  即时间戳 `-= N` ([调研](docs/research.md));
- 本库的 `apply_delta(+ms)` 是"时间戳 `+= ms`", 即歌词**延后**.

所以从 metadata 应用 offset 的正确写法是取负号:

```python
from lemony_lrc_parser import Lyrics

lyrics = Lyrics.loads("[offset: 500]\n[00:10.000]hello\n")
shifted = lyrics.apply_delta(-int(lyrics.metadata["offset"]))
print(shifted[0].start)  # 9500 —— 提前了 500ms
```

本库不会自动应用 offset (显式优于隐式), 需要由使用者自行处理.

也可以通过 `min_timestamp` / `max_timestamp` 快速检查歌词的时间范围:

```python
from lemony_lrc_parser.offset import min_timestamp, max_timestamp

lyrics = Lyrics.loads(lrc_text)
print(min_timestamp(lyrics))  # 最小时间戳 (ms), 无时间戳时为 None
print(max_timestamp(lyrics))  # 最大时间戳 (ms), 无时间戳时为 None
```

### 校验

使用 `lyrics.validate()` 检查歌词数据一致性:

```python
from lemony_lrc_parser import Lyrics, ValidationOptions

lyrics = Lyrics.loads(lrc_text)

# 返回问题列表
issues = lyrics.validate()
for issue in issues:
    print(f"[{issue.severity}] {issue.code}: {issue.message}")

# strict 模式: 遇到 error 级问题时抛出 InvalidLyricsError
issues = lyrics.validate(options=ValidationOptions(strict=True))
```

检查项包括:

- 歌词行是否按时间升序排列 (`unsorted`)
- 是否存在重复时间戳 (`duplicate-start`)
- 行结束时间是否晚于开始时间 (`end-not-after-start`)
- 逐字 token 时间是否单调递增 (`token-nonmonotonic`)
- 逐字 token 自身区间是否合法 (`token-end-not-after-start`)
- 逐字 token 是否在所属行的时间范围内 (`token-before-line-start` / `token-after-line-end`)
- metadata key 格式合法性 (`invalid-metadata-key`)
- `offset` 元数据是否可解析为整数 (`offset-not-int`)

`error` 与 `warning` 的分工: 由解析器写出的数据不会包含任何 `error` 级问题
(见 `tests/test_roundtrip_matrix.py` 的不变量测试), 因此出现 `error` 通常意味着
调用方手工构造了自相矛盾的对象.

### 命令行

本库不注册 console script, 用 `python -m lemony_lrc_parser` 调用 (与
`python -m json.tool` 同样的形态):

```bash
# 验证 LRC 文件数据一致性
python -m lemony_lrc_parser validate song.lrc
python -m lemony_lrc_parser validate --strict song.lrc    # 有 error 时退出码为 1

# 整体时间偏移 (毫秒)
python -m lemony_lrc_parser offset --delta 500 song.lrc           # 输出到 stdout
python -m lemony_lrc_parser offset --delta -200 song.lrc -o out.lrc  # 输出到文件

# 转换为字幕格式
python -m lemony_lrc_parser to-srt song.lrc
python -m lemony_lrc_parser to-webvtt song.lrc -o song.vtt
```

### 字幕格式转换 (SRT / WebVTT)

`Lyrics` 可与常见的简单字幕格式互相转换, 便于把歌词用于视频字幕制作,
或把已有字幕导入为歌词:

```python
from lemony_lrc_parser import Lyrics, SubtitleOptions

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
    fill_end_from_next=True,  # 缺少行尾时间时, 用下一行的 start 补齐
    default_duration_ms=5000,  # 无法推断时长时使用的默认时长 (也用于修正非法区间)
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

## 参考资料

- [CHANGELOG](CHANGELOG.md) —— 版本变更历史.
- 开发笔记 ([索引](docs/feature-ideas.md)):
  [路线图](docs/roadmap.md) ·
  [设计与取舍](docs/design.md) ·
  [风险与不计划](docs/risks.md) ·
  [调研与语料数据](docs/research.md)
- [LRC Wikipedia](https://en.wikipedia.org/wiki/LRC_%28file_format%29)
- [SPL Specification](https://moriafly.com/standards/spl.html)

## UwU?

UwU!

## License

MIT License
