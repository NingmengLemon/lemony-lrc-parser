# 不计划

下面这些提过，结论是不做。重新提起之前先看理由。

## metadata 的反斜杠转义

LRC 家族没有任何规范或社区实现定义过转义语法。AMLL 的格式文档对正文里的
`<` / `>` 写得很直白：转义没有官方标准，未匹配的一律当普通文本。引入 `\]` 会：

1. 自造方言，别的播放器会把反斜杠原样显示出来；
2. 改变含反斜杠的既有 value 的含义；
3. 让写出的文件与读入的文件不再是同一种格式。

替代方案是配对方括号，见 [semantics.md](semantics.md#metadata)。

## `to_json()` / `from_json()`

`to_dict()` 产出的 dict 交给调用方 `json.dumps(..., ensure_ascii=False)` 即可。
再包一层会让"JSON schema 是否稳定"变成库的长期兼容负担。若将来决定正式提供
稳定格式，需要先加 `schema_version`。

## 逐字时间的线性插值

插值是播放器或音频强制对齐工具的职责，不属于解析器。

## `apply_delta` 自动清理或应用 `[offset:]`

显式优于隐式。LRC 的 `offset` 与 `apply_delta` 符号相反，自动处理极易搞错方向；
也有播放器完全忽略 offset。显式 helper 见 roadmap META-1。

## 异步 I/O

解析是 CPU 上的同步逻辑，异步读文件由调用方处理。

## 重写 `Lyrics` 的全部 list 操作以守住不变量

成本高，也违反用户对 list 的预期。用 `add_line` / `sort_inplace` / `validate()`
代替，见 [architecture.md](architecture.md#lyrics-是聚合入口)。
