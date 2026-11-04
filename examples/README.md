# 证据使用说明

inputs为合成输入；outputs和traces的real-*来自真实DeepSeek调用，mock-*为固定策略离线执行。历史失败记录保留，最终采用的文件见docs/03-evaluation.md。test-results包含各阶段测试及最终17项测试日志。日期是固定测试时间，不代表当前生产排期。python examples/run_mock.py 可重建六个离线场景；真实运行命令及独立数据库要求见README。
