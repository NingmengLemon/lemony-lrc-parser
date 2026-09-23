# Changelog

本文件记录 `lemony-lrc-parser` 的版本变更. 格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/), 版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/).

> 历史版本条目按 `Added` / `Changed` / `Fixed` / `Removed` / `Docs` / `Tooling`
> 分类. 版本号与 git tag 一一对应 (`v0.4.0`), 由 CI 在版本号滚动时自动打 tag 并
> 创建 GitHub Release (预发布版本 `-aN` / `-bN` / `-rcN` 会标记为 prerelease).
> 功能规划见 [`docs/roadmap.md`](docs/roadmap.md), 设计与取舍见
> [`docs/design.md`](docs/design.md), 调研与语料数据见
> [`docs/research.md`](docs/research.md).

## [0.4.1] — 未发布

按 [SPL 标准](https://moriafly.com/standards/spl.html)（Salt Player Lyrics，
最近修订 2026-09-19）逐条对照之后的一轮语义修正。SPL 是目前唯一把 LRC 家族多年
踩到的兼容性问题写成条文的文档；对照结果与 6 处有意偏离见
[README「与 SPL 的一致性」](README.md#与-spl-的一致性) 与
[`docs/research.md`](docs/research.md#spl-对照2026-09-19-修订版)，逐条用例在
`tests/test_spl_conformance.py`。

> 语料回归：**全量 6622 份 .lrc**（58.6 万非空行）。空正文行 28836 条，其中 420 处
> （138 个文件）会把紧随其后、时间戳相同的真实歌词挤成"翻译" —— 本轮全部修掉，
> 28436 行拿到真实 `end`；改后解析异常 0、`validate()` 问题 0、`dumps` 不收敛 0。
> 另有 2 万份随机语料：三条往返不变量全过，且 `dumps` 首轮即为不动点
> （改前有 135/20000 需要第二轮）。

### Fixed

- **空正文行按 SPL 读作"纯结束标记", 不再产生空歌词行** (真 bug, 语料里 420 处).
  SPL 明文规定"时间戳后不接任何文本内容的行是纯粹的结束标记: 它不会产生一句新
  歌词, 也不参与翻译识别", 而且这种标记**常与下一句歌词使用相同的时间戳**.
  0.4.0 为它造了一条空正文行, 于是:

  ```
  [00:20.82]
  [00:20.82]フィクション
  [00:20.82]
  [00:20.82]喜欢虚构的
  ```

  第二行被挂成空行的 `reference_lines`(翻译), `line.text` 是空串 ——
  按行遍历的消费者整行丢失. 现在空标记只给"最近一行有正文的歌词"补 `end`
  (已有显式行尾则忽略), 找不到收尾目标 (文件首行、目标行开始时间不晚于标记)
  就丢弃; 解析器不再产出空正文行.

- **越界逐字标记按 SPL 忽略, 行标签/行尾标签为准** (取代 0.4.0 的"按首个词元
  归位"). SPL 规定逐字标记必须递增且落在行开始与结束时间之间, 否则该标记被忽略.
  于是:
  - `[00:30.000]<00:10.000>hi` 现在落在 `30000ms` (文件声明的时间), 标记被丢弃;
  - `[00:20.000]a<00:23.000>b<00:25.000>c[00:24.000]` 保住行尾 `24000ms`,
    不再反过来把行尾标签当成乱序丢掉;
  - 丢弃标记时两侧文本合并, 不丢字, 并记 warning.
  真实语料里越界 0 例, 但这让解析器不再产出自相矛盾的词元时间
  (`validate()` 的 `token-before-line-start` / `token-after-line-end` 不再由解析器
  自己触发).

- **同行内的行尾标签不再被"重复标签合并"吃掉**. 当行尾时间与末词元时间相同
  (`[00:02.000]<00:10.000>hello[00:10.000]`) 时, 它此前会被当成重复标签合并,
  整行的结束时间丢失; 现在由 `parser._apply_explicit_line_end()` 按已知的行尾
  时间补上.

- **没有正文的参考行不再写出** (0.4.0 只跳过了"完全为空"的参考行). 只有逐字标签、
  没有正文的参考行写成孤立行后, 解析端按 SPL 会把它读成上一行的结束标记 ——
  既丢参考行又改上一行的时间范围, 因此改为跳过并记 `debug`.

### Changed

- **"多个行首标签 + 正文还有标签"的歧义改用 SPL 的递增规则判定**.
  SPL 要求逐字标记递增, 于是:
  - 整行标签**非递减** → 按"行标签 + 首字标签"的逐字行读成一行 (首字延迟);
  - 出现**递减** → 按重复行简写展开, 第二行里越界的逐字标记按 SPL 忽略.
  依据: 真实语料里 199 行这种写法有 197 行是非递减的 (两个标签相差 0.1-1.3 秒),
  按重复行读会得到两条几乎相同的行. 0.4.0 一律按单行读, 会丢掉真实重复行的第二次
  出现 (SPL"局限性"一节的例子), 现在两种都能正确处理.
  写出时这种写法会被规范化成 SPL 的规范形式 (中间标记 `<...>`、行尾 `[...]`).

- **空正文行改用尖括号写出**. `dumps()` 遇到没有正文的行时写
  `<00:01.000>` / `<00:01.000><00:02.000>`, 而不是 `[00:01.000][00:02.000]` ——
  后者在 SPL 下是"上一行的结束标记", 重新解析会静默改掉上一行的时间范围.
  尖括号写法是 Enhanced LRC 的扩展, 也是空 SRT cue 的形状, `dumps` → `loads`
  因此成为严格不动点.

- **序列化器不再写出解析端必然会忽略的越界逐字标记** (标记落在
  `[line_start, line_end]` 之外), 这样自己写出的文件重新解析时不会再触发
  "越界标记被忽略"的 warning.

### Added

- **SPL 一致性测试** `tests/test_spl_conformance.py`: 把
  [SPL 标准](https://moriafly.com/standards/spl.html) 的每条可判定规则钉成用例
  (时间戳数字规范、显式/隐式行尾、空正文结束标记、重复行简写、翻译的三种识别、
  两种逐字括号写法、延迟首字、越界标记忽略), 外加"有意偏离"的显式规格.

### Docs

- `README.md` 新增"与 SPL 的一致性" (完全一致的部分 / 6 处有意偏离), 并更新
  "往返保真度"表 (空正文行不再是有损场景).
- `docs/research.md` 新增"SPL 对照 (2026-09-19 修订版)": 修订内容、空正文行的语料
  统计、逐条差异对照表, 以及"毫秒 4-6 位"这条标准自身歧义的两种读法.
- `docs/design.md` 的"待决策"第 1、2 条 (空正文行语义、没有正文的参考行) 按 SPL
  收敛; `docs/risks.md` 第 4 条更新为现有的递增判据, 新增第 11 条 (与 SPL 的差异
  可能被当成 bug 报告); `docs/roadmap.md` 记入 `NEW-SPL-CONFORM`.

## [0.4.0] — 2026-09-21

`0.4.0b0` / `0.4.0b2` / `0.4.0b3` 是这一轮开发中的预发布快照, 下面是它们之后的
两轮代码审查修复. `0.4.0` 本身按**正式版**发布: 项目还在 `0.x`, 语义化版本里
`0.x` 已经自带"接口可能变"的含义, 再叠一层 beta 只会让版本号失去信息量.

> 本轮的改动在一份真实语料上做过只读回归: **6536 份**与音频同名的 `.lrc`
> (33 万行, 全部 UTF-8, 其中 410 份带 metadata、1666 行逐字、27023 行空占位),
> 解析异常 **0**、`validate()` 问题 **0**、往返不变量违例 **0**;
> 相邻时间标签"相等" 1917 次 (改为 `debug`, 不再刷 warning)、"递减" 0 次、
> 行首重复标签 0 次. 另外, 因行首标签与词元矛盾需要归位的行 **0** 行、
> 完全为空的参考行 **0** 条、value 含方括号的 metadata **0** 条 ——
> 这三处修复对这份语料是纯防御性/纯新增能力, 不改变任何真实文件的解析结果.
> 明细见 [`docs/research.md`](docs/research.md) 的"真实语料基线".

### Fixed

- **行首标签与首个词元矛盾时按首个词元归位, 不再丢弃整行** (A2).
  `[00:30.000]<00:10.000>hi` 这样的行此前整行被丢弃, 紧随其后的翻译/音译行也
  因失去锚点一起消失; 现在行落在 `10000ms` (首个词元时间), 只丢标签本身.
  多个标签归位到同一时间点时只注册一次, 不会自我复制成参考行.
  (0.4.1 起改为按 SPL 忽略越界标记, 见上.)

- **解析器不再产出 `end <= start` 的行** (第一轮审查 A1).
  行尾时间由最后一个词元"推断"而来; 若推断结果不晚于行首 (行尾标签与行首标签
  相同, 如 `[00:01.000]text[00:01.000]`), 现在丢弃该推断 (置回 `None`) 并记
  warning. 此前这类行会被 `validate()` 判为 error, 于是
  `lemonyrics validate --strict` 会拒绝解析器自己写出的文件.
  词元自身的 `start` / `end` 原样保留, 不丢数据.

- **metadata 的整行判定不再被正则回溯绕过** (A3).
  `[ti: song]extra[ar: x]` 曾被整体当成 metadata (守卫里的 `.*?` 把 `extra` 吸进
  value), 而提取阶段 (`finditer`) 又给出另一组结果, 于是中间的正文被静默吞掉.
  判定与提取现在共用同一个扫描器, 不可能再给出不同答案.

- **`combine()` 对"可迭代但没有一条 `LyricLine`"的入参报错** (此前静默 no-op):
  `dict` / `bytes` / 生成器都会抛 `TypeError`, 真正的空容器仍是合法 no-op;
  校验移到改动 `self` 之前, 避免"改了一半再报错".

- **`ParseOptions.line_filter` 在构造之后再被赋字符串也能工作**
  (此前会在解析时炸 `AttributeError: 'str' object has no attribute 'search'`).

- **CLI 退出码统一由 `main()` 决定**: `_read_lrc()` 改为返回 `Lyrics | None`,
  不再混用"返回码"与 `SystemExit` 两套控制流.

- **序列化器不再为"完全空的参考行"写出孤立行标签** (解析端会把它当成已存在的
  时间点而忽略, 只会让 `dumps` 的输出不稳定); 只有逐字标签、没有正文的参考行
  照常写出.

### Changed

- **metadata value 支持配对平衡的方括号** (还原原始意图).
  `[al: Album [Deluxe]]` 现在解析为 `value = "Album [Deluxe]"`, 而不是截断成
  `Album [Deluxe` (社区真实写法, 参见 rmpc#519). value 边界由"配对方括号"确定:
  遇到 `[` 深度 +1、`]` 深度 -1, 深度回到 0 的那个 `]` 才收尾.
  - 方括号**不平衡**时 (如 `[ti: 50% ]off]`、`[ti: a [b]`) 整行不算 metadata,
    按普通正文处理 —— 边界无法确定, 与其猜不如不猜.
  - 由此 `METATAG_REGEX` 常量被移除: Python `re` 无法表达"配对", 保留一个
    名不副实的模式只会制造第二套规则. 整行判定改由
    `parser._parse_metatag_line()` 扫描完成; key 规则仍统一来自
    `regex.METATAG_KEY_REGEX`.
  - 往返告警同步改为"方括号不配对"判据 (`_utils.is_bracket_balanced`).

- **`str in <模型>` 的歧义用法改为发 `DeprecationWarning`** (行为不变).
  同一个 `in` 在不同模型上历史语义各不相同 (子串 / 词元相等 / 行相等), 极易误读,
  现在引导到显式的文本查找 API:
  - 新增 `LyricToken.contains_text()` / `BasicLyricLine.contains_text()` /
    `LyricLine.contains_text(include_reference_lines=False)` /
    `Lyrics.contains_text()` / `Lyrics.find_text()`.
  - `in` 的行为保持原样: `BasicLyricLine` 仍是子串, `LyricLine` 仍是词元相等
    (对 `str` 恒为 `False`), `Lyrics` 仍是行相等 (对 `str` 恒为 `False`).

- **相邻时间标签"相等"不再按 warning 打扰用户**: 相等 (逐字行里空格词元与下一个
  词共享时间戳) 视为正常写法, 合并后只记 `debug`; 只有真正递减的乱序标签才
  warning. 依据: 6536 份真实 .lrc 语料里"相邻相等"出现 1917 次, "递减" 0 次.

- **`Lyrics.load()` 去掉多余临时变量**; `Lyrics` / `BasicLyricLine` docstring
  写明拷贝语义 (构造与切片深拷贝, `append` / `extend` 存引用).

### Added

- **常见 metadata key 的类型提示** (不强制): `MetadataKey` (`Literal`)、
  `MetadataDict` (`TypedDict`, `total=False`)、`COMMON_METADATA_KEYS`.
  `Lyrics.metadata` 运行时仍是普通 `dict[str, str]`, 非标准 key (真实语料里的
  `ly` / `mu` / `total` / `tool` 等) 照常可用.
- **往返保真度测试矩阵** `tests/test_roundtrip_matrix.py`: 三条不变量 ——
  解析器输出必须通过自己的 `validate()`、`dumps` 最多一轮收敛、格式良好语料的
  dump→load 行结构稳定; 语料 = 手写用例 + 固定种子随机语料.
- **CI**: `.github/workflows/ci.yml`, Python 3.9–3.14 矩阵跑 pytest, 另跑
  `ruff check` / `ruff format --check` / `mypy` / `ty check`, 校验 sdist 内容,
  并新增"最低依赖"两个作业 (`--resolution lowest-direct` + 把
  `typing-extensions` 钉到声明下限重跑测试).
- **发布流程**: `.github/workflows/release.yml` —— 版本号一旦滚动, 就在该 commit
  上打 `v<version>` tag 并发 GitHub Release, Release 正文自动取自本文件对应段落,
  sdist/wheel 作为附件; `-aN` / `-bN` / `-rcN` 自动标记 prerelease, 同日重复推送
  不会重复发布.
- **sdist 内容守卫** `tools/check_sdist.py`.

### Docs

- `README.md`: 修正逐字示例里错误的 `[3000 -> None] 'up'` (实为 `3500`)、补齐
  示例缺少的 import、校验项清单补上 `token-end-not-after-start`; 新增"往返保真度"
  与"与 LRC `[offset:...]` 的符号差异"两节 (后者说明 `apply_delta(-offset)` 的
  原因, 并指向调研).
- 文档按"问题类型"重组: `docs/feature-ideas.md` 变成索引,
  正文拆成 [`roadmap.md`](docs/roadmap.md) / [`design.md`](docs/design.md) /
  [`risks.md`](docs/risks.md) / [`research.md`](docs/research.md);
  历史版本迁到本文件; 去掉手写目录 (交给编辑器导航).
- 新增调研: metadata 的 `]` 处理与转义可行性、同名 key 与 HTTP 头容器设计的对照、
  `offset` 正负语义 (含一次真实实现的符号修正案)、时间标签的宽松形式.
- `docs/design.md` 的"待决策 / 已知取舍"改成"现象 → 为什么绕 → 当前选择 →
  若要改需要动什么"四段式, 便于下次决策时不用重新推一遍.

### Tooling

- `pyproject.toml` 补齐 `[tool.ruff]` (`target-version = "py39"`, 规则集
  `E/F/W/I/UP/B/SIM/C4/RET/PIE`)、`[tool.pytest.ini_options]`、
  `[tool.mypy]` (`strict = true`, 覆盖 `src` / `tests` / `tools`)、
  `[tool.coverage.*]` (branch 覆盖), 并显式声明
  `[tool.hatch.build.targets.sdist] include`.
- **`typing-extensions` 依赖按 Python 版本分档**: `<3.15` 上的下限从 4.14.0 降到
  本库真正用到的版本 (实测各版本的下限见下), 3.15 起仍需 `>=4.14.0`.
- 显式声明 sdist 内容的原因: hatchling 默认会收录工作区里"未被 VCS 忽略"的目录,
  曾把构建缓存 `.uv-cache/` (427 项, 含 `Scripts/python.exe`) 打进 sdist
  (本地 870 KB → 175 KB). `.gitignore` 补上 `.uv-cache/`.
- `parser.py` 两处"防御性但不可达"的分支加 `# pragma: no cover`; 补齐
  `ruff format` 漏网文件; 负例测试补上 `# type: ignore[...]` / `# ty: ignore[...]`.

## [0.4.0b3] — 2026-07-25

### Added
- 数据一致性验证子系统 `validation.py`: `ValidationIssue` / `ValidationOptions` /
  `ValidationSeverity` / `validate_lyrics()`, 以及 `Lyrics.validate()`
  (`strict=True` 时遇 error 抛 `InvalidLyricsError`). 检查排序、重复 `start`、
  `end <= start`、词元单调性与越界、metadata key 合法性、`offset` 可解析性.
- CLI 入口 `lemonyrics` / `python -m lemony_lrc_parser`: `validate [--strict]` /
  `offset --delta` / `to-srt` / `to-webvtt`.
- `InvalidLyricsError.line_no` / `.raw_line`: 解析错误与 warning 日志都带行号.

### Fixed
- 歧义行首标签 (`[00:05.000][00:30.000]<00:10.000>hi`) 不再把锚点指向未注册的
  时间点.

## [0.4.0b2] — 2026-07-21

### Added
- SRT / WebVTT 互转: `Lyrics.to_srt()` / `from_srt()` / `to_webvtt()` /
  `from_webvtt()`, 顶层 `dump_srt` / `parse_srt` / `dump_webvtt` / `parse_webvtt`,
  以及 `SubtitleOptions`.
- 字典序列化与深拷贝: `to_dict()` / `from_dict()` 覆盖 `Lyrics` / `LyricLine` /
  `BasicLyricLine` / `LyricToken`; `copy()` 系列方法.

### Changed
- **破坏性**: `Lyrics` 改为纯 `UserList[LyricLine]` 容器 (移除 `lyrics.lines`
  兼容层), 运算符语义随之调整.

## [0.4.0b0] — 2026-07-01

### Added
- `ParseOptions.line_filter`: 按正则丢弃匹配的行 (str 形式自动 `re.compile`).

### Changed
- **破坏性**: `LyricLine.start` 收敛为必需的 `int`, 无时间戳行不再进入正常行模型.
- **破坏性**: `Lyrics` / `LyricLine` / `BasicLyricLine` / `LyricToken` 的序列化
  与容器语义重设计 (基于 `UserList`).
- 支持只有逐字标签 (尖括号) 的行; 时间标签解析放宽 (允许省略尾数、秒数越界按字面
  折算并 warning).

### Fixed
- 序列化时保留词元结束时间戳, 不再写出重复的时间标签.
- `combine()` 对非法入参 (单个 `LyricLine` / `str`) 显式抛 `TypeError`.

## [0.3.1] — 2026-05-13

### Added
- `SerializationOptions.line_separator` / `line_tag_decimal_length` /
  `word_tag_decimal_length` / `use_bracket_for_byword_tag`.

### Fixed
- 序列化时不再产生重复时间标签; metadata 处理细化.

## [0.3.0] — 2026-05-09

### Changed
- **破坏性**: `LyricWord` 更名为 `LyricToken`; 时间偏移 API 重设计
  (`apply_delta()` / `<<` / `>>`).

## [0.3.0a1] — 2026-05-08

### Changed
- 公共 API 分层入口 (`Lyrics` 方法 + 顶层 `loads` / `dumps` / `load` / `dump`),
  新增时间标签工具 `parse_timetag` / `format_timetag`.

## [0.3.0a0] — 2026-05-08

### Added
- 首次发布到 PyPI 的预发布版本 (解析 / 序列化 / 参考行 / 逐字标签的基础实现).

## [0.2.1] — 2026-04-11

### Fixed
- 修正 `pyproject.toml` 元数据与类型标注.

## [0.2.0] — 2026-04-10

### Added
- 项目初始版本: LRC 解析与序列化, 时间标签工具, tox 配置.

[0.4.1]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/0.4.0b3...v0.4.0
[0.4.0b3]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/0.4.0b2...0.4.0b3
[0.4.0b2]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/0.4.0b0...0.4.0b2
[0.4.0b0]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.3.1...0.4.0b0
[0.3.1]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.3.0a1...v0.3.0
[0.3.0a1]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.3.0a0...v0.3.0a1
[0.3.0a0]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.2.0...v0.3.0a0
[0.2.1]: https://github.com/NingmengLemon/lemony-lrc-parser/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/NingmengLemon/lemony-lrc-parser/releases/tag/v0.2.0
