"""Scoring agent - multi-dimensional evaluation of interview answers."""

import logging
from typing import Any

from app.agents.base import BaseAgent, sanitize_user_input

logger = logging.getLogger(__name__)

SCORING_DIMENSIONS = ["技术深度", "技术广度", "工程化思维", "沟通逻辑", "项目经验匹配度"]


class ScoringAgent(BaseAgent):
    """Agent responsible for evaluating candidate answers across five dimensions.

    Analyzes answers against scoring points and sample answers, identifies
    factual errors and depth gaps, and produces structured scores.
    """

    @property
    def system_prompt(self) -> str:
        return (
            "你是一个专业的面试评分专家，负责对候选人的面试回答进行多维度评估。\n\n"
            "评分维度说明：\n"
            "- 技术深度：对技术原理、底层机制的理解程度\n"
            "- 技术广度：知识面的宽度，对相关技术和工具的掌握\n"
            "- 工程化思维：系统设计、架构、可扩展性、代码质量的考虑\n"
            "- 沟通逻辑：表达清晰度、结构化思维、逻辑严密性\n"
            "- 项目经验匹配度：回答与目标岗位实际需求的匹配程度\n\n"
            "评分标准：\n"
            "- 90-100：优秀，回答深入全面，有独到见解\n"
            "- 70-85：良好，回答基本正确，但深度或广度略有不足\n"
            "- 60-69：及格，回答有部分正确但不够深入\n"
            "- 0-59：不及格，回答有明显错误或严重不足\n\n"
            "如果候选人的回答中没有明确提到的技术细节或错误，不要虚构。"
            "只基于回答中实际展示的内容进行评估。\n\n"
            "错误分类：\n"
            "- fact_error：事实性错误，回答中出现了明确错误的知识点\n"
            "- depth_insufficient：深度不足，回答过于浅显，缺乏深入分析\n\n"
            "请严格按照以下 JSON 格式返回评分结果：\n"
            "{\n"
            '  "total_score": 0-100 的总分,\n'
            '  "dimensions": {\n'
            '    "技术深度": 0-100,\n'
            '    "技术广度": 0-100,\n'
            '    "工程化思维": 0-100,\n'
            '    "沟通逻辑": 0-100,\n'
            '    "项目经验匹配度": 0-100\n'
            "  },\n"
            '  "strengths": ["回答的优点1", "优点2"],\n'
            '  "weaknesses": ["回答的不足1", "不足2"],\n'
            '  "errors": [\n'
            '    {\n'
            '      "type": "fact_error",\n'
            '      "snippet": "候选人回答中的错误片段",\n'
            '      "correction": "正确的说法",\n'
            '      "suggestion": "改进建议"\n'
            '    }\n'
            "  ],\n"
            '  "overall_comment": "总体评价，50-100字"\n'
            "}\n"
        )

    async def score_answer(
        self,
        question_text: str,
        user_answer: str,
        scoring_points: list[dict] | None = None,
        sample_answer: str | None = None,
        stage: str = "",
        position: str = "",
        difficulty: str = "中级",
    ) -> dict[str, Any]:
        """Score a single answer across all five dimensions."""
        logger.info(f"开始评分: stage={stage}, difficulty={difficulty}")

        scoring_str = ""
        if scoring_points:
            scoring_str = "评分要点：\n" + "\n".join(
                f"- {p.get('point', '')}（满分{p.get('max_score', 0)}分）"
                for p in scoring_points
            ) + "\n"

        sample_str = ""
        if sample_answer:
            sample_str = f"参考答案：{sample_answer}\n"

        messages = [{
            "role": "user",
            "content": (
                f"面试阶段：{stage}\n"
                f"目标岗位：{position}\n"
                f"难度级别：{difficulty}\n"
                f"题目：{question_text}\n"
                f"{scoring_str}"
                f"{sample_str}"
                f"候选人回答：{sanitize_user_input(user_answer)}\n\n"
                f"请对以上回答进行五维度评分，识别事实错误和深度不足，返回 JSON 格式结果。"
            ),
        }]

        result = await self.llm_call_json(messages=messages)
        logger.info(f"评分完成: total_score={result.get('total_score')}")
        return result
