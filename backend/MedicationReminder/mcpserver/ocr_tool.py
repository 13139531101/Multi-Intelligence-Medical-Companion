# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : ocr_tool.py
# @Author: Health Assistant Team
# @Desc  : OCR识别工具 - 用于识别医疗文档中的文字信息

import base64
import os
import json
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

mcp = FastMCP("药品OCR工具")

def call_aliyun_ocr(image_base64: str) -> str:
    """
    调用阿里云OCR服务
    :param image_base64: base64编码的图片数据
    :return: OCR识别结果
    """
    try:
        # 读取凭证
        access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
        access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
        # 默认使用上海区域的OCR端点；可通过环境变量覆盖
        endpoint = os.getenv('ALIYUN_OCR_ENDPOINT', 'ocr-api.cn-shanghai.aliyuncs.com')

        if not access_key_id or not access_key_secret:
            return "阿里云OCR配置缺失，请设置 ALIYUN_ACCESS_KEY_ID 与 ALIYUN_ACCESS_KEY_SECRET"

        # 校验Base64字符串基本合法性（避免非图像字符串导致SDK异常）
        try:
            base64.b64decode(image_base64, validate=True)
        except Exception:
            return "图片Base64数据不合法，请提供有效的Base64编码图片"

        # 动态导入阿里云官方SDK，避免未安装时模块导入失败影响整个服务
        try:
            from alibabacloud_ocr20191230.client import Client as OCRClient
            from alibabacloud_ocr20191230 import models as ocr_models
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_tea_util import models as util_models
            from alibabacloud_tea_util.client import Client as TeaUtilClient
        except ImportError:
            return (
                "阿里云OCR SDK未安装，请安装: alibabacloud-ocr20191230, "
                "alibabacloud-tea-openapi, alibabacloud-tea-util"
            )

        # 创建客户端（显式设置 region_id 以避免 InvalidVersion 问题），并增加端点回退
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=os.getenv('ALIYUN_REGION_ID', 'cn-shanghai'),
        )

        # 端点优先级：环境变量指定 > 上海 > 杭州
        endpoint_candidates = []
        if endpoint:
            endpoint_candidates.append(endpoint)
        endpoint_candidates.extend([
            'ocr-api.cn-shanghai.aliyuncs.com',
            'ocr-api.cn-hangzhou.aliyuncs.com',
        ])

        last_error = None
        runtime = util_models.RuntimeOptions()
        def _region_from_endpoint(ep: str) -> str:
            if 'cn-shanghai' in ep:
                return 'cn-shanghai'
            if 'cn-hangzhou' in ep:
                return 'cn-hangzhou'
            return os.getenv('ALIYUN_REGION_ID', 'cn-shanghai')

        for ep in endpoint_candidates:
            try:
                config.endpoint = ep
                config.region_id = _region_from_endpoint(ep)
                client = OCRClient(config)

                # RecognizeAdvanced：使用属性赋值以兼容SDK的构造器不接收关键字参数
                request = ocr_models.RecognizeAdvancedRequest()
                setattr(request, 'imageBase64', image_base64)
                response = client.recognize_advanced_with_options(request, runtime)
            except Exception as e_adv:
                # 回退到字符识别接口（使用属性赋值避免 __init__ 关键字不匹配）
                try:
                    request = ocr_models.RecognizeCharacterRequest()
                    setattr(request, 'imageBase64', image_base64)
                    response = client.recognize_character_with_options(request, runtime)
                except Exception as e_char:
                    last_error = f"endpoint={ep}, error={str(e_char)}"
                    continue  # 尝试下一个端点

            # 如已获得 response，跳出循环并解析
            if 'response' in locals() and response:
                break

        if 'response' not in locals() or not response:
            return f"阿里云OCR调用失败: {last_error or '未能连接任何端点'}"

        # 解析返回体为字典
        try:
            body_json = TeaUtilClient.to_jsonstring(response.body)
            body = json.loads(body_json) if isinstance(body_json, str) else {}
        except Exception:
            # 兜底：直接转字符串
            body = {"raw": str(response.body)}

        # 从 data/Data 中提取文本内容
        data = body.get('data') or body.get('Data') or {}
        if isinstance(data, dict):
            # 常见字段：content 或 lines/prism_wordsInfo
            text = data.get('content')
            if not text:
                lines = data.get('lines') or data.get('prism_wordsInfo') or []
                if isinstance(lines, list) and lines:
                    # prism_wordsInfo: [{"word": "..."}] 或 {"text": "..."}
                    parts = []
                    for it in lines:
                        if isinstance(it, dict):
                            parts.append(it.get('text') or it.get('word') or '')
                    text = "\n".join([p for p in parts if p])
            if not text:
                # 兜底：返回完整data字典
                text = json.dumps(data, ensure_ascii=False)
        elif isinstance(data, str):
            text = data
        else:
            text = json.dumps(body, ensure_ascii=False)

        return text

    except Exception as e:
        return f"阿里云OCR调用失败: {str(e)}"

def call_local_ocr(image_base64: str) -> str:
    """
    本地离线OCR兜底：使用 pytesseract 对图片进行识别。
    - 优先尝试中文简体(chi_sim) + 英文(eng)，若语言包缺失则回退到英文。
    - 未安装 pytesseract 或系统未安装 Tesseract 可执行程序时，返回可读的错误提示。
    """
    try:
        # 动态导入，避免环境未安装导致全局报错
        try:
            import pytesseract  # type: ignore
        except Exception:
            return "本地OCR兜底不可用：未安装 pytesseract，请安装 pytesseract 与 Pillow，并在系统安装 Tesseract。"

        try:
            from PIL import Image
            from io import BytesIO
        except Exception:
            return "本地OCR兜底不可用：未安装 Pillow，请安装 Pillow。"

        # 优先从环境变量读取 TesserACT 可执行路径；否则尝试常见安装目录
        try:
            tess_env = os.getenv('TESSERACT_PATH')
            candidates = []
            if tess_env and isinstance(tess_env, str) and tess_env.strip():
                candidates.append(tess_env.strip())
            candidates.extend([
                r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
                r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
            ])

            for p in candidates:
                try:
                    if p and os.path.exists(p):
                        pytesseract.pytesseract.tesseract_cmd = p  # type: ignore
                        break
                except Exception:
                    # 如果设置失败，继续尝试下一个候选路径
                    continue
        except Exception:
            # 忽略路径设置的异常，交由后续调用报错并提示
            pass

        # 配置 TESSDATA_PREFIX（中文语言包路径）
        try:
            tessdata_prefix = os.getenv('TESSDATA_PREFIX')
            if tessdata_prefix and isinstance(tessdata_prefix, str) and tessdata_prefix.strip():
                # 赋值给环境变量，Tesseract 会自动读取
                os.environ['TESSDATA_PREFIX'] = tessdata_prefix.strip()
        except Exception:
            # 忽略 TESSDATA_PREFIX 配置异常
            pass

        # 解码Base64到图像
        try:
            img_bytes = base64.b64decode(image_base64)
            img = Image.open(BytesIO(img_bytes))
        except Exception:
            return "本地OCR兜底失败：图片Base64无效或无法打开。"

        # 语言选择：支持环境变量 OCR_LANG（例如 "chi_sim+eng"），否则按默认顺序尝试
        lang_override = os.getenv('OCR_LANG')
        if lang_override and isinstance(lang_override, str) and lang_override.strip():
            lang_candidates = [lang_override.strip()]
        else:
            lang_candidates = ["chi_sim+eng", "chi_sim", "chi_tra", "eng"]
        last_err: str | None = None
        for lang in lang_candidates:
            try:
                text = pytesseract.image_to_string(img, lang=lang)
                # 成功（允许空字符串，仍视为成功识别结果）
                return text.strip()
            except Exception as e:
                last_err = str(e)
                continue

        return f"本地OCR兜底失败：{last_err or '未知错误'}"
    except Exception as e:
        return f"本地OCR兜底异常：{str(e)}"

def call_aliyun_ocr_v2021(image_base64: str) -> str:
    """
    使用阿里云 OCR 统一识别（2021-07-07）RecognizeAllText。
    - 通过 `ALIYUN_OCR_TYPE` 指定 Type（默认 general）。
    - 支持端点与区域的回退（环境变量 > 上海 > 杭州）。
    """
    try:
        access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
        access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
        endpoint = os.getenv('ALIYUN_OCR_ENDPOINT', 'ocr-api.cn-shanghai.aliyuncs.com')
        region_default = os.getenv('ALIYUN_REGION_ID', 'cn-shanghai')
        ocr_type = os.getenv('ALIYUN_OCR_TYPE', 'general')

        if not access_key_id or not access_key_secret:
            return "阿里云OCR(2021)配置缺失，请设置 ALIYUN_ACCESS_KEY_ID 与 ALIYUN_ACCESS_KEY_SECRET"

        # 校验Base64字符串基本合法性
        try:
            decoded_bytes = base64.b64decode(image_base64, validate=True)
        except Exception:
            return "图片Base64数据不合法，请提供有效的Base64编码图片"

        # 动态导入 2021-07-07 版 SDK
        try:
            from alibabacloud_ocr_api20210707.client import Client as OCRClient2021
            from alibabacloud_ocr_api20210707 import models as ocr2021_models
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_tea_util import models as util_models
            from alibabacloud_tea_util.client import Client as TeaUtilClient
        except ImportError:
            return (
                "阿里云OCR(2021) SDK未安装，请安装: alibabacloud-ocr-api20210707, "
                "alibabacloud-tea-openapi, alibabacloud-tea-util"
            )

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=region_default,
        )

        endpoint_candidates = []
        if endpoint:
            endpoint_candidates.append(endpoint)
        endpoint_candidates.extend([
            'ocr-api.cn-shanghai.aliyuncs.com',
            'ocr-api.cn-hangzhou.aliyuncs.com',
        ])

        runtime = util_models.RuntimeOptions()
        last_error = None

        def _region_from_endpoint(ep: str) -> str:
            if 'cn-shanghai' in ep:
                return 'cn-shanghai'
            if 'cn-hangzhou' in ep:
                return 'cn-hangzhou'
            return region_default

        # 构造 Type 尝试候选：先尝试不传 Type，其次尝试多种常见取值
        type_candidates = [None]
        if isinstance(ocr_type, str) and ocr_type.strip():
            orig = ocr_type.strip()
            type_candidates.append(orig)
            title = orig[:1].upper() + orig[1:]
            if title not in type_candidates:
                type_candidates.append(title)
        for t in ['General', 'AllText', 'Text', 'GeneralText', 'AdvancedGeneral', 'PrintedText', 'Handwriting', 'Document']:
            if t not in type_candidates:
                type_candidates.append(t)

        for ep in endpoint_candidates:
            config.endpoint = ep
            config.region_id = _region_from_endpoint(ep)
            client = OCRClient2021(config)

            for tp in type_candidates:
                try:
                    req = ocr2021_models.RecognizeAllTextRequest()
                    # 有些环境下 Type 为可选，若 tp 为 None 则不设置
                    if tp is not None:
                        setattr(req, 'type', tp)
                    # 使用原始二进制作为 body
                    setattr(req, 'body', decoded_bytes)
                    response = client.recognize_all_text_with_options(req, runtime)
                except Exception as e_req:
                    last_error = f"endpoint={ep}, type={tp}, error={str(e_req)}"
                    response = None
                    continue

                if response:
                    break

            if response:
                break

        if 'response' not in locals() or not response:
            tried = ','.join([str(t) for t in type_candidates])
            return f"阿里云OCR(2021)调用失败: {last_error or '未能连接任何端点'}；Type尝试: {tried}"

        # 解析返回
        try:
            body_json = TeaUtilClient.to_jsonstring(response.body)
            body = json.loads(body_json) if isinstance(body_json, str) else {}
        except Exception:
            body = {"raw": str(response.body)}

        data = body.get('data') or body.get('Data') or {}
        if isinstance(data, dict):
            text = data.get('content')
            if not text:
                lines = data.get('lines') or data.get('prism_wordsInfo') or []
                if isinstance(lines, list) and lines:
                    parts = []
                    for it in lines:
                        if isinstance(it, dict):
                            parts.append(it.get('text') or it.get('word') or '')
                    text = "\n".join([p for p in parts if p])
            if not text:
                text = json.dumps(data, ensure_ascii=False)
        elif isinstance(data, str):
            text = data
        else:
            text = json.dumps(body, ensure_ascii=False)

        return text
    except Exception as e:
        return f"阿里云OCR(2021)调用失败: {str(e)}"

@mcp.tool()
def extract_text_from_image(image_base64: str) -> str:
    """
    从医疗文档图片中提取文字
    :param image_base64: base64编码的图片数据
    :return: 提取的文字内容
    """
    try:
        # 检查OCR服务提供商
        ocr_provider = os.getenv('OCR_PROVIDER', 'aliyun')
        
        if ocr_provider == 'aliyun':
            # 默认优先使用 2021-07-07 版；失败回退 2019-12-30；再回退本地
            version = os.getenv('ALIYUN_OCR_VERSION', '2021-07-07')

            if version == '2021-07-07':
                ali_text = call_aliyun_ocr_v2021(image_base64)
                if isinstance(ali_text, str) and ali_text.startswith("阿里云OCR(2021)调用失败"):
                    ali2019_text = call_aliyun_ocr(image_base64)
                    if isinstance(ali2019_text, str) and ali2019_text.startswith("阿里云OCR调用失败"):
                        local_text = call_local_ocr(image_base64)
                        if isinstance(local_text, str) and (
                            local_text.startswith("本地OCR兜底不可用") or local_text.startswith("本地OCR兜底失败") or local_text.startswith("本地OCR兜底异常")
                        ):
                            return f"{ali_text}；回退2019：{ali2019_text}；兜底：{local_text}"
                        return local_text
                    return ali2019_text
                return ali_text
            else:
                ali2019_text = call_aliyun_ocr(image_base64)
                if isinstance(ali2019_text, str) and ali2019_text.startswith("阿里云OCR调用失败"):
                    local_text = call_local_ocr(image_base64)
                    if isinstance(local_text, str) and (
                        local_text.startswith("本地OCR兜底不可用") or local_text.startswith("本地OCR兜底失败") or local_text.startswith("本地OCR兜底异常")
                    ):
                        return f"{ali2019_text}；兜底：{local_text}"
                    return local_text
                return ali2019_text
        elif ocr_provider == 'local':
            # 允许通过环境变量强制使用本地OCR
            return call_local_ocr(image_base64)
        else:
            return "不支持的OCR服务提供商，请检查OCR_PROVIDER环境变量"
            
    except Exception as e:
         return f"OCR识别失败: {str(e)}"

@mcp.tool()
def validate_medical_document(text: str) -> str:
    """
    验证医疗文档的有效性
    :param text: OCR识别的文本
    :return: JSON格式的验证结果
    """
    try:
        # 检查是否包含医疗相关关键词
        medical_keywords = [
            '患者', '姓名', '性别', '年龄', '诊断', '处方', '医生', 
            '科室', '检查', '化验', '医院', '主诉', '病史', '治疗',
            '药物', '用法', '用量', '复查', '医嘱'
        ]
        
        found_keywords = [kw for kw in medical_keywords if kw in text]
        confidence = len(found_keywords) / len(medical_keywords)
        
        # 判断文档类型
        document_type = "unknown"
        if any(kw in text for kw in ['处方', '药品', '用法', '用量']):
            document_type = "prescription"
        elif any(kw in text for kw in ['检查报告', '化验单', '检验结果']):
            document_type = "inspection_report"
        elif any(kw in text for kw in ['病历', '诊断', '主诉', '病史']):
            document_type = "medical_record"
        elif any(kw in text for kw in ['住院', '出院', '手术']):
            document_type = "hospital_record"
            
        result = {
            'is_medical_document': confidence > 0.2,  # 至少包含20%的医疗关键词
            'confidence': round(confidence, 2),
            'document_type': document_type,
            'found_keywords': found_keywords,
            'keyword_count': len(found_keywords),
            'total_keywords': len(medical_keywords)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            'error': f"验证失败: {str(e)}",
            'is_medical_document': False,
            'confidence': 0
        }, ensure_ascii=False)

if __name__ == '__main__':
    # 启动FastMCP服务器
    mcp.run()
