"""图片描述 — 阿里云 DashScope 通义千问 VL 多模态模型。"""

import base64
import os
from config.settings import settings


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def describe_image(image_path: str) -> str | None:
    """调用 Qwen-VL 描述图片内容，返回中文描述文本。"""
    import dashscope
    from dashscope import MultiModalConversation

    if not os.path.exists(image_path):
        return None

    b64 = _encode_image(image_path)
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif", "webp") else "image/png"

    messages = [{
        "role": "user",
        "content": [
            {"image": f"data:{mime};base64,{b64}"},
            {"text": "请详细描述这张图片的内容。如果是图表，说明其中的数据和趋势；如果是架构图，描述各组件及其关系。用中文回答。"},
        ],
    }]

    try:
        resp = MultiModalConversation.call(
            model=settings.VISION_MODEL,
            messages=messages,
            api_key=settings.DASHSCOPE_API_KEY,
        )
        if resp.status_code == 200:
            return resp.output["choices"][0]["message"]["content"][0]["text"]
        return None
    except Exception:
        return None
