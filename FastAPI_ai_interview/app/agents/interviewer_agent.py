"""Interviewer agent — generates resume-driven questions with stage-specific behavior.

Each interview stage has a distinct personality:
  初筛: verify resume authenticity + basic competence (宽, 2-3Q, 1-2层追问)
  HR面: assess soft skills via STAR method (中, 2-3Q, 每题追问)
  技术面: deep-dive into tech stack, 3-4 layer follow-up (严, 1-2 topic)
  终面: open-ended, tech vision + product sense (中, 1-2Q)
"""

import json
import logging
from typing import Any

from app.agents.base import BaseAgent, sanitize_user_input
from app.core.logging_config import truncate

logger = logging.getLogger(__name__)

STAGE_CONFIG = {
    "初筛": {
        "max_questions": 3,
        "max_follow_ups": 2,
        "strictness": "宽松",
        "focus": "验证简历中技能基础能力的真实性。挑候选人最强技能出基础概念题，答得好快速过，答不上换一个技能问。",
        "evaluate_guide": (
            "评估标准：\n"
            "- 能正确回答基础概念 → ask_question 进入下一技能\n"
            "- 回答模糊但知道大概 → follow_up 追问1次确认\n"
            "- 完全答不上来 → ask_question 换个技能方向\n"
            "- 2-3个技能问完后 → stage_complete"
        ),
        "question_guide": (
            "出题要求：\n"
            "- 从简历中挑最强的1-2个技能出题\n"
            "- 问基础概念，不要问太深\n"
            "- 每题控制在候选人能在1-2分钟内回答的长度"
        ),
    },
    "HR面": {
        "max_questions": 3,
        "max_follow_ups": 3,
        "strictness": "中等",
        "focus": "评估团队协作、沟通能力、职业规划、工作态度。用 STAR 法（情境-任务-行动-结果）评估每个回答，缺少细节就追问。",
        "evaluate_guide": (
            "评估标准：\n"
            "- 回答有具体场景+行动+结果 → ask_question 进入下一题\n"
            "- 回答笼统缺少细节 → follow_up 追问具体情境或数据\n"
            "- 回答体现自驱力/ownership → 可快速通过\n"
            "- 回答敷衍/空洞 → follow_up 追问到具体为止\n"
            "- 3个维度问完后 → stage_complete"
        ),
        "question_guide": (
            "出题要求：\n"
            "- 评估维度：团队协作、冲突处理、职业规划、抗压能力\n"
            "- 用 STAR 追问：'当时具体是什么情况？''你做了什么？''结果是什么？'\n"
            "- 每题后根据回答补充追问缺失的 STAR 环节"
        ),
    },
    "技术面": {
        "max_questions": 2,
        "max_follow_ups": 4,
        "strictness": "严格",
        "focus": "深挖技术栈，层层递进：基础概念 → 底层原理 → 极端场景 → 系统设计。每个回答必须继续深挖，直到候选人触及知识边界。",
        "evaluate_guide": (
            "评估标准（强制深挖）：\n"
            "- 回答正确且深入 → follow_up 继续深挖下一层\n"
            "- 回答正确但不够深 → follow_up 追问'为什么''还有什么方案'\n"
            "- 回答有误 → follow_up 指出并看候选人如何修正\n"
            "- 连续两次触及知识边界 → ask_question 换技术主题\n"
            "- 所有主题深挖完毕 → stage_complete\n"
            "追问层级示例：概念 → 原理 → '量级扩大100倍怎么处理' → '如果换一个完全不同的场景呢'"
        ),
        "question_guide": (
            "出题要求：\n"
            "- 从简历最强技能出发，出一道可以层层深挖的题\n"
            "- 第1层：基础概念或场景设计\n"
            "- 不要一次性把问题说全，留空间让追问逐步深入"
        ),
    },
    "终面": {
        "max_questions": 2,
        "max_follow_ups": 2,
        "strictness": "中等",
        "focus": "综合评估：技术视野、产品思维、行业洞察、成长潜力。出开放性综合题，看思维广度和深度。",
        "evaluate_guide": (
            "评估标准：\n"
            "- 回答展现系统性思维 → ask_question 或 stage_complete\n"
            "- 回答有亮点但不够系统 → follow_up 追问\n"
            "- 回答空洞 → stage_complete\n"
            "- 1-2个综合题后 → stage_complete"
        ),
        "question_guide": (
            "出题要求：\n"
            "- 开放性综合题：'如果让你设计XX系统''你如何看待XX趋势'\n"
            "- 结合简历中的项目经验\n"
            "- 侧重思维广度和深度，而不是具体技术细节"
        ),
    },
}


class InterviewerAgent(BaseAgent):
    """Stage-aware interviewer that generates resume-driven questions."""

    def __init__(self):
        super().__init__()
        self._stage = "初筛"
        self._cfg = STAGE_CONFIG["初筛"]

    @property
    def system_prompt(self) -> str:
        cfg = self._cfg
        return (
            "你是一个专业的AI面试官，正在为一家科技公司面试求职者。\n\n"
            f"当前阶段：{self._stage}\n"
            f"阶段重点：{cfg['focus']}\n"
            f"严格程度：{cfg['strictness']}\n"
            f"最多追问轮数：{cfg['max_follow_ups']}\n\n"
            "你的职责：\n"
            "1. 根据候选人简历中的技能和项目经验，提出针对性问题\n"
            "2. 评估回答质量，决定追问/下一题/阶段结束\n"
            "3. 保持专业、友好但不失严谨的语气\n\n"
            "核心规则：\n"
            "- 问题必须基于候选人简历中的实际技能和经验\n"
            "- 不要在问题中包含答案提示\n"
            "- 根据难度级别调整问题深度\n"
            "- 不要虚构候选人没有提到的技能、项目或错误\n"
            "- 如果候选人分享的内容涉及违法活动、人身攻击、歧视性言论或与面试无关"
            "的敏感主题，请礼貌拒绝并引导回到面试话题\n"
            "- 严格按照以下 JSON 格式返回：\n"
            "{\n"
            '  "action": "ask_question" | "follow_up" | "stage_complete",\n'
            '  "message": "对候选人说的话（面试官语气）",\n'
            '  "question_text": "下一个问题（action=ask_question 时必填）",\n'
            '  "skill_tags": ["题目涉及的技术栈/技能名"],\n'
            '  "follow_up_reason": "追问原因（action=follow_up 时填写）",\n'
            '  "stage_summary": "阶段简短总结（action=stage_complete 时填写）",\n'
            '  "question_count_in_stage": 当前阶段已问问题数\n'
            "}\n"
        )

    # ── Public API ──

    async def start_stage(
        self,
        stage: str,
        position: str,
        difficulty: str,
        top_skills: list[str] | None = None,
        projects: list[dict] | None = None,
        examples: list[dict] | None = None,
        jd_analysis: dict[str, Any] | None = None,
        kb_documents: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Generate the first question for a new stage, driven by resume content.

        Args:
            examples: Few-shot examples from question bank for reference style/quality.
            jd_analysis: JD analysis result with skills/requirements for targeted questions.
            kb_documents: Retrieved chunks from knowledge base documents.
        """
        self._stage = stage
        self._cfg = STAGE_CONFIG.get(stage, STAGE_CONFIG["初筛"])
        cfg = self._cfg

        skill_str = ", ".join(top_skills) if top_skills else "未知技能"
        project_str = ""
        if projects:
            project_names = [p.get("name", p.get("description", "")) for p in projects[:3]]
            project_str = f"\n项目经验：{' ; '.join(project_names)}"

        # Build few-shot reference section from question bank examples
        examples_str = ""
        if examples:
            examples_str = "\n\n以下是一些高质量面试题示例，请参考它们的深度、风格和评分维度，但根据候选人实际技能来出题：\n"
            for i, ex in enumerate(examples, 1):
                examples_str += (
                    f"\n示例{i}（{ex.get('difficulty', '')}/{', '.join(ex.get('skill_tags', []))}）:\n"
                    f"  题目: {ex['question_text']}\n"
                    f"  评分维度: {', '.join(ex.get('dimensions', []))}\n"
                )
                if ex.get("follow_up_hints"):
                    examples_str += f"  追问方向: {'; '.join(ex['follow_up_hints'][:2])}\n"

        # Knowledge base — reference docs uploaded for this position
        kb_str = ""
        if kb_documents:
            kb_str = "\n\n【知识库参考文档】\n"
            for i, doc in enumerate(kb_documents[:3], 1):
                kb_str += f"\n参考{i} (score={doc['score']:.2f}): {doc['text'][:500]}\n"
            kb_str += "出题时可以引用知识库中的概念、技术标准或方法论。\n"

        # JD context — prioritize company requirements over resume self-reported skills
        jd_str = ""
        if jd_analysis:
            jd_skills = jd_analysis.get("skills", [])
            jd_reqs = jd_analysis.get("requirements", [])
            if jd_skills or jd_reqs:
                jd_str = "\n\n【招聘JD要求 — 出题优先级最高】\n"
                if jd_skills:
                    jd_str += f"必须考察的技术栈：{', '.join(jd_skills)}\n"
                if jd_reqs:
                    jd_str += f"岗位职责要求：{'；'.join(jd_reqs)}\n"
                jd_str += (
                    "请优先围绕JD要求的技术栈和职责出题。候选人简历技能作为辅助参考。\n"
                    "如果候选人表示不了解JD中要求的某项技术，不要追问第二次，直接跳过换其他方向。"
                )

        messages = [{
            "role": "user",
            "content": (
                f"面试进入到【{stage}】阶段。\n"
                f"岗位：{position}\n"
                f"难度：{difficulty}\n"
                f"候选人核心技能：{skill_str}{project_str}"
                f"{jd_str}"
                f"{kb_str}"
                f"{examples_str}\n\n"
                f"{cfg['question_guide']}\n\n"
                f"请以面试官身份开始【{stage}】阶段，action 应为 ask_question，question_count_in_stage 为 1。"
            ),
        }]
        result = await self.llm_call_json(messages=messages)
        logger.info(
            f"阶段开始: stage={stage}, position={position}, "
            f"skills={skill_str}, examples={len(examples) if examples else 0}, "
            f"action={result.get('action')}"
        )
        return result

    async def evaluate_answer(
        self,
        stage: str,
        position: str,
        difficulty: str,
        question_text: str,
        user_answer: str,
        question_count: int,
        max_questions: int | None = None,
        follow_up_count: int = 0,
        jd_analysis: dict[str, Any] | None = None,
        kb_documents: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Evaluate answer with stage-specific strictness and follow-up strategy."""
        self._stage = stage
        self._cfg = STAGE_CONFIG.get(stage, STAGE_CONFIG["初筛"])
        cfg = self._cfg

        if max_questions is None:
            max_questions = cfg["max_questions"]

        # Add hard limit warning when approaching max_follow_ups
        limit_warning = ""
        remaining = cfg["max_follow_ups"] - follow_up_count
        if remaining <= 1:
            limit_warning = (
                f"\n⚠️ 硬性限制：当前题目已追问 {follow_up_count}/{cfg['max_follow_ups']} 轮，"
                f"只剩 {remaining} 轮追问额度。如果回答不够深入，请直接 ask_question 换题或 stage_complete 结束，不要继续追问。\n"
            )

        # Knowledge base context for evaluation
        kb_str = ""
        if kb_documents:
            kb_str = "\n\n【知识库参考】\n"
            for i, doc in enumerate(kb_documents[:3], 1):
                kb_str += f"{i}. {doc['text'][:400]}\n"
            kb_str += "评估时可对照知识库内容判断候选人回答的准确性和深度。\n"

        # JD context for evaluation
        jd_str = ""
        if jd_analysis:
            jd_skills = jd_analysis.get("skills", [])
            if jd_skills:
                jd_str = (
                    f"\n招聘JD要求技术栈：{', '.join(jd_skills)}\n"
                    "如果候选人表示不了解JD中的某项技术，不要追问，直接 skip 换方向。"
                )

        messages = [{
            "role": "user",
            "content": (
                f"当前阶段：{stage}（严格度：{cfg['strictness']}）\n"
                f"岗位：{position}\n"
                f"难度：{difficulty}\n"
                f"当前问题：{question_text}\n"
                f"候选人回答：{sanitize_user_input(user_answer)}\n"
                f"已问问题数：{question_count}/{max_questions}\n"
                f"当前问题已追问：{follow_up_count}/{cfg['max_follow_ups']} 轮{limit_warning}"
                f"{jd_str}"
                f"{kb_str}\n"
                f"{cfg['evaluate_guide']}\n\n"
                f"请评估候选人的回答质量，严格按阶段要求决定下一步。"
            ),
        }]
        result = await self.llm_call_json(messages=messages)
        logger.info(
            f"评估回答: stage={stage}, q_count={question_count}/{max_questions}, "
            f"answer={truncate(user_answer)}, decision={result.get('action')}"
        )
        return result

    async def generate_final_summary(
        self,
        position: str,
        stage_summaries: list[dict[str, Any]],
    ) -> str:
        """Generate a closing statement summarizing the interview."""
        summaries_str = "\n".join(
            f"- {s.get('stage', '未知')}: {s.get('summary', '无')}"
            for s in stage_summaries
        )
        messages = [{
            "role": "user",
            "content": (
                f"岗位：{position}\n"
                f"各阶段总结：\n{summaries_str}\n\n"
                f"面试即将结束，请以面试官身份对候选人说一段结束语（50-100字），"
                f"感谢参与并告知下一步（报告生成中）。"
            ),
        }]
        result = await self.llm_call(messages=messages)
        logger.info(f"结束语生成: position={position}, len={len(result)}")
        return result
