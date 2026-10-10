# 语义取舍

LRC 没有官方规范，下面每一条都是在"保真 / 易用 / 与其它实现兼容"之间挑了
一个。每条写现象、当前选择、理由，以及要改的话先动什么。

总原则：

- 默认宽松。真实世界的 LRC 很野，过早收严会误伤真实文件；更严的需求走
  `ParseOptions(strict=True)` 或 `validate()`。
- 不确定的地方告警而不是猜。
- 解析器不产出 `validate()` 判为 error 的数据。
- 以 [SPL](https://moriafly.com/standards/spl.html) 为语义参照，偏离处逐条
  记录（[对照表](../research/spl.md)）。

## 时间

- 内部精度是毫秒。输出 2 位尾数时有损截断（555ms 写成 `.55`，读回 550ms）。
- 时间标签接受 1-6 位尾数、1-4 位分钟；秒数越界（`[00:99.000]`）按字面折算
  并告警。尾数 4-6 位按"秒的小数部分"截断到毫秒，而不是 SPL 字面读法的
  "毫秒数"，理由见 [spl.md](../research/spl.md#有意偏离)。
- 尾数前的分隔符可以是 `.` 也可以是 `:`，所以 `[01:02:03]` 读作 1 分 2.03 秒，
  而不是 1 小时 2 分 3 秒；`[01:02:03.500]` 不是合法标签。见 roadmap PARSE-4。
- 能写出的最大时间是 `[9999:59.999]`，更大的时间戳 `dumps()` 抛
  `TimestampOverflowError`，而不是写出读不回来的标签。
- 行尾时间可选，`LyricLine.end is None` 是常态而不是异常。`duration` 此时也是
  `None`。需要"持续到下一行开始"时用 `ParseOptions(fill_implicit_line_end=True)`；
  字幕导出会自己推断（下一行的 `start` 或 `SubtitleOptions.default_duration_ms`）。
  涉及时长的新 API 都要写明 `end is None` 的处理。
- 由逐字标记推断出的行尾若不晚于行首，丢弃该推断并告警，词元自身的时间原样
  保留。

## 乱序与负时间戳

- 现象：真实文件里可能有 `start` 递减的行（语料 0 例，历史上见过），以及
  应用 offset 后变负的时间戳。
- 选择：解析端照原样保留，`validate()` 报告（`unsorted` 是 error，
  `duplicate-start` 是 warning）。`apply_delta()` 遇到下溢抛
  `TimestampUnderflowError`。

## 逐字标记

- 逐字标记必须落在 `[行首, 行尾]` 之内且递增（SPL）。越界或递减的标记被忽略，
  两侧文本合并，不丢字，并告警。
- 相邻标记相等视为正常写法（逐字行里空格词元与下一个词共享时间戳），静默
  合并，只记 debug。语料里相等 1917 次、递减 0 次。

## 多个行首标签加逐字标记

- 现象：`[t1][t2]文本<...>` 既可以是重复行简写，也可以是"行标签 + 延迟的
  首字标签"。
- 选择：整行标签非递减且正文里还有其它时间标签时，读成一行（首字延迟）；
  出现递减时按重复行展开，第二行里越界的逐字标记按 SPL 忽略。写出时规范化成
  SPL 的形式（中间标记 `<...>`，行尾 `[...]`）。
- 理由：语料里这种写法 199 行，197 行两标签相差 0.1-1.3 秒，按重复行读会得到
  两条几乎相同的行。SPL"局限性"一节的读法与此不同。
- 代价：剩下 2 行（差值 15 秒以上）会被读成"首字延迟 15 秒"。
  roadmap PARSE-1 打算对这种情况发报告事件。

## 空正文行

- 现象：只有时间标签、没有正文的行，如 `[00:20.82]`。可以读成"空行 / 清屏"，
  也可以读成"上一行到此结束"，两者文本同形。
- 选择：按 SPL 读作纯结束标记，给最近一行有正文的歌词补 `end`（已有显式行尾
  则忽略），找不到收尾目标就丢弃，不产生空歌词行。
- 理由：SPL 明文规定，且结束标记常与下一句同时间戳。读成空行时，下一句真实
  歌词会被挂成空行的翻译，语料里有 420 处（138 个文件）。
- 例外：整行只有尖括号标签（`<00:01.000><00:02.000>`）时保留为空正文行，
  这是 LRC 家族里唯一能无歧义承载空字幕 cue 的写法，`dumps` 也用这个形式写回。
- `[t1][t2]`（空正文 + 两个标签）按第一个能生效的标签收尾，即 `end = t1`，
  而不是读成"t1 到 t2 的空区间"，后者在 LRC 里没有专属写法。

## 空白

- 标签之后只剩空白时算正文：`[00:01.000]` 后跟两个空格，正文是 `"  "`。
  否则 `dumps` 写出的这种行无法往返。
- 没有标签的空白行是分隔符，重置参考行锚点。

## 参考行

- 没有时间标签、紧跟在歌词行后的行挂成该行的参考行（翻译、音译），与主行
  同时间戳的行也是。识别方式与 SPL 一致。
- 没有锚点的行按孤儿行告警丢弃。
- 没有正文的参考行（只剩逐字标记）不写出：它只能写成方括号开头的无正文行，
  而解析端会把那读成上一行的结束标记，既丢参考行又改上一行的时间。真实语料里
  这种参考行 0 条。要支持它只能造新语法。

## metadata

- 只有整行都由 `[key: value]` 构成时才算 metadata 行；正文中间的
  `[to: sender]` 不会把整行吞掉。
- key 规则：字母开头，字母数字，最多 16 位（`regex.METATAG_KEY_REGEX`）。
  `[#...]` 形式的注释因此不算 metadata。
- value 的边界由配对方括号决定：`[al: Album [Deluxe]]` 读作 `Album [Deluxe]`。
  不平衡时（`[ti: 50% ]off]`）整行按正文处理，不猜边界；写出这类 value 时告警
  但照常写出。不引入转义语法，理由见 [not-planned.md](not-planned.md)。
- 容器是 `Metadata`：有序，同名可重复。三种读法口径固定：
  - dict 视角（有损）：整个 `Mapping` 协议，即 `meta["ti"]`、`get()`、
    `keys()`、`values()`、`items()`、`len()`、`dict(meta)`、`to_dict()`，
    每个 key 一条，同名取最后一次出现。
  - 无损视角：`to_pairs()`、`getlist()`，按出现顺序给全部条目。
  - 写入：`add()` 追加，`set()` / `meta[k] = v` 替换（位置取首次出现处）。
- `items()` 守 `Mapping` 约定，而不是像 werkzeug `Headers` 那样返回全部条目：
  把 `Metadata` 当普通 `Mapping` 消费的代码（`for k, v in meta.items()`）不该
  因为重复项拿到同一个 key 两次。无损读取只走显式入口，与 httpx 的
  `multi_items()` 同一取向。
- 代价：`len(meta)` 与 `len(meta.to_pairs())` 不等。ty 对
  `Mapping | Iterable[tuple]` 的 isinstance 收窄会算错，所以 `Metadata.extend`
  用重载加 `object` 实现签名。调研见 [research/metadata.md](../research/metadata.md)。
- `[offset:]` 不自动应用，符号见 [research/offset.md](../research/offset.md)。

## 相等性与 `in`

- `Lyrics` 的相等性比较行序列加 metadata，metadata 按全部条目比，重复项与
  顺序都算数。与普通列表比较时只比行。这样 `loads(dumps(x)) == x` 才能当
  往返检查用。
- `str in <模型>` 在四个模型上语义各不相同（子串 / 词元相等 / 行相等），
  0.5.x 保留原行为但发 `DeprecationWarning`，0.6.0 起抛 `TypeError`。文本查找
  用 `contains_text()` / `find_text()` / `find_regex()`。

## 往返保真度

不变量（`tests/test_roundtrip_matrix.py`）：

1. 解析器的输出通过自己的 `validate()`。
2. `dumps` 最多一轮收敛：`dumps(loads(d))` 第二轮起不变。
3. 格式良好的语料 dump → load 后行结构不变。

已知有损的写法：选项自身的代价照常写出并告警
（`use_bracket_for_byword_tag=True` 且首词元晚于行首会读回两行）；无法用 LRC
表达的跳过并记 debug（没有正文的参考行）。字幕互转丢弃逐字标记与 metadata，
是格式差异，不算有损。

写回不保留原文件风格（行尾、尾数位数、空行），见 roadmap WRITE-1。

## 字典与 JSON

`to_dict()` / `from_dict()` 用于传输与调试，不是长期稳定的存储格式，没有
schema 版本。`to_dict()` 的 metadata 是有损的 dict 视角，无损导出用
`metadata.to_pairs()`。不提供 `to_json()`，见 [not-planned.md](not-planned.md)。

## Python 下限

`requires-python` 是 `>=3.9`，所以代码与测试不用 `zip(..., strict=True)`
（3.10+）。下限抬到 3.10 后交给 ruff 的 B905 统一处理。
