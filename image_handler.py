import os
import base64
import logging
import google.generativeai as genai
from PIL import Image
from io import BytesIO

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量获取Google API密钥
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# 配置Google Gemini API
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logging.warning("未设置 GOOGLE_API_KEY 环境变量")

def image_to_base64(image_bytes):
    """
    将图片转换为base64编码
    """
    return base64.b64encode(image_bytes).decode('utf-8')

async def download_image(bot, file_id):
    """
    下载Telegram图片
    """
    file = await bot.get_file(file_id)
    image_bytes = await file.download_as_bytearray()
    return image_bytes

async def analyze_image_with_gemini(image_bytes):
    """
    使用Google Gemini API分析图片内容
    """
    if not GOOGLE_API_KEY:
        return "（无法分析图片：未配置Google API密钥）"
    
    try:
        # 使用 gemini-2.0-flash 模型，比gemini-pro-vision更先进
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # 将图片字节转换为PIL Image
        image = Image.open(BytesIO(image_bytes))
        
        # 构建提示
        prompt = "请详细描述这张图片中的内容，包括可见的物体、人物、场景、文字等。请用中文回答。"
        
        # 调用API分析图片
        response = model.generate_content([prompt, image])
        
        # 返回分析结果
        return response.text
    except Exception as e:
        logging.error(f"使用Google Gemini API分析图片时出错: {e}")
        return f"（图片分析失败: {str(e)}）"

async def process_image(bot, file_id):
    """
    处理图片：下载、分析、转换为base64
    """
    try:
        # 下载图片
        image_bytes = await download_image(bot, file_id)
        
        # 分析图片
        description = await analyze_image_with_gemini(image_bytes)
        
        # 将图片转换为base64
        base64_image = image_to_base64(image_bytes)
        
        # 创建markdown格式的图片引用
        # base64_markdown = f"![图片](data:image/jpeg;base64,{base64_image})"
        
        # 返回分析结果和base64格式的图片
        return {
            "description": description,
            "base64_image": base64_image
        }
    except Exception as e:
        logging.error(f"处理图片时出错: {e}")
        return {
            "description": f"处理图片时出错: {str(e)}",
            "base64_image": None
        } 