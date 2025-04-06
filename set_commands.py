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
        BotCommand("adduser", "【管理员】添加用户到白名单"),
        BotCommand("removeuser", "【管理员】从白名单移除用户"),
        BotCommand("listusers", "【管理员】列出所有允许的用户")
    ]
    
    await bot.set_my_commands(commands)
    logging.info("命令菜单已设置")
    
    # 帮助信息
    help_message = """
📸 <b>图片处理功能已更新</b>:
直接发送图片给机器人，系统将使用Google Gemini 2.0 Flash模型分析图片内容，
然后将分析结果和图片base64编码发送给Claude-3.5-Sonnet处理。

您可以在发送图片时添加说明文字，说明您想了解图片的哪些方面。
图片分析将以中文进行，支持识别物体、人物、场景、文字等内容。

<b>注意</b>: 使用此功能需要设置Google API Key环境变量。
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