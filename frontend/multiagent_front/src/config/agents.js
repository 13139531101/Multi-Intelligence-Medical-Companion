/**
 * 阶段48-config: 智能体名称配置
 * 所有智能体显示名在此集中定义，前端组件从这里引用
 * 支持通过环境变量覆盖（VITE_ 前缀）
 *
 * 用法: import { AGENTS } from '@/config/agents'
 * 或直接用: import { HEALTH_ADVISOR_NAME } from '@/config/agents'
 */
export const HEALTH_ADVISOR_NAME = import.meta.env.VITE_HEALTH_ADVISOR_NAME || '健康顾问'
export const HEALTH_RECORDS_NAME = import.meta.env.VITE_HEALTH_RECORDS_NAME || '健康档案'
export const MEDICATION_REMINDER_NAME = import.meta.env.VITE_MEDICATION_REMINDER_NAME || '用药提醒'
export const VISIT_SUMMARY_NAME = import.meta.env.VITE_VISIT_SUMMARY_NAME || '就诊摘要'

// 完整 agent 列表（含颜色）
export const AGENTS = [
  {
    id: 'health_advisor',
    name: HEALTH_ADVISOR_NAME,
    en: 'health_advisor',
    color: '#1565C0',
  },
  {
    id: 'health_records',
    name: HEALTH_RECORDS_NAME,
    en: 'health_records',
    color: '#00897B',
  },
  {
    id: 'medication_reminder',
    name: MEDICATION_REMINDER_NAME,
    en: 'medication_reminder',
    color: '#7B1FA2',
  },
  {
    id: 'visit_summary',
    name: VISIT_SUMMARY_NAME,
    en: 'visit_summary',
    color: '#E65100',
  },
]
