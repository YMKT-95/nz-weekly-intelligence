# NZ IT Graduate Weekly Intelligence

面向新西兰 IT 毕业生求职的个人本地 Python 工具。最终目标是每周研究相关信息、比较历史变化，并生成有来源支持的 Markdown 周报。

当前只实现 **Phase 1：项目基础**。启动时会读取配置、计算报告周、创建输出目录并打印日志。尚未接入网络研究、LLM、历史比较、评分或报告生成；不会生成示例统计或空白周报，也不会发出 API 请求。

项目范围见 [MVP specification](docs/mvp-specification.md)，阶段状态与验证记录见 [项目进度](PROGRESS.md)。

## 环境与安装

需要 Python 3.12 或更新版本。以下命令适用于 macOS / Linux，在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

虚拟环境激活后，使用其中的 `python` 和依赖，不修改全局 Python 环境。`tzdata` 为缺少系统时区数据库的环境提供时区数据。

## 配置

Phase 1 不需要 `.env` 或 API key，即可直接运行。如需本地配置，可在首次设置时复制模板：

```bash
cp .env.example .env
```

- `REPORT_TIMEZONE`：默认 `Pacific/Auckland`。
- `LLM_API_KEY`、`LLM_MODEL`、`SEARCH_API_KEY`：留待后续接入服务，当前允许为空。

已有的系统环境变量优先于 `.env`。配置文件始终从项目根目录读取，与启动命令所在目录无关。不要提交真实凭据；`.env` 已加入 `.gitignore`，日志不会输出 API key。

## 运行

```bash
source .venv/bin/activate
python main.py
```

日志会显示 ISO 报告周编号、周一至周日的日期范围、带时区的实际运行时间和输出目录。周中运行时，显示的周日是报告周边界，不表示已收集未来日期的信息。

成功时退出码为 `0`；配置无效或目录创建失败时，记录错误并以 `1` 退出。Phase 1 成功日志的最后一行是：

```text
[INFO] Foundation ready. Research and report generation are not yet connected.
```

重复运行不会覆盖已有数据或报告。后续阶段将使用 `data/weekly/YYYY-WXX.json` 和 `reports/YYYY-WXX.md` 保存真实结果；当前仅确保目录存在。

## 项目结构

```text
nz-weekly-intelligence/
├── main.py              # 启动、报告周计算、日志与目录初始化
├── src/
│   ├── __init__.py
│   ├── config.py        # 环境变量、时区和项目路径
│   └── models.py        # Pydantic 证据与每周数据模型
├── data/weekly/         # 后续保存结构化周数据
├── reports/             # 后续保存 Markdown 周报
├── tests/               # 预留后续自动化测试目录
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 数据模型

`WeeklyFact` 保存分类、指标、数值或文字事实、单位、数据时期、来源名称、HTTP(S) 来源 URL、发布日期、带时区的采集时间与置信度。来源、数据时期和值不能为空；未知发布日期使用 `None`，不得用采集日期代替。结构校验不代表已核实事实，来源支持程度将在证据提取阶段检查。

`WeeklyData` 保存报告周、周起止日期、带时区的运行时间和事实列表，支持 Pydantic JSON 序列化。Phase 1 只在内存中创建空的周数据容器。

## 后续阶段

下一步是 Phase 2：选定搜索与 LLM 服务，从 Stats NZ、RBNZ 和一个劳动市场来源开始研究。此后依次实现证据提取与验证、历史比较、确定性评分、报告生成及完整测试。研究、评分和报告模块将在实际实现时添加。
