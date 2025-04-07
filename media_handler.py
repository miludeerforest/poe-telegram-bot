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

async def download_file(bot, file_id, max_retries=5, retry_delay=3, initial_wait=5):
    """
    下载Telegram文件，支持重试机制和初始等待
    
    参数:
        bot: Telegram机器人对象
        file_id: 文件ID
        max_retries: 最大重试次数
        retry_delay: 每次重试间隔的秒数
        initial_wait: 大文件初始等待时间（秒）
    """
    # 先获取文件信息
    try:
        file_info = None
        for i in range(3):  # 尝试3次获取文件信息
            try:
                file_info = await bot.get_file(file_id)
                break
            except Exception as e:
                logging.warning(f"尝试获取文件信息失败 ({i+1}/3): {e}")
                await asyncio.sleep(2)
                
        if not file_info:
            logging.error("无法获取文件信息")
            return None
            
        file_size = file_info.file_size
        logging.info(f"文件大小: {file_size} 字节")
        
        # 对于大文件，先等待一段时间确保上传完成
        if file_size and file_size > 10*1024*1024:  # 大于10MB
            file_size_mb = file_size / (1024 * 1024)
            wait_time = initial_wait + int(file_size_mb / 5)  # 每5MB增加1秒等待
            logging.info(f"大文件 ({file_size_mb:.1f}MB)，等待 {wait_time} 秒确保上传完成")
            await asyncio.sleep(wait_time)
    except Exception as e:
        logging.error(f"获取文件信息时出错: {e}")
        file_size = None
    
    # 下载文件，带重试机制
    for attempt in range(max_retries):
        try:
            # 下载文件
            if attempt > 0:
                logging.info(f"重试下载文件 (尝试 {attempt+1}/{max_retries})")
                
            # 重新获取文件对象，避免因长时间等待导致的token失效
            file = await bot.get_file(file_id)
            file_size = file.file_size
            
            # 如果文件太小，可能尚未完全上传，等待一下
            if file_size is not None and file_size < 1024 and attempt < 2:  # 小于1KB的文件可能未完成上传
                logging.info(f"文件可能未完全上传，等待 {retry_delay} 秒 (文件大小: {file_size} 字节)")
                await asyncio.sleep(retry_delay)
                continue
                
            # 下载文件
            logging.info(f"开始下载文件，大小: {file_size} 字节")
            file_bytes = await file.download_as_bytearray()
            
            # 验证文件是否下载完整
            if len(file_bytes) != file_size:
                logging.warning(f"文件下载不完整：期望 {file_size} 字节，实际 {len(file_bytes)} 字节，重试中...")
                # 对于大文件，增加等待时间
                if file_size and file_size > 10*1024*1024:
                    await asyncio.sleep(retry_delay * 2)
                else:
                    await asyncio.sleep(retry_delay)
                continue
                
            logging.info(f"文件下载完成: {len(file_bytes)} 字节")
            return file_bytes
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"下载文件时出错 (尝试 {attempt+1}/{max_retries}): {error_msg}")
            
            # 对"文件不可访问"错误特殊处理
            if "file is not accessible" in error_msg.lower() or "wrong file_id" in error_msg.lower():
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 2)  # 随重试次数增加等待时间
                    logging.info(f"文件可能尚未完全上传，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    
            elif attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
    
    logging.error(f"经过 {max_retries} 次尝试后无法下载文件")
    return None

async def verify_media_file(file_bytes, file_ext):
    """
    验证媒体文件是否有效
    
    参数:
        file_bytes: 文件字节数据
        file_ext: 文件扩展名（.mp4, .mp3, .wav 等）
    
    返回:
        bool: 文件是否有效
    """
    if not file_bytes:
        return False
        
    # 检查文件大小
    if len(file_bytes) < 1024:  # 小于1KB的文件可能无效
        logging.warning(f"媒体文件过小 ({len(file_bytes)} 字节)，可能无效")
        return False
    
    # 视频文件验证
    if file_ext.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        # MP4文件检查（常见的MP4文件特征）
        if file_ext.lower() == '.mp4' and not (file_bytes[:8].startswith(b'\x00\x00\x00') or 
                                     b'ftyp' in file_bytes[:12] or 
                                     b'moov' in file_bytes[:100]):
            logging.warning(f"疑似无效的MP4文件")
            return False
            
        # MOV文件检查
        if file_ext.lower() == '.mov' and not (b'ftyp' in file_bytes[:12] or b'moov' in file_bytes[:100] or b'wide' in file_bytes[:12]):
            logging.warning(f"疑似无效的MOV文件")
            return False
            
        # 一般视频文件特征检测
        # 很多视频格式在开头都会有特定的标记，如果没有这些标记，文件可能无效
        video_signatures = [b'ftyp', b'moov', b'wide', b'mdat', b'AVI', b'RIFF', b'webm', b'matroska']
        if not any(sig in file_bytes[:100] for sig in video_signatures):
            logging.warning(f"视频文件可能无效，没有找到常见的视频文件特征")
            # 不立即返回假，因为有些视频格式可能没有这些特征

    # 音频文件验证
    elif file_ext.lower() in ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']:
        # MP3文件检查
        if file_ext.lower() == '.mp3':
            if not (file_bytes[:3] == b'ID3' or  # ID3标签头
                   file_bytes[:2] == b'\xff\xfb' or  # MPEG音频帧同步标记
                   file_bytes[:2] == b'\xff\xf3' or  # MPEG音频帧变体
                   file_bytes[:2] == b'\xff\xfa' or  # 另一个MPEG变体
                   file_bytes[:2] == b'\xff\xf2'):  # 另一个MPEG变体
                logging.warning(f"疑似无效的MP3文件")
                return False
                
        # WAV文件检查
        if file_ext.lower() == '.wav' and not (file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WAVE'):
            logging.warning(f"疑似无效的WAV文件")
            return False
            
        # OGG文件检查
        if file_ext.lower() == '.ogg' and not file_bytes[:4] == b'OggS':
            logging.warning(f"疑似无效的OGG文件")
            return False
            
        # FLAC文件检查
        if file_ext.lower() == '.flac' and not file_bytes[:4] == b'fLaC':
            logging.warning(f"疑似无效的FLAC文件")
            return False
            
        # AAC和M4A文件检查
        if file_ext.lower() in ['.aac', '.m4a'] and not (b'ftypM4A' in file_bytes[:20] or b'mp42' in file_bytes[:20]):
            logging.warning(f"疑似无效的AAC/M4A文件")
            return False
    
    # 如果以上检测都通过了，我们认为文件可能是有效的
    return True

async def analyze_media_with_gemini(file_bytes, file_ext, media_type, caption="", max_retries=3):
    """
    使用Google Gemini API分析媒体文件内容，支持重试机制
    """
    if not GOOGLE_API_KEY:
        return "（无法分析媒体：未配置Google API密钥）"
    
    # 验证媒体文件
    if not await verify_media_file(file_bytes, file_ext):
        return f"（无法分析媒体：文件验证失败，可能是无效的{media_type}文件）"
    
    temp_path = None
    
    for attempt in range(max_retries + 1):
        try:
            # 每次尝试都创建新的临时文件
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
            
            # 加载多媒体文件，确保文件存在且可访问
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                logging.error(f"临时文件不存在或为空: {temp_path}")
                # 为下一次尝试准备新文件
                await asyncio.sleep(1)
                continue
                
            logging.info(f"上传{media_type}文件到Gemini API...")
            media_file = genai.upload_file(temp_path)
            
            # 确保文件上传成功后再继续
            await asyncio.sleep(1)
            
            # 调用API分析媒体
            logging.info(f"调用Gemini API分析{media_type}内容...")
            response = model.generate_content([prompt, media_file])
            
            # 清除临时文件
            try:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                    temp_path = None
            except Exception as e:
                logging.warning(f"清除临时文件时出错: {e}")
            
            logging.info(f"{media_type}分析完成")
            # 返回分析结果
            return response.text
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"使用Google Gemini API分析{media_type}时出错 (尝试 {attempt+1}/{max_retries+1}): {error_msg}")
            
            # 清除临时文件
            try:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                    temp_path = None
            except Exception as file_e:
                logging.warning(f"清除临时文件时出错: {file_e}")
            
            # 针对特定错误进行特殊处理
            if "is not in an ACTIVE state" in error_msg:
                logging.warning(f"文件状态不是ACTIVE，等待时间更长后重试")
                await asyncio.sleep(5)  # 等待更长时间
                
                # 如果是最后一次尝试，尝试改变策略
                if attempt == max_retries:
                    logging.info("尝试使用其他方法处理媒体...")
                    # 这里可以添加一些备用策略
            elif "file too large" in error_msg.lower():
                return f"（{media_type}文件过大，超出API限制）"
            elif "unsupported file type" in error_msg.lower():
                return f"（不支持的{media_type}文件格式）"
            else:
                # 一般错误等待时间
                await asyncio.sleep(3)
            
            # 如果是最后一次尝试且失败
            if attempt == max_retries:
                logging.error(f"{media_type}分析失败，已尝试{max_retries+1}次")
                return f"（{media_type}分析失败: {error_msg}）"

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
        
        # 检查视频格式 - 使用临时文件和ffprobe
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(video_bytes)
        
        try:
            # 使用ffprobe获取视频信息
            probe_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 
                'format=duration,size:stream=width,height,codec_name', '-of', 
                'json', temp_path
            ]
            
            from video_compressor import run_command
            video_info = await run_command(probe_cmd)
            logging.info(f"视频信息: {video_info}")
            
            # 检查视频是否有效
            if "codec_name" not in video_info and "duration" not in video_info:
                logging.warning("视频文件可能无效或格式不受支持")
                return {
                    "description": "❌ 视频文件格式无效或不受支持，请提供MP4、MOV或AVI格式的视频",
                    "file_content": None
                }
        except Exception as e:
            logging.error(f"获取视频信息失败: {e}")
            # 继续处理，因为有些视频即使ffprobe无法识别，ffmpeg仍可处理
        finally:
            # 清理临时文件
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                logging.warning(f"清理临时文件失败: {e}")
        
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
                
        # 准备分析前检查视频是否符合Gemini要求
        # Gemini通常接受MP4、MOV格式，建议视频时长小于2分钟
        
        # 分析视频前告知用户
        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text="🔍 正在分析视频，如果分析失败，建议尝试：\n1. 上传更短的视频片段（30秒以内）\n2. 使用MP4格式\n3. 降低视频分辨率"
            )
        
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

async def convert_audio_to_mp3(audio_bytes, original_ext, chat_id=None, bot=None):
    """
    将不同格式的音频转换为MP3格式
    
    参数:
        audio_bytes: 音频文件字节
        original_ext: 原始文件扩展名
        chat_id: 聊天ID，用于发送状态消息
        bot: Telegram机器人对象
        
    返回:
        转换后的MP3格式音频字节，如果转换失败则返回None
    """
    # 如果已经是MP3，就不需要转换
    if original_ext.lower() == '.mp3':
        return audio_bytes
        
    # 需要使用ffmpeg转换
    with tempfile.NamedTemporaryFile(suffix=original_ext, delete=False) as input_file:
        input_path = input_file.name
        input_file.write(audio_bytes)
    
    # 创建输出临时文件
    output_fd, output_path = tempfile.mkstemp(suffix='.mp3')
    os.close(output_fd)
    
    try:
        if chat_id and bot:
            await bot.send_message(
                chat_id=chat_id,
                text=f"🔄 正在转换音频格式为MP3，以提高兼容性..."
            )
            
        # 转换命令
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:a', 'libmp3lame',
            '-q:a', '2',  # 高质量MP3
            '-y', output_path
        ]
        
        logging.info(f"开始转换音频: {' '.join(cmd)}")
        
        # 执行ffmpeg命令
        from video_compressor import run_command
        await run_command(cmd)
        
        # 读取转换后的文件
        with open(output_path, 'rb') as f:
            mp3_bytes = f.read()
            
        logging.info(f"音频转换成功: {len(audio_bytes)} 字节 -> {len(mp3_bytes)} 字节")
        return mp3_bytes
        
    except Exception as e:
        logging.error(f"转换音频失败: {e}")
        return None
    
    finally:
        # 清理临时文件
        try:
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
        except Exception as e:
            logging.error(f"清理音频转换临时文件时出错: {e}")

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
            
        # 检查并尝试获取音频格式
        audio_format = '.mp3'  # 默认格式
        
        # 尝试通过ffprobe获取音频信息
        with tempfile.NamedTemporaryFile(suffix='.audio', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_bytes)
            
        try:
            # 使用ffprobe获取音频信息
            probe_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 
                'format=format_name,duration:stream=codec_name', '-of', 
                'json', temp_path
            ]
            
            from video_compressor import run_command
            audio_info = await run_command(probe_cmd)
            logging.info(f"音频信息: {audio_info}")
            
            # 根据ffprobe结果确定文件格式
            if 'mp3' in audio_info.lower():
                audio_format = '.mp3'
            elif 'wav' in audio_info.lower():
                audio_format = '.wav'
            elif 'ogg' in audio_info.lower() or 'vorbis' in audio_info.lower():
                audio_format = '.ogg'
            elif 'aac' in audio_info.lower():
                audio_format = '.aac'
            elif 'm4a' in audio_info.lower() or 'mp4a' in audio_info.lower():
                audio_format = '.m4a'
            elif 'flac' in audio_info.lower():
                audio_format = '.flac'
                
            logging.info(f"检测到音频格式: {audio_format}")
        except Exception as e:
            logging.warning(f"无法获取音频格式信息: {e}，使用默认格式.mp3")
        finally:
            # 清理临时文件
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
        
        # 如果不是MP3格式，尝试转换
        if audio_format.lower() != '.mp3':
            if chat_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"检测到音频格式为 {audio_format}，尝试转换为MP3以提高兼容性..."
                )
            
            converted_bytes = await convert_audio_to_mp3(audio_bytes, audio_format, chat_id, bot)
            if converted_bytes:
                audio_bytes = converted_bytes
                audio_format = '.mp3'
                logging.info("音频已成功转换为MP3格式")
                
                if chat_id:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="✅ 音频格式转换成功"
                    )
            else:
                logging.warning("音频转换失败，将使用原始格式继续处理")
                
                if chat_id:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ 音频格式转换失败，将尝试直接处理，但可能会遇到兼容性问题"
                    )
        
        # 分析音频
        logging.info(f"音频处理准备完成，开始分析...")
        description = await analyze_media_with_gemini(audio_bytes, audio_format, "audio", caption)
        
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