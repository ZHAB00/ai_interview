"""Report agent - generates comprehensive interview reports."""

import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """Agent responsible for generating the final interview report.

    Aggregates all scored answers, calculates resume deductions, generates
    stage-by-stage breakdowns, overall comments, and improvement suggestions.
    """

    @property
    def system_prompt(self) -> str:
        return (
            "你是一个专业的面试报告分析师，负责生成面试评估报告。\n\n"
            "你的职责：\n"
            "1. 综合所有面试回答的评分，生成各阶段总结\n"
            "2. 分析简历匹配度，计算合理的简历扣分\n"
            "3. 撰写总体评价，指出核心优势和需要改进的方向\n"
            "4. 给出具体的提升建议\n\n"
            "报告原则：\n"
            "- 客观公正，基于实际回答评分\n"
            "- 评价具有建设性，指出不足的同时给出改进路径\n"
            "- 简历扣分仅在技能、经验与岗位要求有明显差距时应用\n"
            "- 扣分范围一般 0-15 分，特殊严重情况可达 20 分\n\n"
            "请严格按照以下 JSON 格式返回报告摘要：\n"
            "{\n"
            '  "overall_comment": "总体评价，150-300字",\n'
            '  "stage_summaries": [\n'
            '    {"stage": "初筛", "summary": "阶段评价", "highlights": ["亮点"], "concerns": ["问题"]}\n'
            "  ],\n"
            '  "resume_deduction": 0-20,\n'
            '  "deduction_reason": "扣分理由，如无扣分则为空字符串",\n'
            '  "improvement_suggestions": ["建议1", "建议2", "建议3"],\n'
            '  "key_strengths": ["核心优势1", "核心优势2"],\n'
            '  "key_weaknesses": ["主要不足1", "主要不足2"]\n'
            "}\n"
        )

    async def generate_report(
        self,
        position: str,
        difficulty: str,
        answers: list[dict],
        position_match_score: int | None = None,
        match_feedback: str | None = None,
        stage_summaries: list[dict] | None = None,
        jd_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate the full interview report."""
        logger.info(f"开始生成报告: position={position}, answer_count={len(answers)}")

        answers_summary = "\n".join(
            f"阶段：{a.get('stage', '未知')} | "
            f"题目：{a.get('question_text', '')} | "
            f"得分：{a.get('score', 0)}/100 | "
            f"反馈：{a.get('feedback', '')}"
            for i, a in enumerate(answers)
            if not a.get("type")  # skip coding_challenge entries
        )

        match_info = ""
        if position_match_score is not None:
            match_info = (
                f"岗位匹配度：{position_match_score}/100\n"
                f"匹配反馈：{match_feedback or '无'}\n"
            )

        # JD match context
        jd_info = ""
        if jd_analysis:
            jd_skills = jd_analysis.get("skills", [])
            jd_reqs = jd_analysis.get("requirements", [])
            if jd_skills or jd_reqs:
                jd_info = "\n【招聘JD要求】\n"
                if jd_skills:
                    jd_info += f"要求技术栈：{', '.join(jd_skills)}\n"
                if jd_reqs:
                    jd_info += f"职责要求：{'；'.join(jd_reqs)}\n"
                jd_info += (
                    "请在报告中补充一个 'jd_match' 字段，包含：\n"
                    "- covered_skills: 候选人掌握并正确回答的JD技能\n"
                    "- missed_skills: JD要求但候选人明显不熟悉的技能\n"
                    "  注意：若JD中某些技能是'至少掌握一种'的条件，"
                    "候选人满足其中一种即视为覆盖，未涉及的其他技能不算遗漏。\n"
                    "- jd_match_score: 候选人对JD要求的整体匹配度(0-100)\n"
                )

        stage_info = ""
        if stage_summaries:
            stage_info = "面试阶段评价：\n" + "\n".join(
                f"- {s.get('stage', '')}: {s.get('summary', '')}"
                for s in stage_summaries
            ) + "\n"

        messages = [{
            "role": "user",
            "content": (
                f"岗位：{position}\n"
                f"难度：{difficulty}\n"
                f"{match_info}"
                f"{jd_info}"
                f"{stage_info}\n"
                f"各题回答及评分：\n{answers_summary}\n\n"
                f"请基于以上信息生成面试报告摘要，包括总体评价、各阶段总结、"
                f"简历扣分（如需要）和改进建议。返回 JSON 格式。"
            ),
        }]

        result = await self.llm_call_json(messages=messages)
        logger.info(f"报告生成完成: deduction={result.get('resume_deduction', 0)}")
        return result
