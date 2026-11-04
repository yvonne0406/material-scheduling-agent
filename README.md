# 素材审核与发布排期 Agent

题号1。CLI + Python 3.11 + SQLite，原生模型动作循环，无 Agent 框架、无运行时第三方依赖。只保存草稿，不接发布。已实测 DeepSeek deepseek-flash，26 项测试通过。真实结果及限制见 docs/03-evaluation.md。

## 安装与离线评审

从仓库根目录执行（Windows PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe examples/run_mock.py
```

macOS/Linux 将上述 Python 路径替换为 `.venv/bin/python`。Mock 不需要密钥，只证明流程，不证明模型决策效果。重跑脚本会覆盖 mock 证据文件，不影响 real 历史记录。

## 真实模型运行

复制 `.env.example` 为 `.env`，填入 MODEL_API_KEY。DeepSeek 地址与模型名已给出；程序自动读取当前目录的 `.env`，进程环境变量优先。密钥文件被 Git 忽略。

```powershell
.\.venv\Scripts\python.exe -m material_agent --mode real --input examples/inputs/normal.json --database runtime/review-normal.db --trace runtime/review-normal.jsonl --output runtime/review-normal.json
.\.venv\Scripts\python.exe -m material_agent --mode real --input examples/inputs/conflict.json --database runtime/review-conflict.db --trace runtime/review-conflict.jsonl --output runtime/review-conflict.json
```

其他输入见 examples/inputs。重复提交使用 duplicate.json 和正常场景同一个数据库；其余场景各用新数据库。保存失败输入必须加 `--test-mode` 才会注入一次故障。模型可以重试恢复，必须结合 Trace 检查第一次失败。重复运行会复用已存在草稿。

可选 `--max-steps 8 --max-calls 12`。退出码0为完成，2为待确认/未完成/任务失败，1为输入或配置错误。Trace 路径会覆盖，请为独立实验使用新路径。默认仍为 scaffold（旧框架演示）；正式运行必须显式指定 mock 或 real。

## 评审入口

- docs/01-requirements.md：需求与验收。
- docs/02-solution.md：实际设计与取舍。
- docs/03-evaluation.md：真实运行、Mock、失败与限制。
- docs/04-ai-usage.md：AI 辅助范围、待本人补充信息。
- docs/05-retrospective.md：问题、学习和改进。
- docs/06-delivery-review.md：最终审查结论和提交缺口。

src/material_agent/agent/runner.py 实现决策与 Trace；models/client.py 实现 HTTP/Mock；tools/service.py 实现工具与 SQLite；cli.py 提供入口。storage、observability 是保留目录，不代表已有独立实现。data 为合成资料，examples 为输入、实际结果和日志，tests 为可执行测试。

## 边界

素材审核仅检查元数据；时间按单账号单时点建模，不处理持续时间或过去时间。待确认草稿不预留时段；确认草稿预留。支持显式确认更新同一草稿。真实模型采用 JSON 动作协议而非原生 function calling。模型自由文字曾出现错误时间，可靠排期应以工具结果和结构化输出为准。单次真实运行不代表稳定通过率。

本人提供的实际用时与贡献已记录于docs/04-ai-usage.md。仓库提交信息见最终交付说明；私有仓库还需提供评审访问权限。

最新专项复审见 docs/07-criteria-review.md：21项测试通过，真实更换时段并重复提交后草稿仍为1份，待确认且不占用排期。

## 可交互演示（推荐评审入口）

```powershell
.\.venv\Scripts\python.exe -m material_agent --interactive --mode mock --input examples/inputs/criteria-shifted.json --data-dir examples/criteria-data --database runtime/interactive.db --trace runtime/interactive.jsonl --output runtime/interactive.json
```

将mock改为real即使用DeepSeek。省略`--input`可在终端输入请求ID、素材ID和时间。出现建议后输入`CONFIRM`明确接受；其他输入保留待确认。确认仍是草稿，不发布；同一请求再运行不会产生第二份草稿。

## 完整交付验证

```powershell
.\.venv\Scripts\python.exe examples/verify_delivery.py --mode mock
.\.venv\Scripts\python.exe examples/verify_delivery.py --mode real
```

real会产生API调用费用。每次使用临时空数据库，输出到examples/delivery-real或delivery-mock（覆盖该目录同名证据）。每组包含输入、实际输出、Trace和数据库核对；summary.json汇总。最后的显式确认由测试脚本模拟用户授权并单独标注，不冒充模型操作。

最终交付入口：docs/08-final-delivery.md。最终证据优先查看examples/delivery-real及docs/03-evaluation.md；之前阶段的日志保留作历史记录。
