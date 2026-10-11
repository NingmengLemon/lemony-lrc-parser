# typing-extensions 下限实测

本库只从 `typing_extensions` 取 `Self`（4.0+）和 `override`（4.4+），但
"下限 4.4.0"只在旧解释器上成立。每个组合都跑完整测试套件：

| Python | 4.4.0 | 4.5.0 | 4.6.0 | 4.10.0 | 4.12.2 | 4.13.0 | 4.14.0 | 下限 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3.9 / 3.10 / 3.11 | ✅ | — | — | — | — | — | — | 4.4.0 |
| 3.12 / 3.13 / 3.14 | ❌ | ❌ | ✅ | — | — | — | — | 4.6.0 |
| 3.15（rc1、rc2） | ❌ | — | ✅ | ❌ | ❌ | ❌ | ✅ | 4.14.0 |

4.3.0 及更早没有 `override`，直接 `ImportError`。

失败模式：

- 3.12-3.14 配 4.4 / 4.5：`TypeError: type 'typing.TypeVar' is not an acceptable
  base type`，旧版不认识新解释器的 typing 内部结构。
- 3.15 配 4.10-4.13：`AttributeError: module 'typing' has no attribute …`，
  这几个版本引用了 3.15 里改名或移除的属性，4.14.0 修好。

3.15 那一档是区间断裂而不是下限更高：4.6.0 能跑通，但 4.10-4.13 会炸，写成
`>=4.6.0` 会放进断裂区间，所以只能写 `>=4.14.0`。

`pyproject.toml` 的分档依赖与 CI 的 `lowest-typing-extensions` 矩阵都以这张表
为准。
