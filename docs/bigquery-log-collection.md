# UTC 日报与 App 日志采集候选

独立只读入口：`python3 tools/ga4_log_collection.py --output <private-result.json>`。

此入口查询 BigQuery、生成日报和候选，不创建任务、不发送通知、不部署定时任务。后端 API 未定稿，结果中的 `dispatch_enabled=false`、`quota_authoritative=false` 必须保留。

## 查询与输入

- 默认数据集 `looktech-online.analytics_506558519`，主 App `ai.looktech.glasses.memo`，已核验两个 Android/iOS 数据流；范围固定 prod/us/release，`us` 不筛用户所在地。
- 默认目标为前一个 UTC 日；北京时间 08:00 由后端现有调度调用。保持 GA4 属性 Asia/Shanghai，仅使用 daily 表，按 event_timestamp 的 UTC 窗口过滤。
- UTC 日可能需要两张属性日期表。先查表元数据；缺表输出 `WAITING_EXPORT`，显示最近就绪统计日，缺失日期不填零。表可读取不代表所有离线事件已到齐。
- 查询最近十四个 UTC 日，以覆盖目标与前三日补算、最近可用日及各自七日基线。Top10 是展示，不限制查询，四十条正式规则与全部流程分母都保留。
- `--maximum-bytes-billed` 默认 1 GiB；结果达到一百万行即拒绝发表可能被截断的数据，不将部分查询结果当全量日报。

`--input fixture.json` 接收 `{available_tables: [...], rows: [...]}`；rows 必须是 `--render-sql` 生成查询的完整结果，包括成功分母、路由字段、user_pseudo_id、UTC 聚合时间与重复参数计数。不得把旧时区的错误 Top10 汇总当此输入，也不能仅凭手工表名宣称完整查询。输出权限 0600，包含业务账号，不发布到公共日报或日志中。

```sh
python3 tools/ga4_log_collection.py --input fixture.json --day 2026-10-27 --render-sql --output private-query.json
python3 tools/ga4_log_collection.py --input fixture.json --day 2026-10-27 --as-of 2026-10-28T00:00:00Z --output private-result.json
```

## 结果与规则

| 内容 | 口径 |
|---|---|
| 日报 | 保留正式四十事件；Top10 只展示非零事件，仍按次数降序、事件名升序；业务账号、原因、结果率及平台／版本分母分别统计 |
| 分析用户 | `analytics_users` 为原始 `user_pseudo_id` 去重数；空值记录单列，不等同 Data API 的 totalUsers／activeUsers |
| 原因归并 | 事件＋平台＋正式原因；媒体先区分 error_source，再按 failure_reason 归组，sync_state 仅作证据 |
| 关键信号 | 明确 crash/anr、笔记终态失败、合法 decode_error／file_missing 至少一条 |
| SDK／网络 | 同账号同组 SDK／明确 unknown 等至少二条，网络／超时至少三条 |
| 影响面／持续高频 | 合格 Top10 异常组至少三个账号；或单账号十条且占组记录至少一半 |
| 预期行为 | 取消、权限拒绝等预期原因不自动进入；缺字段／非法枚举不冒充 unknown |
| 趋势 | 保留前日／基线观察，新发、突增、结果率提级暂不触发采集 |

`blocked` 类型不再整体屏蔽影响面／高频入口，先按正式原因判断预期行为。通用预期原因保持原集合；事件限定的补充包括用户名规则的 `validation_failed`、笔记导入的 `file_too_short`，以及翻译前置条件 `their_language_missing / same_language_pair / saved_config_missing / glasses_not_connected / credits_used_up`。这些符合既有 Schema 和预期阻塞约束，不改变 1／2／3 条、3 账号、10 条及 50% 等门槛。合法 `unknown` 仍是候选线索。

`candidate_pool` 保留所有可解释候选；`candidate_proposals` 是跨本次补算日期合并的限额预览：最多二十账号，同优先级先每组一个再补至每组三个，账号只选一次。最近异常超过 168 小时仅进日报。可用 JSON `--policy` 覆盖初始参数；变更产品额度仍需业务确认。

后端应从候选池校验账号与诊断授权，关联已有任务，并在持久事务内完成任务创建 UTC 日二十账号、每组最多三、账号滚动二十四小时冷却和幂等。平台保留为诊断上下文，不新增手机安装 ID。不能直接把预览名单当可派单结果，不能把重跑预览当额度已扣减；任务先登记，再按账号在线状态选择 WebSocket／FCM。分析入口不实现这些后端行为；Kestra 包装流程仅编排独立命令，见下节。

## Kestra 编排与诊断上下文（2026-10-29）

`flows/bigquery-daily-analysis.yaml` 已在本地 `local.analytics` 注册。使用已有 Kestra 2.0.6 Process runner 和 Python 3.12；无新依赖、不挂载服务号凭据、无定时／Webhook 触发器。计算模块和既有阈值不变。

执行顺序：校验冻结快照 → 调用 `ga4_log_collection.py --input` → 调用 `ga4_diagnostic_context.py` 归档。输入为冻结 `source.private.json`、对应 `manifest.json`、目标 UTC 日和评估时刻；FILE 输入可复用既有执行的 Kestra URI，无需重复上传，更不重复查询生产 BigQuery。流程默认日期和时刻固定于本次快照，不能当作生产每日调度。

| 输出文件 | 内容与用途 |
| --- | --- |
| `analysis.private.json` | 完整日报、候选、排除与限额预览；含业务账号，仅私有访问 |
| `diagnostic-contexts.private.json` | 20 个预览入选账号各自的埋点事实、全部命中线索、规则依据、总体环比／基线和待验证排查方向；包含账号到上下文 ID 的私有索引 |
| `run-summary.json` | 不含账号的摘要、数据状态、计数和源摘要；作为流程 summary 输出 |

文件由 WorkingDirectory 的 `outputFiles` 写入 Kestra 内部存储，Execution 的 Input/Output 可下载。主执行的 SUCCESS 只证明流程运行成功；例如目标日缺表时，摘要仍明确 `WAITING_EXPORT`，并展示最近可用统计日。

上下文 ID 是完整上下文内容的 SHA-256；规则或事实变化生成新 ID。每条事实保留源聚合行 SHA-256、首次／末次 UTC 时间、平台／版本、合法原因、次数和质量状态；候选通过 fact ID 引用事实并核对次数。`population_comparison` 明确是全过滤人群、跨平台总体指标，不能误当单账号或单平台基线。当前仅按日聚合、没有逐条时间线；未知原因原文不被重新带入上下文。

`investigation` 是程序生成的规则排查提示，固定 `HYPOTHESIS / UNVERIFIED`，保留语义搜索词、检查点与需支持／反对证据的要求，不是模型已确认的根因，也不声称搜索词是精确 Logger tag。账号可跨手机与版本；后续实际日志必须核对覆盖、版本、平台与时钟。

后续关联按以下内部约定设计，尚未实现业务 API：后端在采集任务准入成功时保存 `collection_task_id ↔ context_id / context_uri / context_sha256`；同一任务追加新线索保留多个上下文引用，不覆盖旧版本。日志就绪后，以可信任务／上传记录查回上下文，重新验证账号归属、授权、实际覆盖和摘要，交给日志分析。独立上传缺少任务关联时，再按可信账号＋统计窗＋平台／版本查找，返回多项或不匹配，不能只取该账号最新一次推断。

Kestra 保存步骤状态、摘要和文件 URI；业务后端负责账号／任务／日志包的可信关联和权限。KV 可以存游标或最新引用，不作为配额锁、24 小时冷却账本或唯一业务主档。当前本地内部存储使用持久 Docker volume；生产应沿用私有对象存储和既定访问／到期策略，执行清理不得删除仍被业务任务引用的唯一上下文。不能将普通 outputs 当作加密保险箱，不在 labels／运行日志里放原始账号或完整埋点。

当前总包含多个账号，只供可信操作者／诊断服务读取；生产单任务访问前应按账号拆对象或通过受限读取接口筛选，不能将总包交给 AI。`context_id` 是单份上下文的规范化内容摘要，不等于整个文件的字节摘要；后端应同时保存 artifact URI／SHA-256 与 context ID，并分别核验。

本地运行时放在既有只读挂载 `/demo/runtime/analytics-governance`：将当前仓库的 `tools/ga4_log_collection.py`、`tools/ga4_diagnostic_context.py`、`tools/ga4_report/` 与 `analytics_schema/` 复制到宿主 `/Volumes/SanDisk-CaseSensitive/code/log/backend-local/runtime/analytics-governance/`。代码更新应在无活动执行时同步；每份上下文记录实际实现与 Schema 摘要。生产部署应固化镜像或只读版本目录，不依赖个人电脑此路径。

2026-10-29 真实验证：revision 2、execution `65vaHa6WJc5D1zehJXWqQO` 成功，20 个上下文／52 条线索；逐账号回查、事实归属及命中次数均通过，源快照未改变。未创建日志采集任务、未推送、未进行生产定时查询。前轮审查的原生崩溃分类、iOS Schema 漂移和历史补算选样偏重仍是待解决项，本次接线没有改变相关规则。

依据：Kestra 官方 [文件存储](https://kestra.io/docs/concepts/storage)、[WorkingDirectory](https://kestra.io/plugins/core/flow/io.kestra.plugin.core.flow.workingdirectory)、[KV Store](https://kestra.io/docs/concepts/kv-store)、[JSON 解析](https://kestra.io/docs/expressions/functions/parsing)。

## 数据质量与指标状态

- 顶层 `day_coverage` 列出十四个 UTC 日各自的 `required_tables / missing_tables / status`。每份日报附 `window`（UTC 左闭右开）和 `table_coverage`；缺表不生成该日零值日报，查询／认证失败仍以非零退出码报错。
- 日报 `quality` 包含输入／接受记录数、质量问题计数、`count_basis=EXPORTED_EVENT_RECORDS` 和 `late_data_possible=true`。状态为 `AVAILABLE / DEGRADED / NO_DATA`；合法 unknown、非 crash/anr 的辅助退出记录本身不构成质量降级。质量计数针对已读取的 App／环境／事件范围；不同问题可涉及同一条记录，不能把问题计数相加当事件总量。
- 每事件 `quality` 区分缺失／非法账号、缺少分析实例或版本、不支持的平台、缺失／非法原因、缺失／非法媒体上下文。匿名与缺原因事件保留在观察次数；非法原因原文不回写报告，而使用质量代码归类。辅助退出信号仍单列，仅 crash/anr 可触发对应取证规则。
- `result_rate` 及各平台／版本结果率新增 `result_rate_status`：`AVAILABLE`，或 `UNAVAILABLE_NO_DENOMINATOR / UNAVAILABLE_ZERO_DENOMINATOR / UNAVAILABLE_AMBIGUOUS_PARAMETERS / UNAVAILABLE_INCONSISTENT_DENOMINATOR`。重复参数导致相关分子或分母被排除时，不发布看似正常的比率。失败上报存在而完成上报为零时，只要口径有效，失败率仍可为 100%。
- 比率按事件上报记录计算；没有新增业务尝试去重。完整分子／分母使用相同 UTC 窗口、平台和版本。输入必须携带 SQL 返回的重复参数计数，不能把未知计数当零。

## 环比与七日基线

保留原 `previous_day / baseline / baseline_days_available` 明细，新增每事件 `previous_day_comparison / baseline_comparison`，分别包含 `records / identified_accounts / result_rate`：

| 字段 | 含义 |
|---|---|
| `current / reference / delta / relative_change` | 当前值、前日值或基线中位数、绝对差、相对变化；相对变化为比例，例如 1 表示增长 100% |
| `delta_percentage_points` | 仅结果率提供，结果率差乘 100，例如 10% 到 15% 为 5 个百分点 |
| `status / unavailable_reason` | 正常、部分基线、当前指标不可用、前日／基线缺失或参考指标不可用；歧义记录不参与可比值 |
| `reference_days / expected_reference_days` | 当前指标实际可比天数与期望天数；账号归属覆盖不足时账号数不强行比较 |
| `change_status` | 完整参考范围全零且当期非零才标 `NEW`；部分基线或中位数为零但历史非全零时为 `ZERO_REFERENCE`，相对变化留 null；不产生无穷大 |

日报 `baseline_summary` 说明 `MEDIAN` 方法、可用天数、缺失日期和完整／部分／缺失状态。各指标剔除不可比参考值后各自报告天数，不把缺失日补零。基线只包含统计日前七日；比较结果用于观察，`trend_collection_enabled=false` 保持不变，不能把 `NEW` 当自动派单授权。

## 候选解释与账号漏斗

- `candidate_pool` 附 `group_records / account_share / priority_reason`，与已有命中规则、次数、组影响账号、版本、最近时间及顶层 policy 一起解释为何命中。
- 每个候选和建议记录附 `selection`：选中预览 `SELECTED_PREVIEW`、合并到已选账号 `MERGED_INTO_SELECTED_ACCOUNT`、每组满额 `GROUP_LIMIT`、本次总量满额 `TOTAL_ACCOUNT_LIMIT`。保留对应选中候选键、选样次序和 `budget_scope=CURRENT_RUN`。未选中记录仍保留在候选池中。
- `candidate_exclusions` 记录一个主要排除原因及账号／事件／平台／日期、次数和最近时间。原因包括参数歧义、平台不支持、原因或媒体上下文不合法、预期行为、缺失／非法账号、过旧／未来时间、非 crash/anr 退出和未达阈值；不包含非法原因原文或非法账号原文。
- `candidate_summary.funnel` 的四层为 `observed_accounts / eligible_accounts / matched_accounts / proposed_accounts`，均按本次实际参与筛选的统计日集合去重业务账号。基线日不混入候选范围；各层账号不重复累加，事件条数或异常组数不作为账号转化率。
- 两类 `*_observations_by_reason` 统计排除观察项或候选决策项的数量，不是独立账号数。匿名记录继续保留于质量和排除解释，不伪造业务账号。
- 以上结果可能包含业务账号，继续只写权限 0600 的私有 JSON，不进入公开日报或标准输出日志。

## 验证范围

既有十二项分析检查通过；合成输入验证 UTC 跨表、四十规则、完整分母、媒体原因及跨状态累计、候选池与跨补算预算、缺表等待、私有 CLI 输出。未做生产 UTC 全量回放、阈值准确率评估或后端联调；旧二十二失败事件汇总不能代替这项验证。

2026-10-29 分析打磨：运行既有十二项检查和三十五个离线／CLI 核对点，覆盖质量状态、预期与非预期 blocked、前日与七日基线、参考为零、两级限额、跨日合并、同单位漏斗及 0600 输出；没有新增单元测试文件。原始 spec 的工程决策与限定审查保留在工作区 `.scratch/analytics-triggered-log-collection/`。
