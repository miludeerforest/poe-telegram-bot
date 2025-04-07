import os
import base64
import logging
import google.generativeai as genai
from io import BytesIO
import tempfile
import time
import asyncio

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

async def download_file(bot, file_id, max_retries=3, retry_delay=2):
    """
    下载Telegram文件，支持重试机制
    
    参数:
        bot: Telegram机器人对象
        file_id: 文件ID
        max_retries: 最大重试次数
        retry_delay: 每次重试间隔的秒数
    """
    for attempt in range(max_retries):
        try:
            # 先获取文件信息
            file = await bot.get_file(file_id)
            file_size = file.file_size
            
            # 如果文件太小，可能尚未完全上传，等待一下
            if file_size is not None and file_size < 1024:  # 小于1KB的文件可能未完成上传
                logging.info(f"文件可能未完全上传，等待 {retry_delay} 秒 (文件大小: {file_size} 字节)")
                await asyncio.sleep(retry_delay)
                continue
                
            # 下载文件
            logging.info(f"开始下载文件，大小: {file_size} 字节")
            file_bytes = await file.download_as_bytearray()
            
            # 验证文件是否下载完整
            if len(file_bytes) != file_size:
                logging.warning(f"文件下载不完整：期望 {file_size} 字节，实际 {len(file_bytes)} 字节，重试中...")
                await asyncio.sleep(retry_delay)
                continue
                
            logging.info(f"文件下载完成: {len(file_bytes)} 字节")
            return file_bytes
            
        except Exception as e:
            logging.error(f"下载文件时出错 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                return None
    
    logging.error(f"经过 {max_retries} 次尝试后无法下载文件")
    return None

async def verify_media_file(file_bytes, file_ext):
    """
    验证媒体文件是否有效
    
    参数:
        file_bytes: 文件字节数据
        file_ext: 文件扩展名（.mp4 或 .mp3）
    
    返回:
        bool: 文件是否有效
    """
    if not file_bytes:
        return False
        
    # 检查文件大小
    if len(file_bytes) < 1024:  # 小于1KB的文件可能无效
        logging.warning(f"媒体文件过小 ({len(file_bytes)} 字节)，可能无效")
        return False
    
    # 检查文件头部特征（简单验证）
    if file_ext == '.mp4' and not (file_bytes[:8].startswith(b'\x00\x00\x00') or file_bytes[:8].startswith(b'ftyp')):
        logging.warning(f"疑似无效的MP4文件")
        return False
    
    if file_ext == '.mp3' and not (file_bytes[:3] == b'ID3' or file_bytes[:2] == b'\xff\xfb'):
        logging.warning(f"疑似无效的MP3文件")
        return False
    
    return True

async def analyze_media_with_gemini(file_bytes, file_ext, media_type, caption="", max_retries=2):
    """
    使用Google Gemini API分析媒体文件内容，支持重试机制
    """
    if not GOOGLE_API_KEY:
        return "（无法分析媒体：未配置Google API密钥）"
    
    # 验证媒体文件
    if not await verify_media_file(file_bytes, file_ext):
        return f"（无法分析媒体：文件验证失败，可能是无效的{media_type}文件）"
    
    for attempt in range(max_retries + 1):
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
                temp_file.write(file_bytes)
                temp_path = temp_file.name
            
            logging.info(f"开始使用Gemini分析{media_type}文件 (尝试 {attempt+1}/{max_retries+1})...")
            
            # 使用 gemini-2.0-flash 模型
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # 构建提示根据媒体类型
            if media_type == "video":
                prompt = f"请详细描述这个视频的内容。如果用户提供了说明: {caption}，请特别关注相关内容。请用中文回答。"
            else:  # audio
                prompt = f"请详细描述这个音频的内容。如果用户提供了说明: {caption}，请特别关注相关内容。请用中文回答。"
            
            # 加载多媒体文件
            logging.info(f"上传{media_type}文件到Gemini API...")
            media_file = genai.upload_file(temp_path)
            
            # 调用API分析媒体
            logging.info(f"调用Gemini API分析{media_type}内容...")
            response = model.generate_content([prompt, media_file])
            
            # 清除临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
            
            logging.info(f"{media_type}分析完成")
            # 返回分析结果
            return response.text
            
        except Exception as e:
            logging.error(f"使用Google Gemini API分析{media_type}时出错 (尝试 {attempt+1}/{max_retries+1}): {e}")
            # 清除临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
                
            if attempt < max_retries:
                await asyncio.sleep(3)  # 等待3秒后重试
            else:
                return f"（{media_type}分析失败: {str(e)}）"

async def process_video(bot, file_id, caption=""):
    """
    处理视频文件
    """
    try:
        logging.info(f"开始处理视频文件 (ID: {file_id})")
        
        # 下载视频
        video_bytes = await download_file(bot, file_id)
        if not video_bytes:
            return {
                "description": "下载视频失败，请确保视频文件大小在20MB以内，并重新发送",
                "file_content": None
            }
        
        # 分析视频
        logging.info(f"视频下载完成，开始分析...")
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
        logging.info(f"开始处理音频文件 (ID: {file_id})")
        
        # 下载音频
        audio_bytes = await download_file(bot, file_id)
        if not audio_bytes:
            return {
                "description": "下载音频失败，请确保音频文件大小在20MB以内，并重新发送",
                "file_content": None
            }
        
        # 分析音频
        logging.info(f"音频下载完成，开始分析...")
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