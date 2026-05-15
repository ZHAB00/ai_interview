export const STAGES = ['初筛', 'HR面', '技术面', '终面']

export const DIFFICULTY_MAP = {
  '初级': 'junior',
  '中级': 'mid',
  '高级': 'senior'
}

export const INTERVIEW_MODE = {
  FULL: 'full',
  STAGE: 'stage'
}

export const INTERVIEW_STATUS = {
  CREATED: 'created',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  ABANDONED: 'abandoned'
}

export const AI_STATUS = {
  LISTENING: 'listening',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  MUTED: 'muted'
}

export const QUESTION_TYPES = {
  TECHNICAL: 'technical',
  BEHAVIORAL: 'behavioral',
  SITUATIONAL: 'situational'
}

export const DIMENSIONS = ['技术深度', '技术广度', '工程化思维', '沟通逻辑', '项目经验匹配度']

export const PASS_THRESHOLD = 60

export const MAX_INTERVIEW_DURATION = 45 * 60 // 45 minutes in seconds

export const WS_RECONNECT_MAX = 3
export const WS_RECONNECT_INTERVALS = [1000, 3000, 5000]

export const REPORT_POLL_INTERVAL = 5000 // 5 seconds

export const ETHICS_STATEMENT = '此评分为模拟练习参考，不构成真实招聘决策依据'

export const QUICK_REPLIES = [
  '可以再说一遍吗',
  '请换一种问法',
  '跳过这个问题'
]
