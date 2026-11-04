# 最终评估与证据索引

最终测试：26项通过，见examples/test-results/delivery-tests.txt。
真实模型：DeepSeek deepseek-flash（API别名，无不可变权重版本保证）；使用原生JSON动作循环，无第三方Agent框架。离线Mock为固定策略，独立标记。

## 最新真实运行结果

所有文件位于 examples/delivery-real/。每个用例有 `<用例>.input.json`、`<用例>.output.json` 和 `<用例>.trace.jsonl`。输出内 verification 保存当次数据库核对。summary.json为汇总。旧阶段记录保留用于学习过程，评审以本目录为最终入口。

| 用例 | 预期 | 实际任务状态 | 保存状态 | 草稿数 |
| --- | --- | --- | --- | --- |
| normal | 正常保存 | completed | saved | 1 |
| duplicate | 复用同一草稿 | completed | saved | 1 |
| missing-info | 缺授权信息，停止 | needs_information | not_attempted | 0 |
| risk | 规则风险，阻断 | blocked | not_attempted | 0 |
| conflict | 替代时段待确认 | needs_confirmation | saved | 1 |
| save-persistent-failure | 持续保存失败，不写入 | failed | failed | 0 |
| criteria-shifted | 占用改为18点，建议19点 | needs_confirmation | saved | 1 |
| criteria-shifted-repeat | 重复替代建议，不新增草稿 | needs_confirmation | saved | 1 |

## 关键路径

normal：读取素材→规则审核→查询时段→保存→完成。
criteria-shifted：读取/审核→查询原时段→根据冲突补查替代时段→保存待确认建议→结束。以真实Trace为准，不预写模型动作。
save-persistent-failure：工具返回持久故障后模型停止，failed且数据库0行。持久故障由显式test-mode注入，模型是真实API。

重复请求核对同一draft_id、reused=true、draft_count=1。确认记录 explicit-confirmation.json 使用测试脚本模拟用户明确同意，在同一草稿上完成更新；来源明确为test_harness，不冒充真人或模型操作。CLI真实交互对应输入CONFIRM。

## 复现

`python -m unittest discover -s tests -v`
`python examples/verify_delivery.py --mode mock`
`python examples/verify_delivery.py --mode real`

验证脚本创建临时空数据库，使用固定合成输入和资料。真实运行需要.env配置且产生API费用；不同运行模型选择可能不同。mock结果在examples/delivery-mock/。完整命令见README。

## 已发现与修复

真实联调发现自身预留误判冲突；幂等复用缺少风险和时段复查；异常工具参数导致崩溃；缺乏同一草稿显式确认流程。已分别修复并补充测试。模型文字曾出现无依据时间，保留旧Trace，不将自由文本作为结构化排期事实。

## 限制

小样本真实运行不代表稳定通过率；单账号单时点，无持续时长冲突和过去日期校验；无生产鉴权和高并发验证；确认更新已实现，但任意草稿改版尚未实现。达到上限时明确未完成。报告区分模型决策、业务工具事实和模拟用户确认，不将Mock包装成真实模型效果。
