import aiohttp

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
        self.api_suffix = provider_config.get("rerank_api_suffix", "/v1/rerank")
        if self.api_suffix is None:
            self.api_suffix = "/v1/rerank"
        if self.api_suffix and not self.api_suffix.startswith("/"):
            self.api_suffix = "/" + self.api_suffix
        self.timeout = provider_config.get("timeout", 20)
        self.model = provider_config.get("rerank_model", "BAAI/bge-reranker-base")

        h = self.request_headers.copy()
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
        if not documents:
            return []

        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        assert self.client is not None
        # Tolerate an api_base that already contains the version prefix or the
        # full rerank endpoint, so "http://host/v1" + "/v1/rerank" does not 404.
        if self.base_url.endswith("/rerank"):
            rerank_url = self.base_url
        elif self.base_url.endswith("/v1") and self.api_suffix.startswith("/v1/"):
            rerank_url = f"{self.base_url}{self.api_suffix.removeprefix('/v1')}"
        else:
            rerank_url = f"{self.base_url}{self.api_suffix}"
        async with self.client.post(
            rerank_url,
            json=payload,
        ) as response:
            response.raise_for_status()
            response_data = await response.json()
            if not isinstance(response_data, dict):
                raise ValueError("Rerank API response must be a JSON object")

            results = response_data.get("results")
            if not isinstance(results, list) or not results:
                raise ValueError(
                    "Rerank API response must contain a non-empty 'results' list"
                )

            try:
                rerank_results = []
                for result in results:
                    # Some rerank backends (e.g. bge-reranker-v2-m3 behind
                    # vLLM-compatible gateways) report the original document
                    # position as `document_index` or `document.index` instead
                    # of `index`. Falling back to the enumeration order would
                    # silently undo the rerank, so probe the known aliases.
                    index = result.get("index")
                    if index is None:
                        index = result.get("document_index")
                    if index is None and isinstance(result.get("document"), dict):
                        index = result["document"].get("index")
                    if index is None:
                        raise KeyError("index")
                    rerank_results.append(
                        RerankResult(
                            index=int(index),
                            relevance_score=float(result["relevance_score"]),
                        )
                    )
                return rerank_results
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise ValueError("Rerank API returned invalid result data") from exc

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            await self.client.close()
            self.client = None
