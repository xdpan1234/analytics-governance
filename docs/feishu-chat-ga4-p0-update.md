### AI 聊天

#### 当前实现状态

- Android P0 已完成，代码以 Enter-Glass-Android PR #390（`codex/analytics-foundation-chat-p0`）为准。
- iOS 尚未完成；后续应按同一事件名、同一必填属性和同一 enum 值对齐实现。
- 本章节替换旧的全量草案。旧草案中的部分事件没有在 App 侧实现，不能作为正式埋点口径。

#### Analytics Goal & Boundary

- 这组统计先回答 AI Chat 核心链路：是否进入 Chat、是否打开会话、是否发送消息、AI 响应是否完成或失败、语音会话是否启动/失败/结束、用户是否提交反馈。
- P0 只覆盖 Android/iOS 都能稳定对齐的技术边界。图片上传拆分、列表加载失败、会话操作、KWS 独立事件、工具调用、加密响应等保留在 backlog，不在当前 Android P0 中发送。
- 不采集聊天正文、prompt、answer、语音转写、音频、图片内容、文件名、conversationId/messageId、tool arguments、email/nickname/serialNumber、原始错误、响应体或堆栈。

#### P0 已完成事件

| 事件 | Android 状态 | 触发边界 | 必填属性 | 可选属性 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `chat_list_viewed` | 已完成 | Chat 列表或默认会话区域可见 | `entry_point`, `surface` | `trigger_source` | 进入 Chat 时作为入口曝光分母 |
| `chat_session_opened` | 已完成 | 打开默认、历史或恢复会话 | `surface`, `open_mode` | `entry_point`, `trigger_source` | Android local chat 为 `default_session`，历史会话为 `history_session`，无 index 的非 local 会话为 `restored_session` |
| `chat_message_sent` | 已完成 | 用户提交文本或带图消息 | `surface`, `message_mode` | `entry_point`, `trigger_source` | 不上传文本、附件名、图片 URL 或 message id |
| `chat_response_completed` | 已完成 | AI 响应正常结束并形成可见结果 | `surface`, `message_mode` | `entry_point`, `trigger_source` | 图片问答完成也归入 `message_mode=image` |
| `chat_response_failed` | 已完成 | AI 响应、取消、中断、超时或图片准备失败 | `failure_reason`, `surface`, `message_mode` | `entry_point`, `trigger_source` | 图片上传/解码/文件缺失失败先归入该事件 |
| `chat_voice_started` | 已完成 | 语音会话成功进入 starting/active 边界 | `entry_point`, `surface`, `voice_source` | `trigger_source` | Android 当前来源为 app voice、device Bluetooth、KWS wake |
| `chat_voice_start_failed` | 已完成 | 语音会话启动前失败 | `failure_reason`, `surface`, `voice_source` | `entry_point`, `trigger_source` | 失败前未进入 started 边界，不补打 started |
| `chat_voice_ended` | 已完成 | 已启动的语音会话终止 | `surface`, `voice_source`, `termination_reason` | `entry_point`, `trigger_source` | Android 当前只产生手动停止、硬件命令、系统中断、音频超时 |
| `chat_feedback_submitted` | 已完成 | Good/Bad/report issue 用户动作提交 | `surface`, `feedback_action` | `feedback_issue_type`, `feedback_issue_count_bucket`, `entry_point`, `trigger_source` | report issue 多选只打一条事件，用 `multiple` 和 bucket 表达 |

#### Backlog / 未完成事件

| 事件或事件族 | 优先级 | 状态 | 说明 |
| --- | --- | --- | --- |
| `chat_list_load_failed` | P1 | 未完成 | 只有需要单独分析列表加载质量时再加；当前不进入 Android P0 |
| `chat_response_started` | P1 | 未完成 | 当前不做 started/completed 精细漏斗和响应时长指标 |
| `chat_image_upload_started/completed/failed` | P1 | 未完成 | 当前不单独拆图片上传；上传/准备失败先用 `chat_response_failed(message_mode=image)` |
| `chat_session_action_requested/completed/failed` | P1 | 未完成 | 新建、打开历史、删除、中断等会话动作后续再单独分析 |
| `chat_feedback_completed/failed` | P1 | 未完成 | 当前只记录用户提交意图，不记录 report issue 后端提交结果 |
| `chat_kws_wake_triggered/failed` | P1 | 未完成 | 当前通过 `voice_source=kws_wake` 体现在 voice 事件里 |
| `chat_tool_call_started/completed` | P2 | 未完成 | 等两端都有稳定、低基数、无参数内容的 tool 事件源后再纳入 |
| `chat_encrypted_response_viewed/toggled` | P2 | 未完成 | 属于隐私功能使用分析，低于核心 Chat 漏斗优先级 |
| `chat_tool_call_failed` | Future | 未完成 | 当前两端没有稳定 tool failure 边界 |
| `memory_*` / Settings memory events | Future | 未完成 | Memory 管理不归属 Chat，未来应走 `memory_*` 或 Settings |
| `chat_kws_toggle_updated` | Do not add | 不实现 | KWS 开关归属 `device_setting_updated(setting_type=kws_toggle)`，Chat 不重复定义 |
| `chat_shortcut_*` | Do not add | 不实现 | 不单独定义 shortcut 事件；iOS Siri/AppIntent 用 `voice_source=siri_shortcut` 或 `entry_point=app_shortcut` 表达 |

#### 删除 / 废弃的旧草案名

以下名称来自旧全量草案或早期讨论，当前不从 App 侧发送，也不应和 P0 新事件双发：

| 旧名称 | 当前口径 |
| --- | --- |
| `voice_chat_started` / `voice_chat_completed` / `voice_chat_failed` | 改为 `chat_voice_started`、`chat_voice_start_failed`、`chat_voice_ended + termination_reason` |
| `chat_voice_completed` / `chat_voice_failed` | 合并到 `chat_voice_ended + termination_reason`；启动前失败用 `chat_voice_start_failed` |
| `image_chat_started` / `image_chat_completed` / `image_chat_failed` | 当前不发送；图片结果归入 `chat_response_completed/failed(message_mode=image)` |
| `chat_image_started` / `chat_image_completed` / `chat_image_failed` | 当前不发送；未来如拆上传，使用 `chat_image_upload_*` |
| `chat_switch_requested` / `chat_switch_completed` / `chat_switch_failed` | 当前不发送；未来统一为 `chat_session_action_*` |
| `shortcut_chat_started` / `shortcut_chat_completed` / `shortcut_chat_failed` | 当前不发送；通过 `entry_point` 或 `voice_source` 表达入口 |
| `memory_action_started` / `memory_action_completed` / `memory_action_failed` | 不归属 Chat；未来走 `memory_*` 或 Settings |
| `kws_toggle_updated` / `chat_kws_toggle_updated` | 归属 Device 设置事件 |
| `kws_triggered` / `kws_trigger_failed` | 当前不发送；未来如需要，使用 `chat_kws_wake_triggered/failed` |
| `tool_call_started` / `tool_call_completed` / `tool_call_failed` | 当前不发送；未来如需要，使用 `chat_tool_call_*` 并只传低基数 `tool_type` |

#### 参数与枚举

所有事件继续由 adapter 注入公共参数：`platform`、`environment`、`build_region`、`build_type`、`app_version_name`、`app_version_code`。

| 参数 | 取值 |
| --- | --- |
| `surface` | `chat`, `unknown` |
| `entry_point` | `chat_tab`, `home`, `device`, `kws`, `siri_shortcut`, `app_shortcut`, `deep_link`, `push`, `system_share`, `unknown` |
| `trigger_source` | `user`, `system`, `device`, `server_push`, `unknown` |
| `open_mode` | `default_session`, `history_session`, `restored_session`, `unknown` |
| `message_mode` | `text`, `image`, `unknown` |
| `voice_source` | Android 当前子集：`device_bluetooth`, `app_voice_chat`, `kws_wake`, `unknown`；`siri_shortcut` 为 iOS-only |
| `termination_reason` | Android 当前子集：`manual_stop`, `hardware_command`, `system_interrupt`, `audio_timeout`；跨端允许值还包括 `ai_completed`, `rtc_failed`, `remote_disconnect`, `credits_exhausted`, `connection_timeout`, `hardware_disconnect`, `tool_execution_completed`, `unknown` |
| `feedback_action` | `thumbs_up`, `thumbs_down`, `report_issue` |
| `feedback_issue_type` | `couldnt_hear_me`, `misheard_me`, `interrupted_me`, `responded_too_slowly`, `voice_didnt_sound_right`, `didnt_like_responses`, `other`, `multiple`, `unknown` |
| `feedback_issue_count_bucket` | `0`, `1`, `2`, `3_plus` |
| `failure_reason` | `network_error`, `permission_denied`, `validation_failed`, `timeout`, `unauthorized`, `cancelled`, `interrupted`, `unsupported_state`, `device_disconnected`, `upload_failed`, `file_missing`, `decode_error`, `unsupported_format`, `sdk_error`, `unknown` |

反馈多选规则：`chat_feedback_submitted` 每次用户提交只打一条。如果选择 1 个 issue，填具体 `feedback_issue_type`；如果选择多个，填 `feedback_issue_type=multiple` 并填 `feedback_issue_count_bucket`。不传数组，不用多条 submitted 事件放大主漏斗计数。

#### GA4 Custom Definitions

建议注册 event-scoped custom dimensions：

`entry_point`, `surface`, `trigger_source`, `open_mode`, `message_mode`, `voice_source`, `termination_reason`, `feedback_action`, `feedback_issue_type`, `feedback_issue_count_bucket`, `failure_reason`, `platform`, `environment`, `build_region`。

P0 不新增 custom metrics。响应时长、语音时长、上传时长等指标等两端都能稳定记录起止时间后，再补 `*_duration_ms` terminal metrics。

#### Android 验证 Checklist

- 开启 Android app stream 的 GA4 DebugView。
- 进入 Chat，确认 `chat_list_viewed` 和 `chat_session_opened` 只发送一次，`entry_point`、`surface`、`open_mode` 使用批准值。
- 发送文本消息，确认成功链路为 `chat_message_sent -> chat_response_completed(message_mode=text)`。
- 发送带图消息，确认 `message_mode=image`；图片准备失败只用 `chat_response_failed(message_mode=image, failure_reason=upload_failed/file_missing/decode_error/unsupported_format)`。
- 模拟响应网络错误、超时、取消、中断和不支持状态，确认只发送 `chat_response_failed`，不同时发送 `chat_response_completed`。
- 从 App voice、设备蓝牙、KWS wake 启动语音，确认 `chat_voice_started` 使用 Android 当前 `voice_source` 子集。
- 断网、权限拒绝、RTC 初始化失败、KWS 后续启动失败等启动前失败，确认发送 `chat_voice_start_failed`，且同一次尝试不补发 `chat_voice_started`。
- 已启动语音通过手动停止、硬件命令、系统中断、音频超时结束时，确认 `chat_voice_ended` 只使用 Android 当前 `termination_reason` 子集。
- 确认 Android 不发送 `voice_source=siri_shortcut`，也不发送 `termination_reason=ai_completed/rtc_failed/remote_disconnect/credits_exhausted/connection_timeout/hardware_disconnect/tool_execution_completed/unknown`，除非后续有真实 Android 事件源。
- 提交 thumbs up、thumbs down、单选 issue、多选 issue，确认 `feedback_action`、`feedback_issue_type`、`feedback_issue_count_bucket` 符合规则。
- 确认所有 Chat 事件都通过 Android typed analytics tracker/adapter 上报，不包含正文、ID、原始错误、堆栈、邮箱、昵称、序列号等敏感字段。

#### iOS 对齐 Checklist

- iOS 后续实现时使用同一套 P0 事件名、必填属性、可选属性和 enum 值，不新增平台专属事件名。
- 默认会话、历史会话、恢复会话使用同一套 `open_mode`。
- 文本和图片结果使用 `chat_message_sent`、`chat_response_completed`、`chat_response_failed`，通过 `message_mode` 区分。
- Siri/AppIntent/App Shortcut 语音路径可使用 iOS-only `voice_source=siri_shortcut`；KWS/Hey Memo 使用 `voice_source=kws_wake`。
- Feedback 不上传描述、邮箱、昵称、序列号或原始 API payload；多选 issue 使用单事件 bucketing 规则。
- BigQuery/DebugView 抽查同一路径在 Android/iOS 只因 `platform` 不同而分流，事件名和 enum 值不漂移。

#### 报表使用

- 入口漏斗：`chat_list_viewed -> chat_session_opened`，按 `entry_point`、`open_mode`、`platform` 拆分。
- 文本/图片响应漏斗：`chat_message_sent -> chat_response_completed/chat_response_failed`，按 `message_mode`、`failure_reason`、`platform` 拆分。
- 语音漏斗：`chat_voice_started -> chat_voice_ended`，启动前阻断看 `chat_voice_start_failed`，按 `voice_source`、`termination_reason`、`failure_reason`、`platform` 拆分。
- 反馈分布：`chat_feedback_submitted`，按 `feedback_action`、`feedback_issue_type`、`feedback_issue_count_bucket`、`platform` 拆分。
