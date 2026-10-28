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
| 日报 | 正式四十事件、Top10、业务账号去重、原因、结果率、平台／版本分布与各自分母 |
| 分析用户 | `analytics_users` 为原始 `user_pseudo_id` 去重数；空值记录单列，不等同 Data API 的 totalUsers／activeUsers |
| 原因归并 | 事件＋平台＋正式原因；媒体先区分 error_source，再按 failure_reason 归组，sync_state 仅作证据 |
| 关键信号 | 明确 crash/anr、笔记终态失败、合法 decode_error／file_missing 至少一条 |
| SDK／网络 | 同账号同组 SDK／明确 unknown 等至少二条，网络／超时至少三条 |
| 影响面／持续高频 | 合格 Top10 异常组至少三个账号；或单账号十条且占组记录至少一半 |
| 预期行为 | 取消、权限拒绝等预期原因不自动进入；缺字段／非法枚举不冒充 unknown |
| 趋势 | 保留前日／基线观察，新发、突增、结果率提级暂不触发采集 |

`candidate_pool` 保留所有可解释候选；`candidate_proposals` 是跨本次补算日期合并的限额预览：最多二十账号，同优先级先每组一个再补至每组三个，账号只选一次。最近异常超过 168 小时仅进日报。可用 JSON `--policy` 覆盖初始参数；变更产品额度仍需业务确认。

后端应从候选池校验账号／平台／兼容安装／诊断授权，关联已有任务，并在持久事务内完成任务创建 UTC 日二十账号、每组最多三、账号滚动二十四小时冷却和幂等。不能直接把预览名单当可派单结果，不能把重跑预览当额度已扣减。任务先登记再发 FCM 提示。

## 验证范围

既有十二项分析检查通过；合成输入验证 UTC 跨表、四十规则、完整分母、媒体原因及跨状态累计、候选池与跨补算预算、缺表等待、私有 CLI 输出。未做生产 UTC 全量回放、阈值准确率评估或后端联调；旧二十二失败事件汇总不能代替这项验证。
