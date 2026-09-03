# GA4 设备使用总览看板

这份文档定义《设备使用数据统计与埋点（附）》中“总览看板”在 GA4 的固定报表资产。需求来源为飞书 Wiki `NaWhwl6Eoi9hHfkGXnAc8WaenVe`，读取时间为 2026-05-12。

## 适用范围

总览看板只消费清洗后的 `device_usage_*` 事件，不直接消费原始设备事件、蓝牙日志、RPC payload 或调试日志。

本看板覆盖以下指标：

| 指标 | GA4 口径 |
| --- | --- |
| DAU | 当天满足任一有效使用行为的用户数 |
| 每日人均佩戴时长 | `device_usage_wear_session_ended` 的 `duration_ms` 累计值 / 有效使用用户数 |
| 每日人均连接时长 | `device_usage_bt_disconnected` 与 `device_usage_ble_disconnected` 的 `duration_ms` 累计值 / 有效使用用户数 |
| 每日人均核心功能使用次数 | 核心成功行为事件总次数 / 有效使用用户数 |
| 断连次数 | `device_usage_bt_disconnected` 与 `device_usage_ble_disconnected` 的 Event count |
| 低电量 warning 次数 | `device_usage_battery_warning_triggered` 且 `warning_kind` 为 `low_battery` 或 `critical_battery` 的 Event count |

## 需要先注册的 GA4 自定义定义

### 事件级自定义维度

| 参数 | 优先级 | 使用场景 |
| --- | --- | --- |
| `platform` | P0 | Android / iOS 对比 |
| `environment` | P0 | test / prod 过滤 |
| `build_region` | P0 | 区域过滤 |
| `local_hour` | P1 | 按用户本地小时分布 |
| `day_of_week` | P1 | 工作日 / 周末辅助核对 |
| `is_weekend` | P1 | 工作日 / 周末分组 |
| `warning_kind` | P0 | 低电量 warning 过滤 |
| `failure_reason` | P1 | 断连原因拆解 |
| `trigger_source` | P1 | user / system 触发来源拆解 |

不要注册 `event_id`、`session_id`、`user_id_hash`、`device_id_hash`。这些字段只用于去重、关联和 session 计算，不进入 GA4 报表维度。

### 事件级自定义指标

| 参数 | GA4 指标名 | 单位 | 使用场景 |
| --- | --- | --- | --- |
| `duration_ms` | `duration_ms` | Milliseconds | 佩戴、BT/BLE 连接、媒体播放、通话等 session 时长 |
| `battery_level` | `battery_level` | Standard | 电量 warning QA 与电量状态抽查 |

## 看板 1：设备使用总览

### GA4 报表名

`Device Usage - Overview`

### 目标

提供设备真实使用情况的日常固定看板，用于观察用户是否实际使用眼镜，以及连接、电量是否影响使用。

### 核心事件

- `device_usage_wear_session_ended`
- `device_usage_bt_disconnected`
- `device_usage_ble_disconnected`
- `device_usage_photo_capture_succeeded`
- `device_usage_video_record_ended`
- `device_usage_audio_record_ended`
- `device_usage_ai_chat_ended`
- `device_usage_media_playback_ended`
- `device_usage_call_ended`
- `device_usage_battery_warning_triggered`

### 有效使用行为口径

有效使用用户需满足任一条件：

- `device_usage_wear_session_ended` 的 `duration_ms >= 600000`
- `device_usage_photo_capture_succeeded` 的 Event count >= 1
- `device_usage_video_record_ended` 的 Event count >= 1
- `device_usage_audio_record_ended` 的 Event count >= 1
- `device_usage_ai_chat_ended` 的 Event count >= 1
- `device_usage_call_ended` 的 Event count >= 1
- `device_usage_media_playback_ended` 的 `duration_ms >= 300000`

GA4 原生 Reports Library 无法稳定表达“跨事件 OR + 单事件 duration 阈值”的精确 DAU。精确 DAU 建议放在 BigQuery 或 Looker Studio 计算；GA4 原生看板保留近似卡片和各事件明细，用于日常趋势观察与 DebugView/Realtime 验证。

### 建议摘要卡片

| 卡片 | GA4 配置 |
| --- | --- |
| 有效使用用户数（近似） | 指标 `Total users`；过滤 `Event name` 匹配核心有效行为事件；佩戴和媒体播放阈值在 GA4 原生报表中不能精确过滤时，使用 BigQuery/Looker Studio 精确看板兜底 |
| 每日人均佩戴时长 | 指标 `duration_ms`；过滤 `Event name = device_usage_wear_session_ended`；展示时在看板说明中标注单位转换为分钟 |
| 每日人均连接时长 | 指标 `duration_ms`；过滤 `Event name` 匹配 `device_usage_bt_disconnected` 或 `device_usage_ble_disconnected` |
| 核心功能使用次数 | 指标 `Event count`；过滤照片、视频、录音、AI、媒体播放、通话的成功/结束事件 |
| 断连次数 | 指标 `Event count`；过滤 `device_usage_bt_disconnected` 与 `device_usage_ble_disconnected` |
| 低电量 warning 次数 | 指标 `Event count`；过滤 `Event name = device_usage_battery_warning_triggered` 且 `warning_kind` in `low_battery`, `critical_battery` |

### 建议明细表

维度：

- `Event name`
- `platform`
- `environment`
- `build_region`

指标：

- `Event count`
- `Total users`
- `duration_ms`

筛选条件：

- `Event name` 匹配正则 `device_usage_(wear_session_ended|bt_disconnected|ble_disconnected|photo_capture_succeeded|video_record_ended|audio_record_ended|ai_chat_ended|media_playback_ended|call_ended|battery_warning_triggered)`

建议比较：

- `platform`
- `environment`
- `build_region`

## 看板 2：连接与电量风险

### GA4 报表名

`Device Usage - Connection Battery Risk`

### 目标

拆分连接时长、断连次数和低电量 warning，判断连接与电量是否影响设备真实使用。

### 建议图表

- BT / BLE 断连次数趋势：`Event count` by `Event name`
- 连接时长趋势：`duration_ms` by `Event name`
- 低电量 warning 趋势：`Event count` by `warning_kind`
- 断连原因表：`Event count` by `failure_reason`

### 筛选条件

- 连接类：`Event name` in `device_usage_bt_disconnected`, `device_usage_ble_disconnected`
- 电量类：`Event name = device_usage_battery_warning_triggered`

## 看板 3：有效行为构成

### GA4 报表名

`Device Usage - Effective Action Mix`

### 目标

观察有效使用由哪些核心功能贡献，避免 DAU 只由连接或短时佩戴撑起。

### 建议图表

- 核心行为事件占比：`Event count` by `Event name`
- 平台拆分表：`Event count`, `Total users` by `Event name`, `platform`
- 用户本地小时分布：`Event count` by `local_hour`
- 工作日 / 周末对比：`Event count` by `is_weekend`

### 核心行为事件

- `device_usage_photo_capture_succeeded`
- `device_usage_video_record_ended`
- `device_usage_audio_record_ended`
- `device_usage_ai_chat_ended`
- `device_usage_media_playback_ended`
- `device_usage_call_ended`

## GA4 UI 创建顺序

1. Admin -> Data display -> Custom definitions，注册上方 P0 维度与自定义指标。
2. 等待 GA4 自定义定义生效；新定义通常不会回填历史数据。
3. Reports -> Library 中创建 `Device Usage` collection。
4. 新建 `Device Usage - Overview` detail report，添加摘要卡片和明细表。
5. 新建 `Device Usage - Connection Battery Risk` detail report。
6. 新建 `Device Usage - Effective Action Mix` detail report。
7. 发布 collection，并在报告描述中标注“精确有效使用 DAU 以 BigQuery/Looker Studio 计算为准”。

## 验证清单

- Android DebugView 中能看到 `device_usage_wear_session_ended`，且包含 `duration_ms`、`platform`、`environment`、`build_region`。
- Android DebugView 中能看到 BT/BLE disconnect 事件，且不包含蓝牙地址、原始错误码或调试日志。
- Android DebugView 中能看到 `device_usage_battery_warning_triggered`，且 `warning_kind` 只使用 `low_battery`、`critical_battery`、`charger_plugged`、`charger_unplugged`、`unknown` 等低基数枚举。
- Reports / Explore 可按 `platform`、`environment`、`build_region` 过滤总览事件。
- Reports / Explore 中 `duration_ms` 可用于佩戴和连接时长分析。
- BigQuery 或 Looker Studio 中补齐精确有效使用 DAU，并与 GA4 近似卡片趋势一致。
