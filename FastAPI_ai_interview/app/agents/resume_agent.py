"""Resume analysis agent - parses resume text and calculates position match."""

import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ResumeAgent(BaseAgent):
    """Agent responsible for analyzing resume content and matching against target positions."""

    @property
    def system_prompt(self) -> str:
        return (
            "你是专业的简历分析助手。你需要从简历文本中提取出结构化信息，"
            "并评估候选人与目标岗位的匹配度。\n\n"
            "请严格按照以下 JSON 格式返回结果：\n"
            "{\n"
            '  "name": "姓名",\n'
            '  "phone": "手机号",\n'
            '  "email": "邮箱",\n'
            '  "education": [{"school": "学校", "degree": "学历", "major": "专业", "year": "毕业年份"}],\n'
            '  "skills": ["技能1", "技能2"],\n'
            '  "work_experience": [{"company": "公司", "position": "职位", "duration": "时间", "description": "描述"}],\n'
            '  "project_experience": [{"name": "项目名", "role": "角色", "description": "描述"}],\n'
            '  "position_match_score": 0-100,\n'
            '  "match_feedback": "匹配度分析和建议（中文，简洁）"\n'
            "}\n\n"
            "注意：评估应当客观，岗位匹配度基于技能、经验与目标岗位的相关性计算。"
        )

    async def analyze(self, resume_text: str, position: str) -> dict[str, Any]:
        """Analyze resume text and return structured data with match score."""
        logger.info(f"开始解析简历: position={position}, text_length={len(resume_text)}")

        messages = [
            {
                "role": "user",
                "content": (
                    f"目标岗位：{position}\n\n"
                    f"简历文本：\n{resume_text[:8000]}"
                ),
            }
        ]

        result = await self.llm_call_json(messages=messages)

        logger.info(
            f"简历解析完成: name={result.get('name')}, "
            f"match_score={result.get('position_match_score')}"
        )
        return result
