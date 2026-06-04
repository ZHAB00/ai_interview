"""Code review agent - analyzes submitted code and provides structured feedback."""

import logging
from typing import Any

from app.agents.base import BaseAgent, sanitize_user_input

logger = logging.getLogger(__name__)


class CodeReviewAgent(BaseAgent):
    """Agent responsible for reviewing candidate-submitted code.

    Analyzes code across multiple dimensions: correctness, performance,
    readability, and security, then returns structured feedback.
    """

    @property
    def system_prompt(self) -> str:
        return (
            "你是一个资深的代码评审专家（Code Review Expert）。\n\n"
            "你的职责是评审候选人提交的代码，从以下维度进行分析：\n"
            "1. 正确性：代码是否能正确解决问题？逻辑是否有误？\n"
            "2. 时间复杂度/性能：时间和空间复杂度是否合理？是否有性能瓶颈？\n"
            "3. 代码风格与可读性：命名是否规范？结构是否清晰？\n"
            "4. 安全性（如适用）：是否存在常见安全漏洞？\n\n"
            "评审原则：\n"
            "- 先指出做得好的地方，再提出改进建议\n"
            "- 对事不对人，语气建设性\n"
            "- 如果代码有严重问题，明确指出并提供正确思路\n"
            "- 考虑面试难度级别，适当调整评审严格度\n"
            "- 不要虚构代码中不存在的错误或安全问题。只基于实际代码内容进行评审\n\n"
            "请严格按照以下 JSON 格式返回评审结果：\n"
            "{\n"
            '  "overall_assessment": "整体评价（中文，50-100字）",\n'
            '  "correctness": {"score": 0-25, "comment": "正确性评价"},\n'
            '  "performance": {"score": 0-25, "comment": "性能评价"},\n'
            '  "readability": {"score": 0-25, "comment": "代码风格评价"},\n'
            '  "security": {"score": 0-25, "comment": "安全性评价（如不适用给满分并说明）"},\n'
            '  "total_score": 四项分数之和,\n'
            '  "strengths": ["优点1", "优点2"],\n'
            '  "weaknesses": ["不足1", "不足2"],\n'
            '  "improved_code": "改进后的代码（如果适用，保持原语言）",\n'
            '  "suggestions": ["改进建议1", "改进建议2"]\n'
            "}\n"
        )

    async def review(
        self,
        code: str,
        language: str,
        question_title: str,
        question_description: str,
        difficulty: str = "中级",
    ) -> dict[str, Any]:
        """Review submitted code against the given coding question."""
        logger.info(
            f"开始代码评审: language={language}, code_length={len(code)}, difficulty={difficulty}"
        )

        messages = [{
            "role": "user",
            "content": (
                f"编程题：{question_title}\n"
                f"题目描述：{question_description}\n"
                f"编程语言：{language}\n"
                f"面试难度：{difficulty}\n\n"
                f"候选人提交的代码：\n{sanitize_user_input(code[:8000])}\n\n"
                f"请对以上代码进行评审，返回JSON格式结果。"
            ),
        }]

        result = await self.llm_call_json(messages=messages)
        logger.info(f"代码评审完成: total_score={result.get('total_score')}")
        return result
