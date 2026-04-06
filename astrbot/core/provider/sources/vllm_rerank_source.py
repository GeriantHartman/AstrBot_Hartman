import aiohttp

from astrbot import logger

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "vllm_rerank",
    "VLLM Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class VLLMRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.auth_key = provider_config.get("rerank_api_key", "")
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get("rerank_model", "BAAI/bge-reranker-base")

        h = {}
        if self.auth_key:
            h["Authorization"] = f"Bearer {self.auth_key}"
        self.client = aiohttp.ClientSession(
            headers=h,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        url = self.base_url
        if not url.endswith("/rerank"):
            if url.endswith("/v1"):
                url = f"{url}/rerank"
            else:
                url = f"{url}/v1/rerank"

        assert self.client is not None
        
        logger.info(f"[VLLM Rerank] 准备发起请求 | URL={url} | model={self.model} | query_length={len(query)} | docs_count={len(documents)} | top_n={top_n}")
        logger.debug(f"[VLLM Rerank] 请求载荷 (Payload): {payload}")

        try:
            async with self.client.post(url, json=payload) as response:
                response_text = await response.text()
                logger.info(f"[VLLM Rerank] API响应状态码: {response.status}")
                if response.status >= 400:
                    logger.error(f"[VLLM Rerank] API请求失败，返回内容: {response_text}")
                else:
                    logger.debug(f"[VLLM Rerank] API返回内容: {response_text}")

                response.raise_for_status()

                import json
                response_data = json.loads(response_text)
                results = response_data.get("results", [])

                if not results:
                    logger.warning(
                        f"[VLLM Rerank] API 返回了空的列表数据。原始响应: {response_data}",
                    )

                rerank_results = []
                for idx, result in enumerate(results):
                    try:
                        index = result.get("index")
                        if index is None:
                            if "document_index" in result:
                                index = result["document_index"]
                            elif "document" in result and "index" in result["document"]:
                                index = result["document"]["index"]
                            else:
                                index = idx
                                
                        relevance_score = result.get("relevance_score", 0.0)
                        rerank_results.append(
                            RerankResult(
                                index=int(index),
                                relevance_score=float(relevance_score),
                            )
                        )
                    except Exception as e:
                        logger.warning(f"解析结果 {idx} 时出错: {e}, result={result}")
                        continue
                        
                logger.info(f"[VLLM Rerank] 重排序完成，成功返回 {len(rerank_results)} 个结果")
                return rerank_results

        except aiohttp.ClientError as e:
            logger.error(f"[VLLM Rerank] 网络请求失败: {e}")
            raise

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            await self.client.close()
            self.client = None
