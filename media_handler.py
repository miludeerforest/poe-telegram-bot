import os
import base64
import logging
import google.generativeai as genai
from io import BytesIO
import tempfile
import time
import asyncio
from video_compressor import compress_video

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量获取Google API密钥
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# 视频大小限制（MB）
MAX_VIDEO_SIZE_MB = 20
COMPRESSED_TARGET_SIZE_MB = 19  # 压缩目标略小于限制

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

async def process_video(bot, file_id, caption="", chat_id=None):
    """
    处理视频文件
    
    参数:
        bot: Telegram机器人对象
        file_id: 文件ID
        caption: 视频说明
        chat_id: 聊天ID，用于发送处理状态消息
    """
    try:
        logging.info(f"开始处理视频文件 (ID: {file_id})")
        
        # 下载视频
        video_bytes = await download_file(bot, file_id)
        if not video_bytes:
            return {
                "description": "下载视频失败，请确保视频文件可以访问，并重新发送",
                "file_content": None
            }
        
        # 检查视频大小
        video_size_mb = len(video_bytes) / (1024 * 1024)
        logging.info(f"原始视频大小: {video_size_mb:.2f}MB")
        
        # 如果视频超过大小限制，进行压缩
        if video_size_mb > MAX_VIDEO_SIZE_MB:
            logging.info(f"视频文件过大 ({video_size_mb:.2f}MB > {MAX_VIDEO_SIZE_MB}MB)，尝试压缩...")
            
            # 发送压缩提示消息给用户
            if chat_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ 视频文件过大 ({video_size_mb:.2f}MB)，可能导致处理失败。正在尝试压缩视频..."
                )
            
            # 压缩视频
            compressed_bytes = await compress_video(
                video_bytes, 
                target_size_mb=COMPRESSED_TARGET_SIZE_MB
            )
            
            if compressed_bytes:
                compressed_size_mb = len(compressed_bytes) / (1024 * 1024)
                logging.info(f"视频压缩成功: {video_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")
                
                if compressed_size_mb <= MAX_VIDEO_SIZE_MB:
                    # 使用压缩后的视频
                    video_bytes = compressed_bytes
                    
                    # 告知用户压缩结果
                    if chat_id:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ 视频压缩成功: {video_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB"
                        )
                else:
                    logging.warning(f"压缩后视频仍然过大 ({compressed_size_mb:.2f}MB)，无法处理")
                    return {
                        "description": f"❌ 视频压缩后仍然过大 ({compressed_size_mb:.2f}MB > {MAX_VIDEO_SIZE_MB}MB)，无法处理。请上传更小的视频或降低视频质量后重试。",
                        "file_content": None
                    }
            else:
                logging.error("视频压缩失败")
                return {
                    "description": "❌ 视频压缩失败，请上传更小的视频或降低视频质量后重试。",
                    "file_content": None
                }
        
        # 分析视频
        logging.info(f"视频处理准备完成，开始分析...")
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

async def process_audio(bot, file_id, caption="", chat_id=None):
    """
    处理音频文件
    
    参数:
        bot: Telegram机器人对象
        file_id: 文件ID
        caption: 音频说明
        chat_id: 聊天ID，用于发送处理状态消息
    """
    try:
        logging.info(f"开始处理音频文件 (ID: {file_id})")
        
        # 下载音频
        audio_bytes = await download_file(bot, file_id)
        if not audio_bytes:
            return {
                "description": "下载音频失败，请确保音频文件可以访问，并重新发送",
                "file_content": None
            }
        
        # 检查音频大小
        audio_size_mb = len(audio_bytes) / (1024 * 1024)
        logging.info(f"原始音频大小: {audio_size_mb:.2f}MB")
        
        # 音频文件超过大小限制
        if audio_size_mb > MAX_VIDEO_SIZE_MB:  # 使用相同的大小限制
            logging.warning(f"音频文件过大 ({audio_size_mb:.2f}MB > {MAX_VIDEO_SIZE_MB}MB)，无法处理")
            return {
                "description": f"❌ 音频文件过大 ({audio_size_mb:.2f}MB > {MAX_VIDEO_SIZE_MB}MB)，无法处理。请上传更小的音频文件。",
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