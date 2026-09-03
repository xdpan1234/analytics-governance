# GA4 启动与登录报表

这份文档定义了启动与账号登录健康度对应的固定 GA4 报表资产。

请以以下正式协议为准：

- `analytics_schema/app_basic.yaml`
- `analytics_schema/account.yaml`
- `docs/tracking-plan.md`

不要把已经废弃的 `app_login_*` 事件混入这些报表。登录相关报表只使用：

- `account_login_started`
- `account_login_completed`
- `account_login_failed`

## 适用范围

这组报表覆盖以下主题：

- 启动健康度
- 启动降级原因拆解
- 登录漏斗
- 登录失败拆解
- 账号可用态漏斗

这些报表面向 GA4 Reports Library、日常巡检、提测验证和发布前回归。

## 需要先注册的 GA4 自定义定义

在创建完整报表集之前，先注册以下事件级自定义维度：

| 参数 | 来源模块 | 优先级 | 使用场景 |
| --- | --- | --- | --- |
| `platform` | 适配器注入公共元数据 | P0 | 全部报表 |
| `environment` | 适配器注入公共元数据 | P0 | 全部报表 |
| `build_region` | 适配器注入公共元数据 | P0 | 全部报表 |
| `failure_reason` | app + account | P0 | 启动降级、登录失败 |
| `degraded_component` | app | P0 | 启动降级 |
| `sign_in_type` | account | P0 | 登录漏斗、登录失败 |
| `surface` | app + account | P0 | 登录失败、账号可用态 |
| `entry_point` | app + account | P1 | 登录入口、失败拆解 |
| `trigger_source` | app + account | P1 | QA 深挖、会话恢复场景分析 |

仅供 QA 或辅助排查使用，可选注册：

| 参数 | 说明 |
| --- | --- |
| `has_push_token` | 可用于启动相关 QA，不属于这套核心报表的必需字段 |

不要注册或上传原始错误文本、URL、token、用户标识、堆栈等 Tracking Plan 已禁止的字段。

## 报表命名规范

为了方便在 GA4 Reports Library 中统一检索，所有报表建议使用以下前缀：

- `App Boot -`
- `Account -`

## 报表 1：启动总览

### GA4 报表名

`App Boot - Overview`

### 目标

作为日常固定启动健康面板，用于版本巡检和应用健康度观察。

### 核心事件

- `app_boot_started`
- `app_boot_completed`
- `app_boot_degraded`

### 建议摘要卡片

- `app_boot_started` 的 Event count
- `app_boot_completed` 的 Event count
- `app_boot_degraded` 的 Event count

### 建议明细表

维度：

- `Event name`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 匹配正则 `app_boot_(started|completed|degraded)`

建议比较：

- `platform`
- `environment`

### 用途

- 每日启动流量巡检
- Android / iOS 启动量对比
- 测试环境与生产环境基础校验

## 报表 2：启动完成按平台和区域拆分

### GA4 报表名

`App Boot - Completion By Platform Region`

### 目标

观察启动成功量是否在平台、环境或区域维度上发生偏移。

### 核心事件

- `app_boot_completed`

### 建议明细表

维度：

- `platform`
- `environment`
- `build_region`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 精确匹配 `app_boot_completed`

### 用途

- 版本发布对比
- 分区域灰度验证
- 平台偏斜检测

## 报表 3：启动降级原因拆解

### GA4 报表名

`App Boot - Degradation Breakdown`

### 目标

定位哪些非致命启动失败正在影响用户，但应用仍然进入可用状态。

### 核心事件

- `app_boot_degraded`

### 建议图表

- 按 `failure_reason` 的 donut
- 按 `failure_reason` 与 `degraded_component` 的明细表

### 建议明细表

维度：

- `failure_reason`
- `degraded_component`
- `platform`
- `environment`
- `build_region`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 精确匹配 `app_boot_degraded`

### 用途

- 启动事故排查
- 受控降级 QA 验证
- 分区域启动问题复盘

## 报表 4：登录总览

### GA4 报表名

`Account - Login Overview`

### 目标

基于迁移后的 `account_login_*` 事件族，提供固定登录健康面板。

### 核心事件

- `account_login_started`
- `account_login_completed`
- `account_login_failed`

### 建议摘要卡片

- `account_login_started` 的 Event count
- `account_login_completed` 的 Event count
- `account_login_failed` 的 Event count

### 建议明细表

维度：

- `Event name`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 匹配正则 `account_login_(started|completed|failed)`

建议比较：

- `platform`
- `environment`

### 用途

- 每日登录健康度巡检
- 版本间登录稳定性比较
- 快速确认废弃的 `app_login_*` 是否已停止使用

## 报表 5：登录完成按登录方式拆分

### GA4 报表名

`Account - Login Completion By Sign In Type`

### 目标

比较 email、Google、Apple 和 session-restore 等路径的登录完成情况。

### 核心事件

- `account_login_completed`

### 建议明细表

维度：

- `sign_in_type`
- `platform`
- `environment`
- `build_region`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 精确匹配 `account_login_completed`

### 用途

- 登录方式成功量对比
- 会话恢复路径监控
- 平台偏差诊断

## 报表 6：登录失败拆解

### GA4 报表名

`Account - Login Failure Breakdown`

### 目标

拆解用户在进入账号可用态之前的登录或会话恢复失败原因。

### 核心事件

- `account_login_failed`

### 建议图表

- 按 `failure_reason` 的 donut
- 按 `sign_in_type`、`entry_point`、`surface` 的明细表

### 建议明细表

维度：

- `failure_reason`
- `sign_in_type`
- `entry_point`
- `surface`
- `platform`
- `environment`
- `build_region`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 精确匹配 `account_login_failed`

### 用途

- 发布阻断项巡检
- 登录失败根因拆解
- 区分用户主动登录失败与会话恢复失败

## 报表 7：登录入口拆解

### GA4 报表名

`Account - Login Entry Breakdown`

### 目标

查看正式登录或会话恢复尝试是从哪些入口和触发源开始的。

### 核心事件

- `account_login_started`

### 建议明细表

维度：

- `entry_point`
- `trigger_source`
- `sign_in_type`
- `platform`

指标：

- `Event count`
- `Total users`

筛选条件：

- `Event name` 精确匹配 `account_login_started`

### 用途

- 会话恢复占比分析
- deep link / notification 登录入口验证
- QA 检查枚举值是否符合协议

## 漏斗 1：启动完成漏斗

### 资产名

`App Boot - Completion Funnel`

### 漏斗步骤

1. `app_boot_started`
2. `app_boot_completed`

### 建议拆分维度

- `platform`
- `environment`
- `build_region`

### 目标

- 跟踪冷启动完成率
- 比较 Android / iOS 启动成功表现

## 漏斗 2：账号登录漏斗

### 资产名

`Account - Login Funnel`

### 漏斗步骤

1. `account_login_started`
2. `account_login_completed`

### 建议拆分维度

- `sign_in_type`
- `platform`
- `environment`

### 目标

- 跟踪登录完成率
- 比较 email、Google、Apple 和 restore 路径表现

## 漏斗 3：账号可用态漏斗

### 资产名

`Account - Usable State Funnel`

### 漏斗步骤

1. `app_boot_completed`
2. `account_login_completed`

### 建议拆分维度

- `platform`
- `environment`
- `build_region`
- `sign_in_type`

### 目标

- 衡量启动成功后，有多少流量真正进入账号可用态
- 识别启动完成后卡在 auth-restore 或登录流程的问题

## 创建顺序建议

建议按以下顺序创建这些资产：

1. 注册所需自定义维度
2. 创建 `App Boot - Overview`
3. 创建 `App Boot - Degradation Breakdown`
4. 创建 `Account - Login Overview`
5. 创建 `Account - Login Failure Breakdown`
6. 创建三个漏斗
7. 补齐剩余拆分型报表

## 验证清单

- 确认在 GA4 DebugView 中，`app_boot_started` 出现在 `app_boot_completed` 之前。
- 确认 `app_boot_degraded` 带有批准过的 `failure_reason` 和 `degraded_component`。
- 确认 `account_login_started`、`account_login_completed`、`account_login_failed` 仅使用批准过的枚举值。
- 确认同一条受控登录行为不会再次发送废弃的 `app_login_*`。
- 确认报表和漏斗都可以按 `platform` 拆分，而无需区分 Android 专用或 iOS 专用事件名。
- 确认没有任何报表依赖原始错误文本、URL、token、request id、response body 或 PII。

## 后续建议

如果后续要做定时分发：

- 固定报表优先使用 GA4 原生的定时报表邮件。
- 只有在需要推送到飞书、Slack 或其他 webhook 时，再引入 GA4 Data API。
