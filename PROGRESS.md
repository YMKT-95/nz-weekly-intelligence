# 项目进度

以 [MVP specification](docs/mvp-specification.md) 为范围依据，逐步实现本地 Python 周报工具。

## 阶段状态

- [x] Phase 1 — Foundation：入口程序、环境配置、日志、基础证据模型、输出目录和运行说明。
- [ ] Phase 2 — Research：选定服务，接入 Stats NZ、RBNZ 和一个劳动市场来源。
- [ ] Phase 3 — Structured Evidence：提取事实、验证证据并保存结构化 JSON。
- [ ] Phase 4 — Comparison：读取历史数据、比较指标并识别重要变化。
- [ ] Phase 5 — Job Search Index：定义分项规则，以 Python 确定性计算指数。
- [ ] Phase 6 — Report Generation：基于证据生成 Markdown 周报。
- [ ] Phase 7 — Testing and Refinement：完成模拟数据测试及端到端验收。

## 2026-09-08 — Phase 1 完成

已实现：

- `python main.py` 初始化本地目录并打印报告周和运行时间。
- 默认使用 `Pacific/Auckland` 时区及周一至周日的 ISO 报告周。
- 支持 `.env` 和系统环境变量；API 配置当前允许为空。
- 使用 Pydantic 保存事实来源、数据时期、采集时间和每周数据结构。
- 使用独立虚拟环境，提供安装和运行说明。

验证记录：在本机 Python 3.14 环境完成启动、依赖一致性检查、模型校验、JSON 往返序列化、ISO 跨年周编号、不同工作目录启动、无效时区报错和日志不输出 API key 的烟雾检查。检查通过；本阶段尚未建立持久化自动测试套件。

当前边界：尚未连接外部研究或 LLM 服务，不生成真实周报，也不计算求职指数。

## 下一步需确定

- 搜索服务和 LLM 服务的选择。
- 分项评分的证据映射规则，以及数据缺失时的处理方式。

## 进度记录约定

每个可验证的小步骤形成独立提交，提交信息说明具体变化。完成一个阶段后更新本文件，记录实现内容、验证结果及已知限制。
