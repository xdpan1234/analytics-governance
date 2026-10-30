const labels: Record<string, string> = {
  WAITING_EXPORT: '等待导出', AVAILABLE: '可用', DEGRADED: '存在质量缺口', NO_DATA: '无数据', SUCCEEDED: '归档成功',
  SELECTED_PREVIEW: '预览选中', MERGED_INTO_SELECTED_ACCOUNT: '合并到已选账号', TOTAL_ACCOUNT_LIMIT: '本次账号总额限制',
  GROUP_LIMIT: '本次分组上限', UNRESOLVED: '实例目标未解析', KEY_SIGNAL: '关键异常信号', SDK_OR_UNKNOWN: 'SDK 或未知错误',
  NETWORK_OR_TIMEOUT: '网络或超时', TOP10_IMPACT: '日报 Top10 影响', EXPECTED_BEHAVIOR: '预期行为排除', BELOW_THRESHOLD: '低于阈值',
  INVALID_REASON: '原因值不符合契约', MISSING_ACCOUNT: '缺少合法账号', NON_CRASH_EXIT: '非已支持崩溃退出',
  AMBIGUOUS_PARAMETERS: '参数歧义', APPROVED_UNKNOWN: '合法 unknown', HYPOTHESIS: '待验证假设', UNVERIFIED: '尚未由日志验证',
  VALID: '有效', MEDIAN: '中位数', SINGLE_ACCOUNT_NOISE: '单账号集中异常', UNAVAILABLE_NO_DENOMINATOR: '无分母，结果率不可计算',
}
export const label = (value: string | null | undefined) => value == null ? '未知' : (labels[value] ?? value)
export function metric(value: number | null | undefined, percent = false): string {
  if (value == null) return '不可计算'
  return percent ? `${(value * 100).toFixed(2)}%` : value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}
export const utc = (value: string) => value.replace('T', ' ').replace(/(?:\+00:00|Z)$/, ' UTC')
