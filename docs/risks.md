# Risks（风险与不计划项）

本文件记录**已知会咬人的地方**与**明确不做的事**。
调研依据见 [`research.md`](research.md)，取舍结论见 [`design.md`](design.md)。

---

## 可能的问题与风险

### 1. LRC 缺少统一标准，严格模式容易误伤真实文件

LRC 野生格式很多。过早把 parser 默认行为改严，会破坏兼容性。

建议：

- 默认继续宽松。
- `strict=True` 明确 opt-in。
- 宽松解析 + `validate()` 报告问题，是更稳的路线。

### 2. `Lyrics` 继承 `UserList`，用户可绕过不变量

例如用户可直接插入乱序行，或把非预期对象放进列表。

建议：

- 文档说明“直接 list 操作不会自动 validate / sort”。
- 提供 `add_line()` / `sort_inplace()` / `validate()`。
- 不建议强行重写所有 list mutator，成本高且容易违反用户预期。

### 3. 行尾时间语义不稳定

LRC 行尾标签可选，SRT / WebVTT 必须有 end。这会导致导出字幕时需要推断。

建议：

- `SubtitleOptions` 当前方向正确。
- `duration`、`lines_in_range`、`stats` 都必须明确 `end is None` 的处理策略。

### 4. 逐字标签与行标签组合存在歧义

连续行首时间标签 + 行内逐字标签时，可能既像折叠行，又像"行标签 + 首字标签"的逐字行。

现状（0.4.0）：用 SPL 的"逐字标记必须递增"当判据 —— 整行标签**非递减**时按首字延迟的
逐字行读成一行；出现**递减**时按重复行简写展开，第二行里越界的逐字标记按 SPL 忽略。
真实语料里 199 行这种写法有 197 行是非递减的（两标签相差 0.1-1.3 秒），所以这个判据
在真实数据上站得住；剩下 2 行（`RFFFF`、`哀歌`，差值 15 秒以上）会被读成"延迟 15 秒的
首字"，属于已知代价。统计见 [research.md](research.md#其余差异)。

建议：

- strict mode 下把"非递减但差值过大"的歧义作为 warning 报告出来。

### 5. metadata 是 `dict[str, str]`，无法表达重复 tag 与注释 tag

如多个 `[#...]` 注释或重复 `[ar:...]`，dict 会覆盖旧值。

建议：

- 暂时不要为了冷门方言破坏简单模型。
- 如确有需求，可未来增加 `metadata_items: list[tuple[str, str]]` 或 source map，但这属于较大模型变更。

### 6. JSON schema 一旦公开可能形成兼容负担

`to_dict()` 已经存在，若增加 `to_json()`，用户可能把它当稳定存储格式。

建议：

- 文档标注“用于传输 / 调试，非长期稳定文件格式”，除非项目决定正式版本化 schema。
- 若要长期稳定，应添加 `schema_version`。

### 7. 模糊合并可能产生错误关联

时间接近不代表歌词对应，尤其在重复副歌、短句、rap 密集歌词中。

建议：

- 默认 `tolerance_ms=0`。
- 模糊匹配结果最好可审计：返回 unmatched / matched-by-fuzzy 信息。
- CLI combine 中应输出统计。

### 8. CLI 会扩大维护面

CLI 涉及参数设计、路径、编码、退出码、错误输出、Windows shell 兼容等问题。

建议：

- 第一阶段只做少量命令。
- CLI 尽量薄封装核心库能力。
- 为退出码写测试。

### 9. ASS / 高级字幕格式可能偏离项目定位

ASS 支持样式、定位、特效，完整支持会显著扩大复杂度。

建议：

- 如要做，先只支持纯文本导出。
- 不承诺样式往返。
- 低优先级。

### 10. 过多便利 API 可能让核心模型变胖

`Lyrics` 已经是聚合层，继续增加 stats、search、normalize、diff、path I/O 等方法会让类变大。

建议：

- 高频能力放 `Lyrics` 方法。
- 低频 / 工具型能力可放独立模块函数。
- 保持顶层公共 API 有节制。

### 11. 与 SPL 的几处已知差异可能被当成 bug 报告

逐条对照 [SPL](https://moriafly.com/standards/spl.html) 之后仍有 6 处有意偏离
（分 4 位、毫秒 4-6 位的读法、标签后只剩空白、`[行标签][首字标签]` 的读法、默认不填
隐式行尾、尖括号空行）。理由与语料实测值写在 README「与 SPL 的一致性」与
[research.md](research.md#其余差异)，逐条钉在 `tests/test_spl_conformance.py` 里。

建议：

- 收到相关报告时先对照那张表：多数是"标准本身有歧义"或"真实语料另有共识"。
- 若要改动其中任何一条，先补语料统计再改行为。

---
## 已关闭 / 不计划

- **[NEW-META-ESCAPE] metadata 引入反斜杠转义**

  关闭理由：LRC 家族没有官方规范，也没有任何社区实现定义转义语法
  （[AMLL 的格式文档](https://amll.dev/en/guides/lyric/formats) 明确写了"`<`/`>`
  的转义没有官方标准，未匹配的一律当普通文本"）。引入 `\]` 只会：
  1. 自造方言——其它播放器会把反斜杠当字面量显示出来；
  2. 破坏既有 value 的语义（含反斜杠的 value 会被二次解释）；
  3. 让"写出的文件"与"读入的文件"不再是同一种格式。

  替代方案是**配对平衡**（已在 0.4.0 实现）：`[al: Album [Deluxe]]` 原样往返，
  不平衡时整行按正文处理并告警。作为参照，ffmpeg 的 `lrcdec.c` 用
  `strchr(line.str, ']')` 取**第一个** `]` 收尾，于是这类 value 会被截断成
  `Album [Deluxe`——比我们的行为更糙，但也说明社区对此并无共识。
  完整调研见 [research.md](research.md#metadata-语法)。

- **[F-DICT-JSON] `to_json()` / `from_json()`**

  关闭理由：`to_dict()` / `from_dict()` 已经够用，产出的 dict 交给调用方自行
  `json.dumps()`；再包一层只会把"JSON schema 是否稳定"变成库的长期兼容负担
  （见本条目前面的风险 6）。

- **[NEW-INTERP] 逐字时间线性插值填充**

  关闭理由：插值是播放器或音频强制对齐工具的职责，不适合放在解析器中。

- **[NEW-OFFSET-META] `apply_delta` 自动清理 `metadata.offset`**

  关闭理由：显式优于隐式。可考虑新增显式 helper，但不应自动修改 metadata。
  另外 LRC 的 `offset` 与 `apply_delta` 的**符号相反**（前者正值=歌词提前），
  自动应用极易踩错方向，调研见 [research.md](research.md#offset-标签的正负语义)。

- **[NEW-ASYNC] 异步 I/O 支持**

  关闭理由：解析本质是 CPU 同步逻辑，异步 I/O 应由调用方处理。

---
