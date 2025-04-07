import os
import logging
import tempfile
import subprocess
import asyncio
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def compress_video(video_bytes, target_size_mb=19, max_width=1280, quality=23):
    """
    使用ffmpeg压缩视频文件到指定大小以下
    
    参数:
        video_bytes: 原始视频数据
        target_size_mb: 目标大小（MB）
        max_width: 最大宽度（像素）
        quality: 质量参数（CRF值，越小质量越高，范围通常是18-28）
        
    返回:
        compressed_bytes: 压缩后的视频数据
    """
    if not video_bytes:
        return None
    
    # 创建输入临时文件
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
        input_path = input_file.name
        input_file.write(video_bytes)
    
    # 创建输出临时文件
    output_fd, output_path = tempfile.mkstemp(suffix='.mp4')
    os.close(output_fd)
    
    try:
        # 获取视频信息
        probe_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 
            'format=duration,size:stream=width,height', '-of', 
            'json', input_path
        ]
        
        probe_result = await run_command(probe_cmd)
        logging.info(f"视频信息: {probe_result}")
        
        # 计算当前视频大小（MB）
        original_size_mb = len(video_bytes) / (1024 * 1024)
        logging.info(f"原始视频大小: {original_size_mb:.2f}MB")
        
        # 如果已经小于目标大小，不需要压缩
        if original_size_mb <= target_size_mb:
            logging.info(f"视频已经小于目标大小({target_size_mb}MB)，不需要压缩")
            os.unlink(output_path)
            return video_bytes
        
        # 设定压缩参数，根据原始大小动态调整
        if original_size_mb > 100:
            # 对于非常大的视频，更激进地压缩
            quality = 28
            max_width = 854  # 480p
        elif original_size_mb > 50:
            quality = 26
            max_width = 1280  # 720p
        
        # 压缩视频的ffmpeg命令
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',
            '-crf', str(quality),
            '-preset', 'medium',
            '-vf', f'scale=min({max_width},iw):-2',  # 按比例缩小，保持宽高比
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y', output_path
        ]
        
        logging.info(f"开始压缩视频: {' '.join(cmd)}")
        
        # 执行ffmpeg命令
        await run_command(cmd)
        
        # 检查输出文件大小
        output_size = os.path.getsize(output_path)
        output_size_mb = output_size / (1024 * 1024)
        
        logging.info(f"压缩后视频大小: {output_size_mb:.2f}MB")
        
        # 如果压缩后仍然太大，可以尝试第二次压缩（更激进）
        if output_size_mb > target_size_mb:
            logging.info(f"第一次压缩后视频仍然太大，尝试更激进的压缩")
            second_output_fd, second_output_path = tempfile.mkstemp(suffix='.mp4')
            os.close(second_output_fd)
            
            # 更激进的压缩
            cmd2 = [
                'ffmpeg', '-i', output_path,
                '-c:v', 'libx264',
                '-crf', str(quality + 6),  # 更高的CRF，质量更低
                '-preset', 'fast',
                '-vf', 'scale=640:-2',  # 强制降低分辨率到640p以下
                '-c:a', 'aac',
                '-b:a', '64k',  # 降低音频质量
                '-y', second_output_path
            ]
            
            logging.info(f"开始第二次压缩视频: {' '.join(cmd2)}")
            await run_command(cmd2)
            
            # 删除第一次的输出
            os.unlink(output_path)
            output_path = second_output_path
            
            output_size = os.path.getsize(output_path)
            output_size_mb = output_size / (1024 * 1024)
            logging.info(f"第二次压缩后视频大小: {output_size_mb:.2f}MB")
        
        # 读取压缩后的视频
        with open(output_path, 'rb') as f:
            compressed_bytes = f.read()
        
        # 返回压缩后的视频数据
        return compressed_bytes
    
    except Exception as e:
        logging.error(f"压缩视频时出错: {e}")
        return None
    
    finally:
        # 清理临时文件
        try:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
        except Exception as e:
            logging.error(f"清理临时文件时出错: {e}")

async def run_command(cmd):
    """
    异步执行命令行命令
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        error_msg = stderr.decode('utf-8', errors='replace')
        logging.error(f"命令执行失败 (代码 {process.returncode}): {error_msg}")
        raise Exception(f"命令执行失败: {error_msg}")
    
    return stdout.decode('utf-8', errors='replace') 