# Python 版本支持策略

`requires-python` 只设下界（当前 `>=3.9`），不设上界。已实测过的版本由 Trove
classifier 表达（`3.9` 到 `3.16`），新解释器一发布就往 CI 矩阵里加一档。

## 为什么不设上界

本库是纯 Python：`src/lemony_lrc_parser` 里除 `py.typed` 外没有非 `.py` 文件，
不编译扩展，因此不存在 ABI 层面的版本耦合。运行时唯一的第三方依赖
`typing-extensions` 本身也只约束下限，见
[typing-extensions.md](typing-extensions.md)。

设上界换不到什么，代价却是实打实的：

- pip 在 `Requires-Python` 不匹配时会回退到更老的发行版。本库历史上的每个
  版本都带着当时的 `<3.x` 上界，所以在超出上界的新解释器上，回退到底也找不到
  可用版本，结果是直接装不上，而不是"也许能跑"。
- uv 的处理更明确：评估依赖的 `requires-python` 时只看下限，上限被完全忽略，
  因为它会引发"形式上正确、实际上错误"的解析。见
  <https://docs.astral.sh/uv/concepts/resolution>。
- PyPA 的打包指南已经把示例里的 `<4` 删掉（
  <https://github.com/pypa/packaging.python.org/pull/850>）。`Requires-Python`
  的设计目的是让库能丢掉老解释器，不是声明测到哪一版；后者是 classifier 的
  职责。

生态里的同类纯 Python 库也都不设上界。2026-11 抽查 PyPI 元数据：

| 包 | `Requires-Python` |
| --- | --- |
| requests | `>=3.10` |
| attrs | `>=3.9` |
| typing-extensions | `>=3.9` |
| pytest | `>=3.10` |
| hypothesis | `>=3.11` |
| rich | `>=3.9.0` |
| markdown-it-py | `>=3.10` |
| platformdirs | `>=3.11` |
| packaging | `>=3.9` |
| pluggy | `>=3.10` |

## 代价与兜底

没有上界意味着在还没测过的新解释器上也能装上。兜底靠三件事：

1. classifier 只列实测过的版本，"支持哪些版本"在 PyPI 页面上直接可读。
2. CI 矩阵跟着 classifier 走，新 alpha 一发布就加一档（3.16 就是这么加的）。
3. 真在新解释器上出问题，按 bug 修并单独发版，而不是把用户卡在解析器层面的
   "装不上"。

下界仍然是硬约束：只在上调时改，并同步 tox 的 `env_list`、CI 矩阵与
classifier。
