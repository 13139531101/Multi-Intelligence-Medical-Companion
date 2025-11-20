import os
import logging
from typing import List, Optional, Dict, Any
try:
    import numpy as np  # type: ignore
    _HAS_NUMPY = True
except Exception:
    np = None  # type: ignore
    _HAS_NUMPY = False
# from sentence_transformers import SentenceTransformer
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
    _HAS_SENTENCE_TRANSFORMERS = True
except Exception:
    SentenceTransformer = None  # type: ignore
    _HAS_SENTENCE_TRANSFORMERS = False
import json

logger = logging.getLogger(__name__)

class EmbeddingService:
    """嵌入服务 - 负责生成和管理文本向量嵌入"""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        self.model = None
        self.dimension = None
        self._use_simple_embedding = False
        self._load_model()
    
    def _load_model(self):
        """加载嵌入模型"""
        if not _HAS_SENTENCE_TRANSFORMERS:
            logger.warning("sentence-transformers 未安装，将使用简单本地嵌入实现")
            self.model = None
            self.dimension = 384
            self._use_simple_embedding = True
            return
        try:
            logger.info(f"正在加载嵌入模型: {self.model_name}")
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
        if not _HAS_SENTENCE_TRANSFORMERS:
            logger.warning("无法加载备用模型（sentence-transformers 未安装），改用简单本地嵌入实现")
            self.model = None
            self.dimension = 384  # 默认维度
            self._use_simple_embedding = True
            return
        try:
            logger.info("尝试加载备用嵌入模型")
            self.model_name = 'paraphrase-MiniLM-L6-v2'
            self.model = SentenceTransformer(self.model_name)
            
            test_embedding = self.model.encode(["test"])
            self.dimension = len(test_embedding[0])
            
            logger.info(f"备用嵌入模型加载成功: {self.model_name}")
        except Exception as e:
            logger.error(f"备用嵌入模型加载失败: {e}")
            logger.warning("将使用简单的本地嵌入实现")
            self.model = None
            self.dimension = 384  # 默认维度
            self._use_simple_embedding = True
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本的向量嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 向量嵌入，如果失败返回None
        """
        if not text.strip():
            return None
        
        # 如果使用简单嵌入实现
        if self._use_simple_embedding:
            return self._simple_embedding(text)
        
        if not self.model:
            return None
        
        try:
            # 预处理文本
            processed_text = self._preprocess_text(text)
            
            # 生成嵌入
            embedding = self.model.encode([processed_text])[0]
            
            # 转换为Python列表
            return embedding.tolist()
            
        except Exception as e:
            logger.error(f"生成嵌入失败: {e}")
            return None
    
    def generate_batch_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """批量生成文本嵌入
        
        Args:
            texts: 文本列表
            
        Returns:
            List[Optional[List[float]]]: 嵌入列表
        """
        if self._use_simple_embedding:
            return [self._simple_embedding(text) if text and text.strip() else None for text in texts]
        
        if not texts:
            return []
        
        if not self.model:
            return [None] * len(texts)
        
        try:
            # 预处理文本
            processed_texts = [self._preprocess_text(text) for text in texts]
            
            # 过滤空文本
            valid_indices = [i for i, text in enumerate(processed_texts) if text.strip()]
            valid_texts = [processed_texts[i] for i in valid_indices]
            
            if not valid_texts:
                return [None] * len(texts)
            
            # 批量生成嵌入
            embeddings = self.model.encode(valid_texts)
            
            # 构建结果列表
            results = [None] * len(texts)
            for i, embedding in zip(valid_indices, embeddings):
                results[i] = embedding.tolist()
            
            return results
            
        except Exception as e:
            logger.error(f"批量生成嵌入失败: {e}")
            return [None] * len(texts)
    
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """计算两个嵌入向量的余弦相似度
        
        Args:
            embedding1: 第一个嵌入向量
            embedding2: 第二个嵌入向量
            
        Returns:
            float: 相似度分数 (0-1)
        """
        try:
            if _HAS_NUMPY:
                vec1 = np.array(embedding1)
                vec2 = np.array(embedding2)
                dot_product = np.dot(vec1, vec2)
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
            else:
                # 纯 Python 余弦相似度实现
                dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
                norm1 = (sum(a * a for a in embedding1)) ** 0.5
                norm2 = (sum(b * b for b in embedding2)) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return max(0.0, min(1.0, (similarity + 1) / 2))
        except Exception as e:
            logger.error(f"计算相似度失败: {e}")
            return 0.0
    
    def find_most_similar(self, query_embedding: List[float], 
                         candidate_embeddings: List[List[float]], 
                         top_k: int = 5) -> List[Dict[str, Any]]:
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
                    similarity = self.calculate_similarity(query_embedding, candidate)
                    similarities.append({
                        'index': i,
                        'similarity': similarity
                    })
            
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
        return {
            'model_name': self.model_name,
            'dimension': self.dimension,
            'is_loaded': self.model is not None,
            'max_length': int(os.getenv('EMBEDDING_MAX_LENGTH', 512))
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
    
    def decode_from_storage(self, encoded_embedding: str) -> Optional[List[float]]:
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
            if _HAS_NUMPY:
                vec = np.array(embedding)
                if np.isnan(vec).any() or np.isinf(vec).any():
                    return False
            else:
                import math
                for x in embedding:
                    if not math.isfinite(x):
                        return False
            return True
        except Exception:
            return False
    
    def _simple_embedding(self, text: str) -> List[float]:
        """简单的本地嵌入实现（基于字符哈希）
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 384维的嵌入向量
        """
        import hashlib
        
        # 预处理文本
        processed_text = self._preprocess_text(text)
        
        # 生成多个哈希值来创建向量
        embedding = []
        
        # 使用不同的种子生成384个特征
        for i in range(self.dimension):
            # 结合文本和索引生成哈希
            hash_input = f"{processed_text}_{i}".encode('utf-8')
            hash_value = hashlib.md5(hash_input).hexdigest()
            
            # 将哈希值转换为浮点数（-1到1之间）
            numeric_value = int(hash_value[:8], 16) / (16**8 / 2) - 1
            embedding.append(numeric_value)
        
        return embedding