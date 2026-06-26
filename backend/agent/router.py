from typing import Literal
from loguru import logger

class IntentRouter:
    def __init__(self, llm):
        """
        传入已经初始化好的 llm 实例进行意图判定
        """
        self.llm = llm
        
    def classify_intent(self, query: str, history: list) -> Literal["rag", "chat", "plan"]:
        """
        判定用户的真实意图，决定流量路由。
        如果非常明显的日常寒暄，可通过规则提前放行。
        否则调用轻量级 LLM 进行分类。
        """
        # 1. 规则前置短路（极速）
        q_strip = query.strip().lower()
        if q_strip in ["你好", "在吗", "哈喽", "hello", "hi", "谢谢", "太棒了", "牛逼", "ok", "好的"]:
            return "chat"
            
        if "计划" in q_strip and ("生成" in q_strip or "帮我" in q_strip or "制定" in q_strip or "怎么复习" in q_strip):
            return "plan"
            
        # 2. 调用大模型进行智能分类
        prompt = f"""作为一个智能教育系统的意图路由器，请仔细判断用户的最新一句话属于哪种意图。
只能从以下三个词中输出一个，绝对不要输出任何其他字符：

1. rag: 用户在提问专业知识、名词解释、代码原理、技术细节等，必须查阅知识库。
2. plan: 用户在要求系统为其制定学习计划、安排复习任务、询问进度等。
3. chat: 用户纯粹在进行日常寒暄、感谢、感叹，或者毫无技术含量的闲聊。

用户问题：{query}

请直接输出你的选择（rag, plan, chat）："""
        
        try:
            logger.info(f"正在进行意图路由分析 (Query: {query})")
            # 同步快速调用
            result = self.llm.generate_with_citation(prompt, [])
            intent = result.strip().lower()
            
            # 清理可能的额外标点符号
            for valid in ["rag", "plan", "chat"]:
                if valid in intent:
                    logger.info(f"路由判定结果: {valid}")
                    return valid
                    
        except Exception as e:
            logger.error(f"路由分发失败，降级为默认 RAG: {e}")
            
        # 默认回退到知识检索
        logger.info("路由判定未命中，回退到默认 rag 路由")
        return "rag"
