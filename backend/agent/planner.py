from typing import List, Dict, Union
import json
from loguru import logger

from backend.llm.client import ChunkForLLM


class PlanGenerationError(Exception):
    """计划生成失败（JSON 解析 / LLM 返回异常）。"""
    def __init__(self, message: str, original: Exception | None = None) -> None:
        super().__init__(message)
        self.original = original


class StudyPlanner:
    """Generates study plans using LLM."""

    def __init__(self, llm):
        self.llm = llm

    def generate_plan_json(
        self,
        days: int,
        hours: int,
        context_chunks: List[Union[Dict, ChunkForLLM]],
        completed_chapters: List[str] | None = None,
    ) -> List[Dict]:
        """
        Generate a study plan and return it as a list of dictionaries.
        Format: [{"day": 1, "task": "Chapter 1: Introduction"}, ...]

        Raises:
            PlanGenerationError: LLM 返回无法解析的 JSON 或调用失败。
        """
        completed_str = "\n".join(completed_chapters) if completed_chapters else "None"

        prompt = f"""
        你是一位资深考研规划师。请根据以下参考资料，为我制定一个 {days} 天的学习计划，每天学习 {hours} 小时。
        
        【硬性约束】
        1. 只能基于提供的参考资料生成计划。
        2. 跳过我已经掌握的内容：{completed_str}。
        3. 必须输出为纯 JSON 格式（List of Objects），不要任何其他 Markdown 文本！
        4. 格式示例：[ {{"day": 1, "task": "第一章 绪论 - 数据结构概念"}}, {{"day": 2, "task": "第二章 线性表 - 顺序表"}} ]
        """

        # ★ 修复 #1：将 dict 统一转换为 ChunkForLLM，避免 LLM 内部 .course/.filename 属性访问崩溃
        llm_chunks = self._normalize_chunks(context_chunks)

        try:
            logger.info("Calling LLM for plan generation...")
            response = self.llm.generate_with_citation(query=prompt, chunks=llm_chunks, timeout=60)

            # Clean up potential markdown formatting around the JSON
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            plan_data = json.loads(cleaned.strip())

        except json.JSONDecodeError as e:
            logger.error("计划生成 JSON 解析失败: {} — raw response: {}", e, response[:200])
            raise PlanGenerationError(
                "AI 返回的计划格式异常，请调整参数后重新生成", original=e
            ) from e

        except PlanGenerationError:
            raise

        except Exception as e:
            logger.opt(exception=True).error("计划生成失败: {}", e)
            raise PlanGenerationError(
                "计划生成失败，请检查网络连接或稍后重试", original=e
            ) from e

        # ★ 修复 #6：不再静默降级为假计划，而是抛出明确异常让调用方处理
        if not isinstance(plan_data, list) or len(plan_data) == 0:
            logger.error("LLM 返回了非预期的计划结构: {}", type(plan_data))
            raise PlanGenerationError("AI 返回的计划为空，请重试")

        return plan_data

    # ── 内部 ────────────────────────────────────────────────

    @staticmethod
    def _normalize_chunks(chunks: List[Union[Dict, ChunkForLLM]]) -> List[ChunkForLLM]:
        """将 dict 或 ChunkForLLM 统一转换为 ChunkForLLM 列表。"""
        result: List[ChunkForLLM] = []
        for c in chunks:
            if isinstance(c, ChunkForLLM):
                result.append(c)
            elif isinstance(c, dict):
                result.append(ChunkForLLM(
                    content=c.get("content", ""),
                    filename=c.get("filename", ""),
                    course=c.get("course", ""),
                    score=c.get("score", 0.0),
                ))
            else:
                logger.warning("跳过未知类型的 chunk: {}", type(c))
        return result
