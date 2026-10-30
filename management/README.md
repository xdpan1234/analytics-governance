# 埋点分析管理：第一阶段

当前缓存结果已导入本机独立 PostgreSQL 业务库，管理页：<http://127.0.0.1:8090/>。

支持批次列表、请求日与数据状态、按 UTC 统计日切换 Top10、分母与原因、前日环比及 7 日中位数基线、候选账号查询、用户最近 100 个归档批次、筛选与合并原因、问题假设、事实引用及完整单账号上下文。

## 当前数据与边界

- 冻结快照 `prod-us-release-20261029T080615Z`，源 SHA256 `264e8c81124307c93112a437156fb32d159d2e48346d214f439c86e0261ea31d`。
- 原批次 `f51f9e659e0fa818954570ccfcfd766906f0c0f0f5c79399f76242652bba2e67`：3 份日报（2026-10-25～27 UTC）、20 账号、52 条关联线索及单账号上下文。
- 请求日 10 月 28 日 `WAITING_EXPORT`；数据等待与计算／入库 `SUCCEEDED` 分别保留。页面默认最近可用日报。
- 全部 451 条候选池记录、650 条排除记录与固定策略保存在批次 JSONB；独立线索表保存已选 20 账号的 52 条关联线索。全局漏斗按去重账号计算，不把 451 条候选观察当作 451 个账号。
- 沿用原始阈值、查询范围、版本和上下文内容；`SELECTED_PREVIEW`、`UNRESOLVED` 明确表示旧账号级预览。未新增实例关联，不代表可直接派单或已确认根因。
- **没有 BigQuery 客户端、采集／通知写接口、模型调用、调度器或 Flow B/C 实现。** 现有 Kestra 分析流程保持原样；本阶段通过离线 CLI 回填其归档。后续新归档仍需运行同一导入命令，当前不声称已自动入库。

## 数据库存储

复用 `log-backend-local-postgres-1` 实例及已有 PostgreSQL 数据卷，新增 `analytics_management` 数据库、`analytics` schema；不修改 Kestra 内部表，也不新增数据库公网端口。

| 表 | 检索列 | 不可变内容 |
| --- | --- | --- |
| `telemetry_runs` | run_id、scope、请求日、数据／计算状态、源与规则摘要 | 完整分析 JSONB、来源、源 manifest、归档字节摘要 |
| `daily_reports` | report_revision_id、run_id、统计日 | 全事件、Top10、质量、窗口、环比／基线 JSONB |
| `diagnostic_contexts` | context_id、run_id、账号、选样顺序、目标／预览状态 | 单账号上下文及主候选 proposal JSONB |
| `telemetry_findings` | finding_revision_id、candidate_key、run_id、账号、context_id、事件／平台／统计日／次数／选样原因 | 原线索、事实引用、比较与检查方向 JSONB |
| `run_executions` | run_id、execution_id | 对应 Kestra namespace／flow 的运行引用，可补充多次执行 |

保留原 run/context ID。日报修订 ID 是 `SHA256([run_id, statistical_day])`，线索修订 ID 是 `SHA256([run_id, candidate_key])`。本阶段始终按批次选择日报，不维护跨批次“当前日报”指针，避免重放覆盖历史。

导入先校验快照原始字节、行数／次数、覆盖、归档分析摘要、run/context 内容身份、选中账号集合、每条事实所属账号与原始时间／次数、线索引用与合计、排除集合，再在**一个事务**写入全批次。相同 run 用事务 advisory lock 串行；重复归档复用，任何内容冲突拒绝。仅执行引用允许追加且去重。错误回滚，不留下半批次。

角色：`analytics_owner` 不可登录；`analytics_importer` 仅 SELECT/INSERT；`analytics_reader` 仅 SELECT，并强制只读事务。管理页不持有导入凭据。业务 FK 防止线索引用其他账号的上下文。Pg 的 PUBLIC 默认连接权限不等于业务表权限；已验证 reader 无权查询 Kestra `executions`。

## 启动与复用缓存

运行目录是 `/Volumes/SanDisk-CaseSensitive/code/log/analytics-governance`，以下命令可直接用绝对路径执行。前提是既有 `backend-local` PostgreSQL 与 Docker 网络运行中。

```bash
python3 /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/management/setup_local.py \
  --env-file /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/.scratch/management/local.env \
  --archive /Volumes/SanDisk-CaseSensitive/code/log/.scratch/analytics-triggered-log-collection/kestra-evidence-20261029 \
  --snapshot /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/.scratch/bigquery-replay/prod-us-release-20261029T080615Z

docker compose \
  --env-file /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/.scratch/management/local.env \
  -f /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/management/compose.yaml \
  up -d --build web

docker compose \
  --env-file /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/.scratch/management/local.env \
  -f /Volumes/SanDisk-CaseSensitive/code/log/analytics-governance/management/compose.yaml \
  run --rm import python import_cached.py --archive /archive --snapshot /snapshot \
  --execution-id 65vaHa6WJc5D1zehJXWqQO
```

`setup_local.py` 只创建本机命名数据库／角色，迁移由 owner 应用；重复运行不重置凭据。随机数据库密码只保存在忽略提交的 `.scratch/management/local.env`（0600）。不要提交 env、生产归档、数据库备份；不要把服务号 key 挂载到此应用。源与归档挂载为只读，导入容器按宿主 UID/GID 读取私有文件。

可停止新管理页而保留已导入数据：同上 compose 命令使用 `stop web`；不影响 Kestra，不删除原缓存和数据卷。迁移仅添加自己的业务对象；不提供自动 DROP／回滚数据脚本。

## 页面查询与访问范围

- `/`：最近 100 个批次，可输入精确账号 ID 筛选。
- `/runs/<run_id>?day=YYYY-MM-DD&account=<id>`：批次日报与本批候选用户筛选。
- `/users?account=<id>` 或 `/users/<id>?run=<run_id>`：用户跨批次记录和所选批次证据。
- `/healthz`：数据库只读连接健康检查。

SQL 全部参数绑定；scope 固定为服务端配置 `ai.looktech.glasses.memo/prod/us/release`，不接受浏览器切换 scope。界面原样内容均 HTML 转义；响应 no-store、禁远端资源／脚本／iframe，不记录含账号的访问路径。事实锚点只在当前用户上下文内定位。

本机仅监听 `127.0.0.1:8090`，按单机操作者使用，不提供登录、租户权限或公网部署能力。同一台电脑的其他进程／使用者也能访问此本机端口；要共享给团队或远程访问，先接受控身份认证与授权。Host／跨站请求检查不代替登录。

此阶段不定义新的服务端保留期限或自动删除；手机 7 天任务期／30 天固定副本期不套用业务库。生产使用前仍需确认保留、撤权、审计及备份恢复政策。

## 验证

本阶段不新增单元测试。执行既有 12 项 Python 检查及 Schema 校验，并用当前真实缓存做数据库／HTTP／浏览器验收：校验 3／20／52 与原 JSON 内容，重复并发导入、同 ID 冲突拒绝、失败事务回滚、只读权限、scope／账号查询隔离、非法参数／空结果，以及日期切换、筛选、证据锚点和响应布局。

依据：[PostgreSQL 权限](https://www.postgresql.org/docs/18/ddl-priv.html)、[事务／唯一约束插入](https://www.postgresql.org/docs/18/sql-insert.html)、[Psycopg 安装](https://www.psycopg.org/psycopg3/docs/basic/install.html)。本服务使用 Python 标准库 HTTP 服务处理本机只读页面；不把它当作生产 Web 服务部署。
