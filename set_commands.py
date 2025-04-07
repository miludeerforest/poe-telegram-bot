#!/usr/bin/env python3
import asyncio
import os
import logging
from telegram import Bot, BotCommand

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def setup_commands():
    # 获取token
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logging.error("请设置环境变量 TELEGRAM_BOT_TOKEN")
        return
    
    # 创建机器人实例
    bot = Bot(token=token)
    
    # 设置命令菜单
    commands = [
        BotCommand("start", "开始与机器人对话"),
        BotCommand("new", "开始一个新的对话，清空上下文"),
        BotCommand("gpt4", "切换到 GPT-4 模型"),
        BotCommand("claude3", "切换到 Claude-3-Opus 模型"),
        BotCommand("claude35", "切换到 Claude-3.5-Sonnet 模型"),
        BotCommand("stats", "查看您的使用统计"),
        BotCommand("adduser", "【管理员】添加用户到白名单"),
        BotCommand("removeuser", "【管理员】从白名单移除用户"),
        BotCommand("listusers", "【管理员】列出所有允许的用户"),
        BotCommand("allstats", "【管理员】查看所有用户的使用统计"),
        BotCommand("setlimit", "【管理员】设置用户每日使用限制"),
        BotCommand("resetusage", "【管理员】重置用户今日使用量")
    ]
    
    await bot.set_my_commands(commands)
    logging.info("命令菜单已设置")
    
    # 帮助信息
    help_message = """
📸 <b>多媒体处理功能</b>:

1. <b>图片处理</b>:
直接发送图片给机器人，系统将使用Google Gemini 2.0 Flash模型分析图片内容，
然后将分析结果和图片base64编码发送给Claude-3.5-Sonnet处理。

2. <b>视频处理</b>: 
发送视频文件给机器人，系统将使用Google Gemini 2.0 Flash模型分析视频内容，
然后将分析结果发送给Claude-3.5-Sonnet进行进一步处理。

3. <b>音频处理</b>:
发送语音消息或音频文件给机器人，系统将使用Google Gemini 2.0 Flash模型分析音频内容，
然后将分析结果发送给Claude-3.5-Sonnet进行进一步处理。

您可以在发送多媒体文件时添加说明文字，指明您希望了解的具体方面。
所有分析将以中文进行。

<b>注意</b>: 使用此功能需要设置Google API Key环境变量。多媒体处理可能需要较长时间，请耐心等待。
"""
    
    # 发送帮助信息到管理员（第一个管理员）
    admin_ids_str = os.environ.get("ADMIN_USERS", "")
    if admin_ids_str:
        try:
            admin_ids = admin_ids_str.split(',')
            first_admin_id = int(admin_ids[0])
            await bot.send_message(
                chat_id=first_admin_id, 
                text=help_message,
                parse_mode="HTML"
            )
            logging.info(f"已发送帮助信息到管理员 {first_admin_id}")
        except Exception as e:
            logging.error(f"发送帮助信息时出错: {e}")

if __name__ == "__main__":
    asyncio.run(setup_commands()) 