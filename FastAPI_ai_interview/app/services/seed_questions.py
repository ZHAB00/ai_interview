"""Seed data: comprehensive interview question bank for IT positions.

Usage: python -m app.main --seed

This bank serves as FEW-SHOT EXAMPLES for the LLM interviewer, not as direct
questions to the candidate. The LLM references these examples for:
  - Question style, depth, and quality standards
  - Scoring dimensions and criteria
  - Follow-up direction

Then generates personalized questions based on the candidate's resume skills.

Each question is tagged with:
  - stage: 初筛 / HR面 / 技术面 / 终面
  - position_tags: applicable job positions
  - skill_tags: relevant tech stacks / skills (NEW — for resume matching)
  - difficulty: 初级 / 中级 / 高级
  - type: technical / behavioral / situational
"""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Question Bank
# ══════════════════════════════════════════════════════════════════════════════

PRESET_QUESTIONS: list[dict] = [

    # ─── 初筛 ───

    # -- C++ --
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["C++", "内存管理"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释C++中栈内存和堆内存的区别，以及什么时候应该使用堆分配？",
        "dimensions": ["技术深度", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确说明栈和堆的内存模型差异", "max_score": 40},
            {"point": "能举例说明各自适用场景", "max_score": 35},
            {"point": "提到RAII或智能指针管理堆内存", "max_score": 25},
        ],
        "sample_answer": "栈内存由编译器自动管理，用于局部变量，速度快但空间有限；堆内存需要手动管理，适合动态大小或需要跨作用域的数据。C++11后推荐用智能指针管理堆内存避免泄漏。",
        "follow_up_hints": ["追问：shared_ptr的引用计数是怎么实现的？有什么性能开销？"],
        "tags": ["C++", "内存管理", "基础概念"],
    },
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["C++", "面向对象"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释C++中虚函数的工作原理，以及多态是如何通过虚函数表(vtable)实现的？",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确描述vtable和vptr的概念", "max_score": 40},
            {"point": "解释多态调用时的运行时绑定过程", "max_score": 35},
            {"point": "提到虚析构函数的必要性", "max_score": 25},
        ],
        "sample_answer": "含有虚函数的类会生成虚函数表(vtable)，每个对象有一个vptr指向它。通过基类指针调用虚函数时，运行时通过vptr→vtable查找实际函数地址，实现多态。",
        "follow_up_hints": ["追问：虚继承对vtable布局有什么影响？", "追问：纯虚函数和抽象类在设计中怎么用？"],
        "tags": ["C++", "多态", "面向对象"],
    },
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["C++", "现代C++"],
        "difficulty": "高级",
        "type": "technical",
        "question_text": "C++11/14/17引入了移动语义、lambda、智能指针等特性。请挑一个你最有心得的新特性，讲讲它的设计动机和你实际项目中的应用。",
        "dimensions": ["技术深度", "技术广度", "工程化思维"],
        "scoring_points": [
            {"point": "清楚阐述特性的设计动机（解决了什么问题）", "max_score": 30},
            {"point": "有实际项目应用场景", "max_score": 35},
            {"point": "了解实现原理或性能影响", "max_score": 35},
        ],
        "sample_answer": "移动语义解决了C++03中大量不必要的深拷贝。比如函数返回大vector时，移动构造直接转移内部指针，避免了O(n)拷贝。配合std::move和右值引用，在容器操作、工厂模式中大幅提升性能。",
        "follow_up_hints": ["追问：std::forward和std::move有什么区别？", "追问：什么情况下移动语义不生效？"],
        "tags": ["C++", "现代C++", "移动语义"],
    },

    # -- Python --
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师", "数据分析师"],
        "skill_tags": ["Python", "基础"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释Python中列表(list)和元组(tuple)的区别，以及各自适合的使用场景。",
        "dimensions": ["技术深度", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确说明可变与不可变的区别", "max_score": 40},
            {"point": "能举例各自适用场景", "max_score": 30},
            {"point": "提到哈希性和性能差异", "max_score": 30},
        ],
        "sample_answer": "list可变，适合需要增删改的动态集合；tuple不可变，可哈希，适合作为dict的key或函数返回多个值。tuple因不可变性能略优，且表达'这些数据不应被修改'的语义。",
        "follow_up_hints": ["追问：tuple真的是完全不可变的吗？里面放一个list呢？"],
        "tags": ["Python", "基础", "数据结构"],
    },
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["Python", "异步", "FastAPI"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释Python中async/await的工作原理，以及asyncio事件循环是如何调度协程的？",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确解释协程和事件循环的概念", "max_score": 35},
            {"point": "能区分并发(concurrency)和并行(parallelism)", "max_score": 30},
            {"point": "提到实际应用场景（如FastAPI异步端点）", "max_score": 35},
        ],
        "sample_answer": "async/await定义协程，asyncio事件循环在单线程中调度它们。遇到await时协程挂起，事件循环切换到其他就绪协程。适合IO密集型而非CPU密集型。FastAPI的异步端点自动运行在事件循环中，避免了线程池的开销。",
        "follow_up_hints": ["追问：如果协程中执行了同步阻塞代码会怎样？", "追问：asyncio.gather和asyncio.create_task有什么区别？"],
        "tags": ["Python", "异步", "asyncio"],
    },

    # -- JavaScript / TypeScript --
    {
        "stage": "初筛",
        "position_tags": ["前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["JavaScript", "基础"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释JavaScript中var、let、const的区别，以及它们各自的作用域规则。",
        "dimensions": ["技术深度", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确说明三者的作用域差异（函数/块/全局）", "max_score": 40},
            {"point": "理解变量提升(hoisting)现象", "max_score": 30},
            {"point": "能给出最佳实践建议", "max_score": 30},
        ],
        "sample_answer": "var有函数作用域和变量提升，容易造成意外；let和const有块级作用域和暂时性死区。const声明常量但对象属性仍可修改。现代开发中默认用const，需要重新赋值时用let，避免var。",
        "follow_up_hints": ["追问：暂时性死区(TDZ)是什么？会导致什么错误？"],
        "tags": ["JavaScript", "基础", "变量"],
    },
    {
        "stage": "初筛",
        "position_tags": ["前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["JavaScript", "异步", "Promise"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释JavaScript中Promise的工作原理，以及async/await与Promise的关系。",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确解释Promise的三种状态和链式调用", "max_score": 30},
            {"point": "理解微任务(microtask)执行顺序", "max_score": 30},
            {"point": "能说清async/await是Promise的语法糖", "max_score": 20},
            {"point": "知道Promise.all/race/allSettled的用法", "max_score": 20},
        ],
        "sample_answer": "Promise代表异步操作的最终结果，有pending/fulfilled/rejected三种状态。then/catch返回新Promise形成链。async函数返回Promise，await暂停执行直到Promise完成。Promise回调在微任务队列中执行，优先于setTimeout。",
        "follow_up_hints": ["追问：Promise.all和Promise.allSettled的差别是什么？", "追问：如何实现一个带超时的Promise？"],
        "tags": ["JavaScript", "异步", "Promise"],
    },

    # -- Java --
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["Java", "基础"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释Java中==和equals的区别，以及为什么重写equals时通常也要重写hashCode？",
        "dimensions": ["技术深度", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确说明==比较引用，equals比较内容", "max_score": 35},
            {"point": "理解hashCode在HashMap等集合中的作用", "max_score": 35},
            {"point": "能举例说明不重写hashCode的bug", "max_score": 30},
        ],
        "sample_answer": "==比较对象引用（内存地址），equals默认也是比较引用但可被重写为比较内容。hashCode用于HashMap的桶定位，如果两个对象equals为true但hashCode不同，HashMap中会找不到。所以必须保持一致。",
        "follow_up_hints": ["追问：HashMap的底层实现是怎样的？JDK8做了什么优化？"],
        "tags": ["Java", "基础", "集合"],
    },

    # -- Go --
    {
        "stage": "初筛",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["Go", "基础"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释Go中goroutine和channel的基本概念，以及它们如何实现并发通信。",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确解释goroutine是轻量级协程", "max_score": 30},
            {"point": "理解channel的阻塞和缓冲机制", "max_score": 35},
            {"point": "能对比goroutine与传统线程的优劣", "max_score": 35},
        ],
        "sample_answer": "goroutine是Go运行时管理的轻量级协程，栈初始只有几KB且可动态增长。channel用于goroutine间通信，遵循'不要通过共享内存来通信，而要通过通信来共享内存'的理念。无缓冲channel同步阻塞，有缓冲channel异步解耦。",
        "follow_up_hints": ["追问：select语句怎么用？多个channel同时就绪时怎么选择？"],
        "tags": ["Go", "并发", "goroutine"],
    },

    # -- AI / Agent --
    {
        "stage": "初筛",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师"],
        "skill_tags": ["LangChain", "Agent", "LLM"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请简要描述你对AI Agent的理解：它由哪些核心模块组成？与传统程序的关键区别是什么？",
        "dimensions": ["技术广度", "沟通逻辑"],
        "scoring_points": [
            {"point": "能说出Agent的核心模块（感知/规划/执行/记忆/工具调用）", "max_score": 40},
            {"point": "清晰阐述与传统程序的核心差异（自主性vs确定性）", "max_score": 35},
            {"point": "能举一个简单的Agent应用场景", "max_score": 25},
        ],
        "sample_answer": "AI Agent是能感知环境、自主规划并执行动作的智能系统。核心模块包括：感知(理解输入)、规划(任务分解)、执行(工具调用)、记忆(上下文管理)。与传统程序的核心区别在于自主性和适应性，传统程序按固定逻辑执行，Agent能根据环境动态调整策略。",
        "follow_up_hints": ["追问：在你看来，'记忆'模块是Agent中最难实现的部分吗？为什么？"],
        "tags": ["AI", "Agent", "基础概念"],
    },
    {
        "stage": "初筛",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师"],
        "skill_tags": ["LangChain", "LLM", "Agent"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请简单描述一下你对大语言模型（LLM）的理解，以及LLM在Agent中扮演什么角色？",
        "dimensions": ["技术广度", "沟通逻辑"],
        "scoring_points": [
            {"point": "能说清楚LLM的基本原理", "max_score": 30},
            {"point": "理解LLM在Agent中的角色（决策大脑）", "max_score": 40},
            {"point": "能举例说明", "max_score": 30},
        ],
        "sample_answer": "LLM是Agent的大脑，负责理解任务、规划步骤和生成响应。它通过预训练获得了广泛的知识和推理能力，在Agent中扮演决策核心的角色，决定何时调用工具、如何解读结果、怎样调整策略。",
        "follow_up_hints": ["追问：LLM有哪些局限性？在Agent开发中如何应对？"],
        "tags": ["AI", "LLM", "Agent"],
    },

    # -- 数据分析 --
    {
        "stage": "初筛",
        "position_tags": ["数据分析师", "AI Agent开发工程师"],
        "skill_tags": ["Python", "数据分析", "SQL"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释SQL中INNER JOIN、LEFT JOIN和FULL OUTER JOIN的区别，并举例各自的使用场景。",
        "dimensions": ["技术深度", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确区分三种JOIN的语义", "max_score": 40},
            {"point": "能给出实际业务场景的例子", "max_score": 35},
            {"point": "提到性能考量（如join的顺序）", "max_score": 25},
        ],
        "sample_answer": "INNER JOIN只返回两表匹配的行；LEFT JOIN保留左表全部行，右表无匹配则NULL；FULL OUTER JOIN保留两表全部行。比如LEFT JOIN常用于'查询所有用户及其订单'（保留无订单的用户），INNER JOIN用于'查有订单的用户'。",
        "follow_up_hints": ["追问：如果有三个表要JOIN，怎么优化查询性能？"],
        "tags": ["SQL", "数据分析", "基础"],
    },

    # -- 产品经理 --
    {
        "stage": "初筛",
        "position_tags": ["产品经理"],
        "skill_tags": ["产品思维", "需求分析"],
        "difficulty": "初级",
        "type": "behavioral",
        "question_text": "请分享一个你从0到1推动过的产品功能或项目。你是如何发现需求、设计方案并推动落地的？",
        "dimensions": ["沟通逻辑", "项目经验匹配度"],
        "scoring_points": [
            {"point": "清晰的需求发现过程（用户调研/数据分析/竞品分析）", "max_score": 35},
            {"point": "具体的设计或方案思路", "max_score": 30},
            {"point": "有推动落地的具体行动和结果数据", "max_score": 35},
        ],
        "sample_answer": "我发现用户在使用XX功能时跳出率高，通过用户访谈发现核心痛点是操作步骤太多。我设计了简化流程方案，推动技术团队2周内上线，最终跳出率降低了30%。",
        "follow_up_hints": ["追问：在推动过程中你遇到了什么阻力？怎么解决的？"],
        "tags": ["产品", "需求分析", "初级"],
    },

    # ─── HR面 ───

    {
        "stage": "HR面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师", "数据分析师", "产品经理"],
        "skill_tags": ["通用", "团队协作"],
        "difficulty": "初级",
        "type": "behavioral",
        "question_text": "请描述一次你在团队协作中遇到的技术分歧，你是如何处理的？最后的结论和结果是什么？",
        "dimensions": ["沟通逻辑", "工程化思维"],
        "scoring_points": [
            {"point": "清晰描述了冲突场景和各方立场", "max_score": 25},
            {"point": "展示了积极解决问题的态度和具体行动", "max_score": 40},
            {"point": "有可量化的结果或复盘总结", "max_score": 35},
        ],
        "sample_answer": "在一次项目评审中，团队成员对于选择LangChain还是自研框架产生了分歧。我整理了两种方案的优劣对比表格，包含开发周期、维护成本、灵活性等维度，然后召开技术讨论会让各方充分表达，最终达成共识选择混合方案。",
        "follow_up_hints": ["追问：如果当时无法达成共识，你会怎么做？", "追问：你在这个分歧中扮演了什么角色？"],
        "tags": ["团队协作", "冲突处理", "HR面"],
    },
    {
        "stage": "HR面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师", "数据分析师", "产品经理"],
        "skill_tags": ["通用", "职业规划"],
        "difficulty": "中级",
        "type": "behavioral",
        "question_text": "未来3-5年，你希望自己在技术/职业上达到什么样的高度？你为此做了什么准备？",
        "dimensions": ["沟通逻辑", "项目经验匹配度"],
        "scoring_points": [
            {"point": "职业目标具体、可实现，不是空泛的'成为技术大牛'", "max_score": 35},
            {"point": "有明确的学习和成长路径", "max_score": 35},
            {"point": "目标与应聘岗位的发展方向一致", "max_score": 30},
        ],
        "sample_answer": "我希望3年内成为能够独立负责一个技术领域的技术负责人。为此我正在系统补强分布式系统和架构设计，参与开源项目积累协作经验，同时保持对AI Agent方向的深度关注。5年内希望能推动一个从0到1的技术产品落地。",
        "follow_up_hints": ["追问：你觉得自己目前最大的能力短板是什么？打算怎么补？"],
        "tags": ["职业规划", "自驱力", "HR面"],
    },
    {
        "stage": "HR面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师", "数据分析师", "产品经理"],
        "skill_tags": ["通用", "抗压能力"],
        "difficulty": "中级",
        "type": "situational",
        "question_text": "假设你被分配到一个紧急任务，deadline很紧且你对相关技术栈不完全熟悉。你会如何应对？请说说你的具体步骤。",
        "dimensions": ["沟通逻辑", "工程化思维"],
        "scoring_points": [
            {"point": "制定了合理的学习和开发计划", "max_score": 35},
            {"point": "主动沟通风险和预期，不隐瞒不硬撑", "max_score": 35},
            {"point": "有具体的求助或协作策略", "max_score": 30},
        ],
        "sample_answer": "首先评估技术栈的学习曲线和任务核心需求，判断哪些部分可以快速上手、哪些需要求助。然后和负责人坦诚沟通现状和风险评估，提出分批交付方案（先核心功能再完善）。启动时优先搭建最小可用原型验证技术可行性，过程中保持每日同步进度。",
        "follow_up_hints": ["追问：如果你评估后发现根本无法按期完成，你会怎么沟通？"],
        "tags": ["抗压", "问题解决", "HR面"],
    },
    {
        "stage": "HR面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师", "数据分析师"],
        "skill_tags": ["通用", "ownership"],
        "difficulty": "中级",
        "type": "behavioral",
        "question_text": "请分享一个你主动发现并解决了一个'不是你职责范围内'问题的经历。你为什么要做这件事？结果如何？",
        "dimensions": ["沟通逻辑", "工程化思维", "项目经验匹配度"],
        "scoring_points": [
            {"point": "问题是真实且有价值的，不是刻意编造", "max_score": 30},
            {"point": "展示了ownership和主动性", "max_score": 40},
            {"point": "有具体结果或影响", "max_score": 30},
        ],
        "sample_answer": "我发现团队的CI/CD流程中构建时间过长（15分钟），虽然不是我负责的，但影响了每个人的开发效率。我花了一个周末分析了构建瓶颈，发现主要原因是没有利用缓存和并行构建。我提出了优化方案并自己实现提交了PR，最终构建时间降到4分钟。",
        "follow_up_hints": ["追问：这件事让你学到了什么？"],
        "tags": ["ownership", "主动性", "HR面"],
    },

    # ─── 技术面 ───

    # -- C++ 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["C++", "内存管理", "并发"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释C++中的RAII（资源获取即初始化）原则，以及它在智能指针、锁管理、文件操作中的具体应用。",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "正确阐述RAII的核心思想（资源生命周期绑定对象生命周期）", "max_score": 30},
            {"point": "至少给出2个不同场景的RAII应用实例", "max_score": 35},
            {"point": "能对比不使用RAII时代的常见bug（内存泄漏、死锁）", "max_score": 35},
        ],
        "sample_answer": "RAII将资源的获取和释放绑定到对象的构造和析构上，利用C++的确定性析构保证资源正确释放。智能指针用RAII管理堆内存，std::lock_guard用RAII自动释放锁，std::fstream用RAII自动关闭文件。这种模式从根本上消除了忘记释放资源的bug。",
        "follow_up_hints": ["追问：RAII在多线程环境下有什么需要注意的？", "追问：如果析构函数抛异常会怎样？", "追问：C++20的coroutine对RAII有什么挑战？"],
        "tags": ["C++", "RAII", "资源管理"],
    },
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["C++", "并发", "多线程"],
        "difficulty": "高级",
        "type": "technical",
        "question_text": "请设计一个线程安全的、支持多生产者多消费者的无锁(Lock-Free)队列。说明你选择的数据结构和关键的并发控制策略。",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "给出合理的数据结构设计（如环形缓冲区+CAS操作）", "max_score": 30},
            {"point": "正确使用内存序(memory order)保证正确性", "max_score": 30},
            {"point": "能讨论ABA问题和解决方案", "max_score": 20},
            {"point": "对比锁队列和无锁队列的性能特点和适用场景", "max_score": 20},
        ],
        "sample_answer": "采用环形缓冲区+原子操作实现。使用两个原子head和tail指针，push用CAS递增head后写入，pop用CAS递增tail后读取。需要处理空/满的判断（可以用额外的原子计数器或浪费一个槽位）。内存序用acquire-release保证happens-before关系。ABA问题可以通过带版本号的指针或使用double-width CAS解决。",
        "follow_up_hints": ["追问：如果队列满了，生产者应该怎么处理？", "追问：在x86和ARM上内存序的选择有什么不同？"],
        "tags": ["C++", "并发", "无锁队列"],
    },

    # -- Python 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["Python", "FastAPI", "异步"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请设计一个FastAPI微服务来处理高并发的LLM调用请求。重点说明异步数据库会话管理、请求队列、超时控制和错误重试的设计方案。",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "正确使用异步数据库会话和连接池", "max_score": 25},
            {"point": "设计了合理的限流或排队策略", "max_score": 25},
            {"point": "考虑了超时、重试、熔断等弹性设计", "max_score": 25},
            {"point": "有日志、监控或可观测性设计", "max_score": 25},
        ],
        "sample_answer": "使用async session with context manager管理DB会话，连接池大小根据并发量设定。LLM调用通过asyncio.Semaphore限制并发数，超出则排队等待。超时用asyncio.wait_for设置，重试用指数退避避免雪崩。集成OpenTelemetry做链路追踪，Prometheus收集指标。",
        "follow_up_hints": ["追问：Semaphore队列满了怎么办？直接拒绝还是排队？", "追问：分布式场景下怎么扩展这个方案？"],
        "tags": ["Python", "FastAPI", "异步", "高并发"],
    },
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["Python", "性能优化"],
        "difficulty": "高级",
        "type": "technical",
        "question_text": "你发现一个Python后端服务的API响应时间从50ms恶化到了2s。请描述你的排查思路，以及可能的优化手段。",
        "dimensions": ["技术深度", "工程化思维", "沟通逻辑"],
        "scoring_points": [
            {"point": "排查思路系统化，从请求链路逐层定位", "max_score": 25},
            {"point": "提到了具体的排查工具（profiler、APM、日志）", "max_score": 25},
            {"point": "能给出针对不同层（DB/网络/代码/GC）的优化方案", "max_score": 30},
            {"point": "有性能回归监控的意识", "max_score": 20},
        ],
        "sample_answer": "我会从外到内逐层排查：1) 先看APM确认瓶颈在哪个环节(DB/外部调用/代码)；2) 如果是DB，检查慢查询日志和索引使用；3) 如果是代码，用py-spy或cProfile做profiling定位热点函数；4) 检查是否有不当的同步阻塞调用了异步代码。优化手段包括：添加索引、引入缓存、优化ORM查询（避免N+1）、批量操作替代循环等。",
        "follow_up_hints": ["追问：如果一个第三方API调用偶尔特别慢，怎么处理？", "追问：GC暂停怎么排查和优化？"],
        "tags": ["Python", "性能优化", "排错"],
    },

    # -- JavaScript/TypeScript 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["JavaScript", "闭包", "作用域"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释JavaScript闭包(closure)的原理，并给出至少两个实际开发中的典型应用场景。同时说说闭包可能导致的性能或内存问题。",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "正确解释闭包的形成机制（词法作用域+函数引用环境）", "max_score": 30},
            {"point": "给出至少2个合理的应用场景（如防抖节流、模块模式、回调）", "max_score": 35},
            {"point": "了解闭包可能导致内存泄漏并知道如何避免", "max_score": 35},
        ],
        "sample_answer": "闭包是函数记住并访问其词法作用域的能力，即使函数在词法作用域外执行。应用场景：1)防抖节流函数需要保持timer状态；2)模块模式用IIFE闭包封装私有变量。内存问题：如果闭包持有大对象引用且该闭包长期存在，大对象无法被GC——应在不需要时解除引用。",
        "follow_up_hints": ["追问：let和闭包结合在for循环中有什么经典问题？", "追问：React的useEffect依赖数组和闭包有什么关系？"],
        "tags": ["JavaScript", "闭包", "作用域"],
    },
    {
        "stage": "技术面",
        "position_tags": ["前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["Vue", "响应式", "TypeScript"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释Vue 3的响应式系统原理：reactive/ref是如何追踪依赖和触发更新的？与Vue 2的Object.defineProperty方案有什么本质改进？",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确解释Proxy拦截get/set实现依赖收集和触发", "max_score": 30},
            {"point": "能对比Proxy与Object.defineProperty的关键差异", "max_score": 35},
            {"point": "提到effect、track、trigger这几个核心API", "max_score": 35},
        ],
        "sample_answer": "Vue 3用Proxy拦截对象操作：get时通过track()收集当前active effect作为依赖，set时通过trigger()通知依赖更新。相比Vue 2的defineProperty方案，Proxy可以拦截属性添加/删除、数组索引变更、Map/Set等，不需要递归遍历对象定义getter/setter，性能和功能都有提升。",
        "follow_up_hints": ["追问：为什么reactive不能替换整个对象？", "追问：shallowReactive和reactive有什么区别？"],
        "tags": ["Vue", "响应式", "Proxy"],
    },

    # -- Java 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["Java", "并发", "JVM"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释Java中synchronized关键字和ReentrantLock的区别，并说明各自的适用场景。",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "能列出功能层面的差异（可中断、超时、公平锁等）", "max_score": 35},
            {"point": "了解底层的锁升级过程（偏向锁→轻量锁→重量锁）", "max_score": 35},
            {"point": "能给出选型指导", "max_score": 30},
        ],
        "sample_answer": "synchronized是JVM内置关键字，自动释放锁，JDK6后经过大量优化（锁膨胀、锁消除等）。ReentrantLock提供更多控制：可中断获取锁、超时等待、公平锁、条件变量(Condition)。简单同步用synchronized足够，需要高级特性时用ReentrantLock。两者都是可重入的。",
        "follow_up_hints": ["追问：什么是死锁？如何用jstack排查？", "追问：读写锁(ReadWriteLock)在什么场景下比独占锁更好？"],
        "tags": ["Java", "并发", "锁机制"],
    },

    # -- Go 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["Go", "并发", "内存"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请对比Go的GMP调度模型与传统线程池模型的差异。goroutine的栈空间是如何动态增长的？",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确理解GMP(Goroutine-Machine-Processor)三者关系", "max_score": 30},
            {"point": "能解释Work Stealing和handoff机制", "max_score": 35},
            {"point": "理解goroutine栈的动态增长和收缩", "max_score": 35},
        ],
        "sample_answer": "GMP中G是goroutine，M是OS线程，P是逻辑处理器。P的数量由GOMAXPROCS控制，M可以多于P（阻塞时）。P维护本地G队列，空闲P会从其他P偷G（Work Stealing）。goroutine栈从2KB起，不足时复制到新栈（扩大一倍），GC时也可能收缩栈。这比固定大小的线程栈灵活得多，允许同时运行百万goroutine。",
        "follow_up_hints": ["追问：如果一个goroutine执行了阻塞的系统调用，会发生什么？", "追问：channel的底层是怎么实现的？"],
        "tags": ["Go", "调度器", "并发"],
    },

    # -- 系统设计 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["系统设计", "架构"],
        "difficulty": "高级",
        "type": "technical",
        "question_text": "请设计一个支持100万并发用户的实时消息推送系统。说明整体架构、技术选型、消息可靠性保证和扩展策略。",
        "dimensions": ["技术深度", "技术广度", "工程化思维"],
        "scoring_points": [
            {"point": "架构设计层次清晰（接入层、路由层、存储层）", "max_score": 30},
            {"point": "技术选型有理性依据（WebSocket/长轮询/SSE的取舍）", "max_score": 25},
            {"point": "考虑了消息可靠性（ACK机制、消息持久化、断线重连）", "max_score": 25},
            {"point": "有水平扩展策略（分片、负载均衡）和容量估算", "max_score": 20},
        ],
        "sample_answer": "接入层用WebSocket集群，Nginx做负载均衡(ip_hash维持连接亲和性)。路由层用一致性哈希将用户映射到消息队列的partition(Kafka)。存储层先写消息到Redis用于即时推送和历史缓存，异步落库。ACK机制确保消息不丢，断线时暂存离线消息。容量估算：100W连接×每连接内存约4KB=4GB，单机5W连接需20台接入节点。",
        "follow_up_hints": ["追问：如果需要保证消息的严格有序，架构需要怎么调整？", "追问：跨机房部署时一致性哈希怎么处理？"],
        "tags": ["系统设计", "架构", "高并发"],
    },

    # -- 数据库 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "数据分析师"],
        "skill_tags": ["MySQL", "数据库", "SQL"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释MySQL中InnoDB的MVCC（多版本并发控制）机制是如何实现事务隔离的？READ COMMITTED和REPEATABLE READ在MVCC实现上有什么区别？",
        "dimensions": ["技术深度", "技术广度"],
        "scoring_points": [
            {"point": "正确说明undo log和ReadView的作用", "max_score": 35},
            {"point": "区分RC和RR下ReadView的创建时机差异", "max_score": 35},
            {"point": "能解释幻读和间隙锁", "max_score": 30},
        ],
        "sample_answer": "InnoDB为每行记录维护多个版本（通过undo log串联），每条记录有隐藏列trx_id和roll_pointer。ReadView记录当前活跃事务列表，通过比对trx_id判断可见性。RC在每次SELECT时创建新ReadView（能读到已提交的变更），RR在事务开始时创建ReadView（保证可重复读）。RR通过间隙锁(next-key lock)防止幻读。",
        "follow_up_hints": ["追问：MVCC有什么代价？undo log膨胀怎么办？", "追问：长事务对MVCC有什么影响？"],
        "tags": ["MySQL", "MVCC", "事务"],
    },

    # -- 前端 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["React", "Vue", "性能优化"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "谈谈你对前端性能优化的系统性理解。请从网络层、渲染层、运行时三个维度分别说明优化策略。",
        "dimensions": ["技术广度", "工程化思维"],
        "scoring_points": [
            {"point": "网络层：打包优化、CDN、缓存策略、懒加载", "max_score": 25},
            {"point": "渲染层：关键渲染路径、避免重排、虚拟列表", "max_score": 25},
            {"point": "运行时：内存管理、防抖节流、Web Worker", "max_score": 25},
            {"point": "提到性能监控和Core Web Vitals指标", "max_score": 25},
        ],
        "sample_answer": "网络层：代码分割(动态import)、Tree Shaking、资源压缩、CDN分发、Service Worker缓存。渲染层：避免强制同步布局、使用transform代替position动画、虚拟列表处理长列表、requestAnimationFrame编排动画帧。运行时：清理定时器和事件监听防止内存泄漏、防抖节流控制高频事件、复杂计算移到Web Worker。用Lighthouse和Performance API持续监控LCP/FID/CLS。",
        "follow_up_hints": ["追问：虚拟列表如何处理不定高的列表项？", "追问：微前端架构下如何做性能优化？"],
        "tags": ["前端", "性能优化", "全栈"],
    },

    # -- Git 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师", "数据分析师"],
        "skill_tags": ["Git", "版本控制"],
        "difficulty": "初级",
        "type": "technical",
        "question_text": "请解释Git中merge和rebase的区别，以及各自的使用场景。在团队协作中，你推荐哪种策略？为什么？",
        "dimensions": ["技术深度", "工程化思维", "沟通逻辑"],
        "scoring_points": [
            {"point": "正确解释merge和rebase的底层操作差异", "max_score": 30},
            {"point": "清楚说明各自的优缺点", "max_score": 35},
            {"point": "有团队协作规范的见解", "max_score": 35},
        ],
        "sample_answer": "merge创建一个新的合并提交保留完整历史，rebase将分支提交重放到目标分支顶部形成线性历史。merge适合公共分支（保留上下文），rebase适合个人分支（保持历史整洁）。团队建议：功能分支用rebase保持整洁后merge到主干，公共分支永远不要force push。",
        "follow_up_hints": ["追问：rebase过程中冲突了怎么处理？", "追问：git reflog和git reset有什么区别？"],
        "tags": ["Git", "版本控制", "协作"],
    },

    # -- 网络 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["网络", "HTTP", "TCP"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释从浏览器输入URL到页面加载完成的完整过程中，涉及的网络协议和步骤。",
        "dimensions": ["技术广度", "沟通逻辑"],
        "scoring_points": [
            {"point": "DNS解析过程描述正确", "max_score": 20},
            {"point": "TCP三次握手和TLS握手描述清楚", "max_score": 25},
            {"point": "HTTP请求/响应流程正确", "max_score": 20},
            {"point": "能提到CDN、缓存、负载均衡等中间环节", "max_score": 20},
            {"point": "浏览器渲染流程概览", "max_score": 15},
        ],
        "sample_answer": "1)DNS解析域名→IP（递归查询，可能走CDN智能解析）；2)TCP三次握手建立连接；3)如果HTTPS，TLS握手（证书验证、密钥协商）；4)发送HTTP请求；5)服务端经负载均衡→后端处理→查询DB/缓存→返回响应；6)浏览器接收HTML→解析DOM→构建CSSOM→执行JS→渲染页面。HTTP2可多路复用，HTTP3用QUIC(UDP)进一步减少延迟。",
        "follow_up_hints": ["追问：TLS 1.3相比1.2有什么改进？", "追问：QUIC协议相比TCP有什么优势？"],
        "tags": ["网络", "HTTP", "TCP"],
    },

    # -- Docker / K8s 技术面 --
    {
        "stage": "技术面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["Docker", "Kubernetes", "DevOps"],
        "difficulty": "中级",
        "type": "technical",
        "question_text": "请解释Docker镜像的分层结构(Layer)是如何工作的？为什么分层设计能加速构建和部署？",
        "dimensions": ["技术深度", "工程化思维"],
        "scoring_points": [
            {"point": "正确说明Union FS和写时复制(CoW)的原理", "max_score": 35},
            {"point": "理解层缓存对构建速度的影响", "max_score": 30},
            {"point": "能给出Dockerfile最佳实践（减少层数、合理排序、多阶段构建）", "max_score": 35},
        ],
        "sample_answer": "Docker镜像由多个只读层叠加组成，每层是Dockerfile中一条指令的结果。使用UnionFS将各层合并为一个文件系统视图。分层设计的好处：未变更的层可以跨镜像共享和缓存，构建时只重建变更的层。最佳实践：把不容易变的层（系统依赖）放在前面，经常变的层（代码）放在后面；用多阶段构建减小最终镜像体积。",
        "follow_up_hints": ["追问：多阶段构建中怎么把第一阶段的产物复制到第二阶段？", "追问：Docker和containerd/runc是什么关系？"],
        "tags": ["Docker", "容器", "DevOps"],
    },

    # ─── 终面 ───

    {
        "stage": "终面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "全栈开发工程师"],
        "skill_tags": ["系统设计", "技术管理"],
        "difficulty": "高级",
        "type": "situational",
        "question_text": "假设你作为技术负责人，需要从零搭建一个AI Agent开发平台。请描述你的技术选型、团队组建和分阶段推进计划。",
        "dimensions": ["技术广度", "工程化思维", "沟通逻辑", "项目经验匹配度"],
        "scoring_points": [
            {"point": "技术选型有理有据，考虑了团队能力、生态、性能等维度", "max_score": 25},
            {"point": "项目规划分阶段、可落地（MVP→优化→规模化）", "max_score": 25},
            {"point": "考虑了团队组建和成长路径", "max_score": 25},
            {"point": "提到了风险管理和应急预案", "max_score": 25},
        ],
        "sample_answer": "技术选型：FastAPI(高性能异步)+LangChain(Agent生态)+PostgreSQL+Redis+FAISS(向量检索)。第一阶段MVP：实现核心Agent编排、3个基础Tool、简单的前端演示，2人/6周。第二阶段：扩展Tool生态、记忆系统、多Agent协作，3人/8周。第三阶段：平台化——可视化编排、用户管理、监控告警，4人/10周。风险：LLM API稳定性（备选多供应商）、人才招聘时间（提前启动）。",
        "follow_up_hints": ["追问：在MVP阶段和大规模阶段，技术决策会有哪些不同？"],
        "tags": ["技术管理", "平台搭建", "终面"],
    },
    {
        "stage": "终面",
        "position_tags": ["AI Agent开发工程师", "后端开发工程师", "前端开发工程师", "全栈开发工程师"],
        "skill_tags": ["技术趋势", "行业洞察"],
        "difficulty": "高级",
        "type": "behavioral",
        "question_text": "你如何看待AI Agent技术在未来3-5年的演变？开发者的核心竞争力会如何变化？",
        "dimensions": ["技术广度", "沟通逻辑"],
        "scoring_points": [
            {"point": "对技术趋势有独立见解，不是人云亦云", "max_score": 35},
            {"point": "对个人能力发展有清晰规划", "max_score": 35},
            {"point": "能结合实际应用场景讨论", "max_score": 30},
        ],
        "sample_answer": "未来Agent会更像'数字同事'而不仅是'工具'：多模态感知、长期记忆、跨系统协作会成为标配。Agent的可靠性（幻觉控制、行为可预测）会成为核心挑战。开发者核心竞争力会从'写代码'转向'设计Agent行为'——理解业务场景、定义评估标准、设计安全护栏。但扎实的工程基础（分布式系统、性能优化）仍是底层要求。",
        "follow_up_hints": ["追问：你认为开发者应该如何准备迎接这些变化？"],
        "tags": ["技术趋势", "终面", "行业洞察"],
    },
    {
        "stage": "终面",
        "position_tags": ["后端开发工程师", "全栈开发工程师", "AI Agent开发工程师"],
        "skill_tags": ["系统设计", "分布式"],
        "difficulty": "高级",
        "type": "technical",
        "question_text": "请描述你在之前项目中遇到的最复杂的技术挑战。不需要是最大的项目，但需要是技术上最棘手的。你是如何分析、尝试、最终解决或权衡的？",
        "dimensions": ["技术深度", "沟通逻辑", "工程化思维"],
        "scoring_points": [
            {"point": "挑战有真正的技术含量（不是资源或沟通问题）", "max_score": 25},
            {"point": "展示了系统化的分析过程（假设→验证→方案→结论）", "max_score": 35},
            {"point": "有明确的解决结果或权衡总结", "max_score": 25},
            {"point": "能从中学到可迁移的经验或原则", "max_score": 15},
        ],
        "sample_answer": "（候选人自由回答）",
        "follow_up_hints": ["追问：回头看，你会有不同的选择吗？", "追问：你从这个经历中学到的最重要的原则是什么？"],
        "tags": ["技术挑战", "问题解决", "终面"],
    },
    {
        "stage": "终面",
        "position_tags": ["产品经理", "AI Agent开发工程师"],
        "skill_tags": ["产品思维", "需求分析"],
        "difficulty": "中级",
        "type": "situational",
        "question_text": "如果我们公司要把当前的AI面试产品拓展到海外市场，你认为产品需要做哪些关键调整？请从用户需求、技术架构、合规性三个角度分析。",
        "dimensions": ["技术广度", "工程化思维", "沟通逻辑"],
        "scoring_points": [
            {"point": "用户需求角度有跨文化思考（面试风格、语言、交互习惯差异）", "max_score": 35},
            {"point": "技术架构角度考虑了国际化、部署、延迟等", "max_score": 35},
            {"point": "提到了数据合规（GDPR等）和本地化挑战", "max_score": 30},
        ],
        "sample_answer": "用户需求：面试风格因文化而异（如欧美重直接交流、东亚重礼貌），AI面试官需适配语气和节奏；支持多语言不仅是翻译，还要理解不同语言的表达习惯。技术架构：海外部署节点降低延迟，数据不出境的合规架构（如欧盟用欧洲节点），多币种支付接入。合规：遵循GDPR（数据最小化、用户删除权）、各国AI监管法规差异。",
        "follow_up_hints": ["追问：多语言面试中如何保证评分公平性？"],
        "tags": ["产品思维", "国际化", "终面"],
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# Seed function
# ══════════════════════════════════════════════════════════════════════════════


async def seed_questions(db: AsyncSession) -> int:
    """Seed the question bank. Returns count of newly seeded questions."""
    seeded = 0
    for q_data in PRESET_QUESTIONS:
        result = await db.execute(
            select(func.count()).select_from(Question).where(
                Question.question_text == q_data["question_text"],
                Question.is_deleted == 0,
            )
        )
        if result.scalar() > 0:
            continue

        question = Question(**q_data)
        db.add(question)
        seeded += 1

    if seeded > 0:
        await db.commit()
        logger.info(f"题库预置完成: 新增 {seeded} 道题目")
    else:
        logger.info("题库已包含预置题目，无需重复导入")

    return seeded
