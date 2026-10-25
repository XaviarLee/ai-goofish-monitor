"""
AI 分析服务
封装 AI 分析相关的业务逻辑
"""
from typing import Dict, List, Optional
from src.infrastructure.external.ai_client import AIClient
from src.services.ai_analysis_schema import (
    normalize_ai_analysis_result,
    validate_ai_analysis_result,
)


class AIAnalysisService:
    """AI 分析服务"""

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def analyze_product(
        self,
        product_data: Dict,
        image_paths: List[str],
        prompt_text: str
    ) -> Optional[Dict]:
        """
        分析商品

        Args:
            product_data: 商品数据
            image_paths: 图片路径列表
            prompt_text: 分析提示词

        Returns:
            分析结果
        """
        if not self.ai_client.is_available():
            print("AI 客户端不可用，跳过分析")
            return None

        try:
            result = await self.ai_client.analyze(product_data, image_paths, prompt_text)
            result = normalize_ai_analysis_result(result)

            if result and self._validate_result(result):
                return result
            else:
                print("AI 分析结果验证失败")
                return None
        except Exception as e:
            print(f"AI 分析服务出错: {e}")
            return None

    def _validate_result(self, result: Dict) -> bool:
        """验证 AI 分析结果的格式"""
        if validate_ai_analysis_result(result):
            return True
        print("AI 响应缺少必需字段或字段类型不正确")
        return False
