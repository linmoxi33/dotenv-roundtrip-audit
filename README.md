# dotenv-roundtrip-audit

为什么现在需要它：AI agents 越来越常把密钥、token、PEM、JSON 等写进 `.env`，
而很多模板（如 `mattpocock/skills` 的 `wizard/write_env`）用 **shell 单引号转义**
写这些值。shell 能解开，但常规 dotenv 读取器解不开 —— 你会拿到一个「看起来能跑，
实际值已被静默改掉」的 `.env`。

`dotenv-roundtrip-audit` 逐值验证：**一个 `.env` 里的值，能否被 dotenv 读取器
无损 round-trip**，并精确定位是哪一行、怎么坏的。

Upstream: https://github.com/mattpocock/skills

## 上游是什么、它缺什么

`mattpocock/skills` 是 Matt Pocock 的工程技能集（307k+ stars）。其中的
`wizard` 技能用 `write_env` 函数把用户输入 upsert 进 `.env`，写法是 shell 单引号
转义：

```bash
printf "%s='%s'\n" "$key" "${value//\'/'\''}" >> "$tmp"
```

这段代码对 POSIX shell 是对的，但对 python-dotenv 等常规 `.env` 读取器是错的，
产生了一簇真实 issue（均为 **A 级证据**）：

- [#1360](https://github.com/mattpocock/skills/issues/1360)（open）— 值含换行时写出
  未闭合引号，`.env` 逐行不可解析、值被静默损坏（PEM key / 服务账号 JSON 场景）。
- [#1345](https://github.com/mattpocock/skills/issues/1345)（open）— 
  `'\''` 单引号转义 dotenv 读取器不解码，值被破坏。
- [#770](https://github.com/mattpocock/skills/issues/770)（closed）— 曾不加引号，
  含空格 / `#` / `$` 的值被损坏。
- [#1260](https://github.com/mattpocock/skills/issues/1260)（open）— 回读
  `_existing` 反解码也保留反斜杠，读写不一致。

这些 issue 全部指向同一根因：**没人能逐值验证「shell 写法写进 `.env` 的值，
经 dotenv 读取器读回来是否无损」**。上游自己也没有这样的校验器。

## 这个工具做什么、不做什么

**做**：读一个 `.env` 文件，对每个 `KEY=value`，用两套规则解析同一行——

1. shell 语义（`source`/bash 怎么读）；
2. dotenv 语义（python-dotenv 怎么读）。

当两者不一致、或 shell 单引号未闭合（跨行/PEM）、或值对 dotenv 读取器不可解析时，
标记为损坏，并报告行号、key、损坏类型、shell 值 vs dotenv 值。

**不做**：不改写文件、不校验缺失/多余的 key（那是 `dotenv_validator` 的活）、
不判断密钥强弱、不连接网络。

## 安装 / 用法

零依赖，Python 3，单文件。

```bash
python3 bin/dotenv-roundtrip-audit path/to/.env            # 人类可读
python3 bin/dotenv-roundtrip-audit path/to/.env --json     # 机器可读
```

### `--json` 输出示例

```json
{
  "file": "examples/in/augmented.env",
  "total_keys": 3,
  "corrupt_count": 2,
  "exit_code": 1,
  "corruptions": [
    {
      "line": 3,
      "key": "GREETING",
      "kind": "roundtrip-mismatch",
      "detail": "shell single-quoted write_env encoding decodes to \"It's a trap\" but a dotenv reader decodes to \"It'\\\\''s a trap\"; apostrophes written via '\\'' are not understood by dotenv readers",
      "shell": "It's a trap",
      "dotenv": "It'\\''s a trap"
    },
    {
      "line": 5,
      "key": "PRIVATE_KEY",
      "kind": "unterminated-multiline",
      "detail": "value written via shell single quotes has no closing quote on this line (multiline/PEM-like value); dotenv readers see a broken file"
    }
  ]
}
```

**注意**：`shell` 字段是「shell 想表达的原始值」，`dotenv` 字段是「dotenv 读取器
实际得到的值」。两者不同 = round-trip 断点。

### 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 通过：所有值均可无损 round-trip |
| 1 | 检出问题：存在 round-trip 损坏 |
| 2 | 用法 / 输入错误（缺文件、文件不可读、少了参数） |

## 示例

`examples/in/health.env` → 全部健康，退出码 0。
`examples/in/augmented.env` → 含 `GREETING`（单引号转义不 round-trip）和
`PRIVATE_KEY`（跨行未闭合引号）两处损坏，退出码 1。

## 测试

```bash
python3 -m unittest tests.test_audit -v
```

10 个用例全绿，含行为用例（输入→输出/退出码）。

## 局限

- 只覆盖单值单行的 `.env`（`write_env` 的产物形态），不处理被合并拼接的多行
  shell 引号。
- dotenv 语义按 python-dotenv 的常见行为建模；`export KEY=...` 前缀会被忽略。
- 它找出「shell 可读但 dotenv 不可读 / 读回不一致」的值——它不会替你修复，
  只定位并量化。

## 与同类项目的差异

已有的 `dotenv_validator`（fastruby/dotenv_validator 等）只检查「关键 key 是否
存在 / 缺失」，**不检查「值经 shell 转义写入后能否被 dotenv 读取器无损 round-trip」**。
已有的 SKILL.md 校验器（skill-lint 等）只查 frontmatter/结构，不查 `.env` 值级
往返一致性。本工具填的是「值级 round-trip 无损性」这一块空白。

## 本轮创新

首次把「值级 round-trip 无损性」作为一等检查维度，用在 trending 项目
`mattpocock/skills`（write_env bug 簇 #1360/#1345/#770/#1260 的直接产物）上：
不是复述上游 README，而是把上游开着的 4 个 `.env` 损坏 issue 归到一个可断言、
可离线跑的审计器里。别的 validator 只查有没有 key，本工具查「值写得对不对、
读回来变没变」。档位：B。