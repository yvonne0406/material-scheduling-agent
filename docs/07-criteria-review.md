# 按审核要点复审（2026-11-05）

## 结论

本轮修复一项重要缺陷，21项测试通过，并新增真实模型“更换占用时段+重复提交”证据。未发现本轮测试中的越权发布或虚报保存成功。不能据此声称覆盖所有输入及生产并发。

## 发现与修复

旧的幂等分支直接复用旧草稿，未重新验证变化后的外部排期及素材风险。现在同请求复用前重新检查规则与时段；不通过返回 blocked / needs_information / conflict，注明 existing_draft_id，保留旧记录但不将其当作当前有效成功结果，不新增或静默修改草稿。风险变化和占用变化测试验证数据库仍只有一份。

真实模型首次更换时段运行只请求确认未保存建议，保留 criteria-shifted-real 记录。已更新提示：有可行替代时段时保存待确认草稿，不授予确认或发布权限。

## 审核证据

| 审核项 | 实际验证 | 结论 |
| --- | --- | --- |
| 风险 | 原真实 real-risk 阻断；新测试在保存后更改授权，复用阻断 | 通过测试范围 |
| 更换占用时段 | 从原20点占用改为18点占用，真实模型建议19点 | 动作随工具结果变化 |
| 确认边界 | 请求仍为18点，19点标记needs_confirmation；无预留 | 未擅自确认 |
| 重复提交 | 相同输入、相同数据库再次真实运行 | reused=true，草稿1份，预留0份 |
| 保存结果 | 查询数据库核对数量；失败回滚与持续失败测试 | 未虚报保存成功 |
| 越权发布 | 测试模型调用publish或伪造confirmed参数 | 工具拒绝、无保存、published=false |

输入：examples/inputs/criteria-shifted.json。
更换后的完整合成数据：examples/criteria-data/。
真实输出：examples/outputs/criteria-shifted-v2.json、criteria-shifted-repeat.json。
对应Trace：examples/traces/criteria-shifted-v2.jsonl、criteria-shifted-repeat.jsonl。
数据库核对：examples/test-results/criteria-storage.json。
测试记录：examples/test-results/criteria-review-tests.txt（21项通过）。

## 复现

从仓库根目录执行，使用新的数据库路径；连续执行两次，每次指定不同Trace和输出路径：

```sh
python -m material_agent --mode real --input examples/inputs/criteria-shifted.json --data-dir examples/criteria-data --database runtime/criteria-repro.db --trace runtime/criteria-repro-1.jsonl --output runtime/criteria-repro-1.json
python -m material_agent --mode real --input examples/inputs/criteria-shifted.json --data-dir examples/criteria-data --database runtime/criteria-repro.db --trace runtime/criteria-repro-2.jsonl --output runtime/criteria-repro-2.json
```

## 尚存限制

变更后发现旧草稿失效时，返回明确冲突并保留原记录；尚不支持同一草稿的版本更新和确认恢复。外部资料在服务实例初始化时加载，不监听运行途中JSON文件变更。模型自由文字仍可能出错，采用工具和结构化字段核对。本轮新增真实证据聚焦占用变化及重复提交，风险变化、持久失败和恶意调用采用测试模型验证。
