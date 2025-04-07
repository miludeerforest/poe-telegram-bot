import os
import base64
import logging
import google.generativeai as genai
from io import BytesIO
import tempfile

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量获取Google API密钥
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# 配置Google Gemini API
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logging.warning("未设置 GOOGLE_API_KEY 环境变量")

def file_to_base64(file_bytes):
    """
    将文件转换为base64编码
    """
    try:
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        logging.error(f"转换文件为base64时出错: {e}")
        return None

async def download_file(bot, file_id):
    """
    下载Telegram文件
    """
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        return file_bytes
    except Exception as e:
        logging.error(f"下载文件时出错: {e}")
        return None

async def analyze_media_with_gemini(file_bytes, file_ext, media_type, caption=""):
    """
    使用Google Gemini API分析媒体文件内容
    """
    if not GOOGLE_API_KEY:
        return "（无法分析媒体：未配置Google API密钥）"
    
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        
        # 使用 gemini-2.0-flash 模型
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # 构建提示根据媒体类型
        if media_type == "video":
            prompt = f"请详细描述这个视频的内容。如果用户提供了说明: {caption}，请特别关注相关内容。请用中文回答。"
        else:  # audio
            prompt = f"请详细描述这个音频的内容。如果用户提供了说明: {caption}，请特别关注相关内容。请用中文回答。"
        
        # 加载多媒体文件
        media_file = genai.upload_file(temp_path)
        
        # 调用API分析媒体
        response = model.generate_content([prompt, media_file])
        
        # 清除临时文件
        try:
            os.unlink(temp_path)
        except:
            pass
        
        # 返回分析结果
        return response.text
    except Exception as e:
        logging.error(f"使用Google Gemini API分析媒体时出错: {e}")
        return f"（媒体分析失败: {str(e)}）"

async def process_video(bot, file_id, caption=""):
    """
    处理视频文件
    """
    try:
        # 下载视频
        video_bytes = await download_file(bot, file_id)
        if not video_bytes:
            return {
                "description": "下载视频失败",
                "file_content": None
            }
        
        # 分析视频
        description = await analyze_media_with_gemini(video_bytes, ".mp4", "video", caption)
        
        # 返回分析结果
        return {
            "description": description,
            "file_content": "视频内容过大，不进行base64编码"
        }
    except Exception as e:
        logging.error(f"处理视频时出错: {e}")
        return {
            "description": f"处理视频时出错: {str(e)}",
            "file_content": None
        }

async def process_audio(bot, file_id, caption=""):
    """
    处理音频文件
    """
    try:
        # 下载音频
        audio_bytes = await download_file(bot, file_id)
        if not audio_bytes:
            return {
                "description": "下载音频失败",
                "file_content": None
            }
        
        # 分析音频
        description = await analyze_media_with_gemini(audio_bytes, ".mp3", "audio", caption)
        
        # 返回分析结果
        return {
            "description": description,
            "file_content": "音频内容过大，不进行base64编码"
        }
    except Exception as e:
        logging.error(f"处理音频时出错: {e}")
        return {
            "description": f"处理音频时出错: {str(e)}",
            "file_content": None
        } 