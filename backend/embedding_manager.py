import os
import logging
from typing import List, Optional, Dict, Any
import numpy as np
import json

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    try:
        load_dotenv(override=False)
    except Exception:
        return


_load_dotenv()


class EmbeddingService:
    """嵌入服务 - 负责生成和管理文本向量嵌入"""

    _REMOTE_ALLOWED_DIMS = {
        64,
        128,
        256,
        512,
        768,
        1024,
        1536,
        2048,
        3072,
    }

    _REMOTE_PROVIDERS = {
        "remote",
        "dashscope",
        "qwen",
        "bailian",
        "baidu",
        "openai",
        "azure",
        "bytedance",
        "doubao",
        "deepseek",
        "vllm",
        "lmstudio",
        "zhipu",
    }

    def __init__(self, model_name: str = None):
        provider_env = os.getenv("EMBEDDING_PROVIDER")
        if not provider_env:
            if (os.getenv("EMBEDDING_API_KEY") or "").strip() or (
                os.getenv("DASHSCOPE_API_KEY") or ""
            ).strip():
                provider_env = "dashscope"
            elif (os.getenv("OPENAI_API_KEY") or "").strip():
                provider_env = "openai"
            else:
                provider_env = "local"
        self.provider = provider_env.strip().lower()
        model_env = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.model_name = model_name or model_env
        self.model = None
        self.dimension = None
        self._remote_client = None
        self._remote_base_url = None
        self._remote_api_key = None
        self._remote_dimensions = None
        self._load_model()

    def _adapt_embedding_dimension(
        self, vec: List[float], target_dim: int
    ) -> List[float]:
        target = int(target_dim or 0)
        if target <= 0:
            return []
        if len(vec) == target:
            return vec
        if len(vec) > target:
            return vec[:target]
        return vec + [0.0] * (target - len(vec))

    def _load_model(self):
        """加载嵌入模型"""
        provider = (self.provider or "local").strip().lower()
        if provider in self._REMOTE_PROVIDERS:
            try:
                self._load_remote_model()
                return
            except Exception as e:
                logger.error(f"加载远程嵌入模型失败: {e}")
                self.provider = "local"
        try:
            logger.info(f"正在加载嵌入模型: {self.model_name}")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)

            # 获取模型维度
            test_embedding = self.model.encode(["test"])
            self.dimension = len(test_embedding[0])

            logger.info(f"嵌入模型加载成功，维度: {self.dimension}")
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e}")
            # 使用备用方案
            self._load_fallback_model()

    def _load_fallback_model(self):
        """加载备用模型"""
        try:
            logger.info("尝试加载备用嵌入模型")
            self.model_name = 'paraphrase-MiniLM-L6-v2'
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)

            test_embedding = self.model.encode(["test"])
            self.dimension = len(test_embedding[0])

            logger.info(f"备用嵌入模型加载成功: {self.model_name}")
        except Exception as e:
            logger.error(f"备用嵌入模型加载失败: {e}")
            self.model = None
            self.dimension = 384  # 默认维度

    def _load_remote_model(self):
        provider = (self.provider or "").strip().lower()
        base_url = (os.getenv("EMBEDDING_API_BASE") or "").strip()
        api_key = (os.getenv("EMBEDDING_API_KEY") or "").strip()

        if not base_url and (os.getenv("DASHSCOPE_API_BASE") or "").strip():
            base_url = (os.getenv("DASHSCOPE_API_BASE") or "").strip()
        if not api_key and (os.getenv("DASHSCOPE_API_KEY") or "").strip():
            api_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()

        if not base_url:
            base_url = (
                (os.getenv("OPENAI_BASE_URL") or "").strip()
                or (os.getenv("OPENAI_API_BASE") or "").strip()
            )
        if not api_key:
            api_key = (os.getenv("OPENAI_API_KEY") or "").strip()

        if not base_url:
            if provider == "openai":
                base_url = "https://api.openai.com/v1"
            else:
                base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if not api_key:
            raise RuntimeError(
                "缺少EMBEDDING_API_KEY/DASHSCOPE_API_KEY/OPENAI_API_KEY"
            )

        desired_dim = (
            os.getenv("EMBEDDING_DIM") or os.getenv("RAG_VECTOR_DIM") or "384"
        )
        try:
            desired_dim_int = int(desired_dim)
        except Exception:
            desired_dim_int = 384

        if provider in {"dashscope", "qwen"} and not self.model_name:
            self.model_name = "text-embedding-v4"
        if provider in {"dashscope", "qwen"} and self.model_name in {
            "all-MiniLM-L6-v2",
            "paraphrase-MiniLM-L6-v2",
        }:
            self.model_name = "text-embedding-v4"

        from openai import OpenAI

        self._remote_base_url = base_url
        self._remote_api_key = api_key
        if desired_dim_int in self._REMOTE_ALLOWED_DIMS:
            self._remote_dimensions = desired_dim_int
        else:
            self._remote_dimensions = None
        self._remote_client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = None
        self.dimension = desired_dim_int
        logger.info(
            f"远程嵌入模型已就绪: provider={provider or 'remote'} "
            f"model={self.model_name} dim={self.dimension}"
        )

    def _remote_embeddings(
        self, texts: List[str]
    ) -> List[Optional[List[float]]]:
        if not texts:
            return []
        if self._remote_client is None:
            raise RuntimeError("远程嵌入客户端未初始化")

        processed = [self._preprocess_text(t) for t in texts]
        valid_indices = [i for i, t in enumerate(processed) if t.strip()]
        valid_texts = [processed[i] for i in valid_indices]
        results: List[Optional[List[float]]] = [None] * len(texts)
        if not valid_texts:
            return results

        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "input": valid_texts,
        }
        if self._remote_dimensions is not None and self.model_name in {
            "text-embedding-v3",
            "text-embedding-v4",
        }:
            kwargs["dimensions"] = int(self._remote_dimensions)

        resp = self._remote_client.embeddings.create(**kwargs)
        data = getattr(resp, "data", None) or []
        if len(data) != len(valid_texts):
            raise RuntimeError("远程嵌入返回数量不匹配")

        for out_idx, emb_obj in zip(valid_indices, data):
            emb = getattr(emb_obj, "embedding", None)
            if emb is None:
                results[out_idx] = None
                continue
            vec = list(emb)
            if self.dimension is not None:
                vec = self._adapt_embedding_dimension(vec, int(self.dimension))
            results[out_idx] = vec

        return results

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本的向量嵌入

        Args:
            text: 输入文本

        Returns:
            List[float]: 向量嵌入，如果失败返回None
        """
        if not text.strip():
            return None

        try:
            provider = (self.provider or "").strip().lower()
            if provider in self._REMOTE_PROVIDERS:
                out = self._remote_embeddings([text])
                return out[0] if out else None

            if not self.model:
                return None

            processed_text = self._preprocess_text(text)
            embedding = self.model.encode([processed_text])[0]
            return embedding.tolist()

        except Exception as e:
            logger.error(f"生成嵌入失败: {e}")
            return None

    def generate_batch_embeddings(
        self, texts: List[str]
    ) -> List[Optional[List[float]]]:
        """批量生成文本嵌入

        Args:
            texts: 文本列表

        Returns:
            List[Optional[List[float]]]: 嵌入列表
        """
        if not texts:
            return []

        try:
            provider = (self.provider or "").strip().lower()
            if provider in self._REMOTE_PROVIDERS:
                return self._remote_embeddings(texts)

            if not self.model:
                return [None] * len(texts)

            processed_texts = [self._preprocess_text(text) for text in texts]
            valid_indices = [
                i for i, text in enumerate(processed_texts) if text.strip()
            ]
            valid_texts = [processed_texts[i] for i in valid_indices]
            if not valid_texts:
                return [None] * len(texts)

            embeddings = self.model.encode(valid_texts)
            results: List[Optional[List[float]]] = [None] * len(texts)
            for i, embedding in zip(valid_indices, embeddings):
                results[i] = embedding.tolist()
            return results

        except Exception as e:
            logger.error(f"批量生成嵌入失败: {e}")
            return [None] * len(texts)

    def calculate_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """计算两个嵌入向量的余弦相似度

        Args:
            embedding1: 第一个嵌入向量
            embedding2: 第二个嵌入向量

        Returns:
            float: 相似度分数 (0-1)
        """
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            # 计算余弦相似度
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            # 确保结果在0-1范围内
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.error(f"计算相似度失败: {e}")
            return 0.0

    def find_most_similar(
        self,
        query_embedding: List[float],
        candidate_embeddings: List[List[float]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """找到最相似的嵌入向量

        Args:
            query_embedding: 查询嵌入向量
            candidate_embeddings: 候选嵌入向量列表
            top_k: 返回前k个最相似的结果

        Returns:
            List[Dict]: 相似度结果列表，包含index和similarity
        """
        if not query_embedding or not candidate_embeddings:
            return []

        try:
            similarities = []

            for i, candidate in enumerate(candidate_embeddings):
                if candidate:
                    similarity = self.calculate_similarity(
                        query_embedding, candidate
                    )
                    similarities.append(
                        {
                            'index': i,
                            'similarity': similarity
                        }
                    )

            # 按相似度降序排序
            similarities.sort(key=lambda x: x['similarity'], reverse=True)

            return similarities[:top_k]

        except Exception as e:
            logger.error(f"查找相似嵌入失败: {e}")
            return []

    def _preprocess_text(self, text: str) -> str:
        """预处理文本

        Args:
            text: 原始文本

        Returns:
            str: 预处理后的文本
        """
        if not text:
            return ""

        # 基本清理
        text = text.strip()

        # 限制长度（避免过长文本影响性能）
        max_length = int(os.getenv('EMBEDDING_MAX_LENGTH', 512))
        if len(text) > max_length:
            text = text[:max_length]

        return text

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息

        Returns:
            Dict: 模型信息
        """
        max_length = int(os.getenv('EMBEDDING_MAX_LENGTH', 512))
        return {
            'model_name': self.model_name,
            'dimension': self.dimension,
            'is_loaded': self.model is not None,
            'max_length': max_length
        }

    def encode_for_storage(self, embedding: List[float]) -> str:
        """将嵌入向量编码为存储格式

        Args:
            embedding: 嵌入向量

        Returns:
            str: JSON格式的字符串
        """
        try:
            return json.dumps(embedding, separators=(',', ':'))
        except Exception as e:
            logger.error(f"编码嵌入向量失败: {e}")
            return '[]'

    def decode_from_storage(
        self, encoded_embedding: str
    ) -> Optional[List[float]]:
        """从存储格式解码嵌入向量

        Args:
            encoded_embedding: JSON格式的字符串

        Returns:
            List[float]: 嵌入向量，如果失败返回None
        """
        try:
            return json.loads(encoded_embedding)
        except Exception as e:
            logger.error(f"解码嵌入向量失败: {e}")
            return None

    def validate_embedding(self, embedding: List[float]) -> bool:
        """验证嵌入向量的有效性

        Args:
            embedding: 嵌入向量

        Returns:
            bool: 是否有效
        """
        if not embedding:
            return False

        try:
            # 检查维度
            if len(embedding) != self.dimension:
                return False

            # 检查数值有效性
            vec = np.array(embedding)
            if np.isnan(vec).any() or np.isinf(vec).any():
                return False

            return True

        except Exception:
            return False
