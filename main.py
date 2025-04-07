import asyncio
import fastapi_poe as fp
from telegram import Update, constants, BotCommand
from telegram.ext import Application, MessageHandler, filters, CommandHandler
import logging
import os
import image_handler
import media_handler  # 导入媒体处理模块
import usage_stats  # 导入用户使用统计模块
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量获取API密钥
api_key = os.environ.get("POE_API_KEY", "")
bot_names = {
    'gpt4': 'GPT-4',
    'claude3': 'Claude-3-Opus',
    'claude35': 'Claude-3.5-Sonnet'  # 添加Claude-3.5-Sonnet模型
}
default_bot_name = bot_names['claude3']

# 用户会话管理
user_tasks = {}
user_context = {}

# 管理员ID列表 - 从环境变量获取
admin_users_str = os.environ.get("ADMIN_USERS", "1561126701")  # 默认包含提供的ID
admin_users = list(map(int, admin_users_str.split(',')))
logging.info(f"管理员ID列表: {admin_users}")

# 从环境变量获取允许的用户ID列表
allowed_users_str = os.environ.get("ALLOWED_USERS", "")
# 初始化允许用户列表，包含所有管理员ID
if allowed_users_str:
    allowed_users = list(map(int, allowed_users_str.split(',')))
    # 确保管理员总是在允许列表中
    for admin_id in admin_users:
        if admin_id not in allowed_users:
            allowed_users.append(admin_id)
else:
    # 如果环境变量为空，初始时只有管理员可以使用
    allowed_users = admin_users.copy()

logging.info(f"已启用用户白名单，允许的用户ID: {allowed_users}")

# 从Poe获取响应
async def get_responses(api_key, messages, response_list, done, bot_name):
    async for chunk in fp.get_bot_response(messages=messages, bot_name=bot_name, api_key=api_key):
        response_list.append(chunk.text)
    done.set()
    
# 更新Telegram消息
async def update_telegram_message(update, context, response_list, done, response_text, update_interval=1):
    response_message = None
    last_response_text = ""

    while not done.is_set():
        if response_list:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

            response_text[0] += "".join(response_list)
            response_list.clear()

            if response_text[0].strip() != last_response_text.strip():
                try:
                    if response_message is None:
                        response_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text[0], parse_mode="Markdown")
                    else:
                        await response_message.edit_text(response_text[0], parse_mode="Markdown")
                except Exception:
                    if response_message is None:
                        response_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text[0])
                    else:
                        await response_message.edit_text(response_text[0])
                
                last_response_text = response_text[0]

        await asyncio.sleep(update_interval)

    # 最后检查是否还有未处理的响应
    if response_list:
        response_text[0] += "".join(response_list)
        response_list.clear()

        if response_text[0].strip() != last_response_text.strip():
            try:
                if response_message is None:
                    response_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text[0], parse_mode="Markdown")
                else:
                    await response_message.edit_text(response_text[0], parse_mode="Markdown")
            except Exception:
                if response_message is None:
                    response_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text[0])
                else:
                    await response_message.edit_text(response_text[0])

# 处理用户请求
async def handle_user_request(user_id, update, context):
    if user_id in user_context and user_context[user_id]['messages']:
        response_list = []
        done = asyncio.Event()
        response_text = [""]
        
        # 创建两个任务：一个获取AI响应，一个更新Telegram消息
        api_task = asyncio.create_task(get_responses(api_key, user_context[user_id]['messages'], response_list, done, user_context[user_id]['bot_name']))
        telegram_task = asyncio.create_task(update_telegram_message(update, context, response_list, done, response_text))

        await asyncio.gather(api_task, telegram_task)

        # 将AI的响应添加到用户上下文中
        user_context[user_id]['messages'].append(fp.ProtocolMessage(role="bot", content=response_text[0]))

# 检查用户是否有权限使用机器人
def check_user_permission(user_id, update, context):
    if user_id not in allowed_users:
        logging.warning(f"未授权用户 {user_id} 尝试使用机器人")
        asyncio.create_task(context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"抱歉，您没有权限使用此机器人。\n您的用户ID是: {user_id}"
        ))
        return False
    return True

# 处理用户图片
async def handle_photo(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    # 检查使用限制
    allow_request, daily_used, daily_limit = usage_stats.usage_stats.record_request(
        user_id=user_id, 
        model=bot_names['claude35'],  # 图片处理使用Claude-3.5
        is_image=True
    )
    
    if not allow_request:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"🚫 您今日的请求配额已用尽（{daily_used}/{daily_limit}）。请明天再试或联系管理员提高限制。"
        )
        return
    
    logging.info(f"开始处理用户 {user_id} 的图片请求 (今日第 {daily_used}/{daily_limit} 次请求)")
    
    # 获取图片ID (选择最大分辨率的图片)
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    # 告知用户图片正在处理
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="正在使用Google Gemini 2.0分析您的图片，请稍等..."
    )
    
    # 处理图片
    result = await image_handler.process_image(context.bot, file_id)
    
    # 用户说明文本
    caption = update.message.caption or "请分析这张图片"
    
    # 构建消息内容
    if result["base64_image"]:
        # 构建提示
        prompt = f"""以下是一张图片的分析（由Google Gemini 2.0 Flash模型生成）以及图片的base64编码：

图片分析:
{result["description"]}

用户说明: {caption}

图片的base64编码（已省略部分内容）:
{result["base64_image"][:1000]}...

请根据上述图片分析和用户说明，详细回答用户的问题。如果用户没有特定问题，请对图片内容进行深入解读。"""
        
        # 添加到用户上下文
        message = fp.ProtocolMessage(role="user", content=prompt)
        
        # 获取或创建用户上下文
        if user_id not in user_context:
            user_context[user_id] = {'messages': [message], 'bot_name': bot_names['claude35']}  # 图片处理默认使用Claude-3.5-Sonnet
        else:
            if user_context[user_id]['bot_name'] != bot_names['claude35']:
                # 临时记住原来的模型
                original_model = user_context[user_id]['bot_name']
                # 切换到Claude-3.5-Sonnet
                user_context[user_id]['bot_name'] = bot_names['claude35']
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, 
                    text=f"图片处理已临时切换到 {bot_names['claude35']} 模型"
                )
            user_context[user_id]['messages'].append(message)
        
        # 处理用户请求
        if user_id not in user_tasks or user_tasks[user_id].done():
            user_tasks[user_id] = asyncio.create_task(handle_user_request(user_id, update, context))
    else:
        # 处理图片失败
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"处理图片时出错: {result['description']}"
        )

# 处理用户视频
async def handle_video(update: Update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    # 检查使用限制
    allow_request, daily_used, daily_limit = usage_stats.usage_stats.record_request(
        user_id=user_id, 
        model="Gemini-2.0-Flash",  # 视频处理使用Gemini-2.0-Flash
        is_image=True  # 视频也算作多模态请求
    )
    
    if not allow_request:
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"🚫 您今日的请求配额已用尽（{daily_used}/{daily_limit}）。请明天再试或联系管理员提高限制。"
        )
        return
    
    logging.info(f"开始处理用户 {user_id} 的视频请求 (今日第 {daily_used}/{daily_limit} 次请求)")
    
    # 获取视频信息
    video = update.message.video
    file_id = video.file_id
    duration = video.duration
    file_size = video.file_size
    
    # 检查视频时长和大小
    if duration > 300:  # 大于5分钟的视频
        await context.bot.send_message(
            chat_id=chat_id, 
            text="⚠️ 视频时长超过5分钟，可能无法完整分析。建议上传较短的视频片段。"
        )
    
    if file_size > 20*1024*1024 and file_size <= 50*1024*1024:  # 大于20MB但小于50MB
        await context.bot.send_message(
            chat_id=chat_id, 
            text="⚠️ 视频文件较大，将尝试自动压缩。如处理失败，请上传更小的视频或降低视频质量。"
        )
    elif file_size > 50*1024*1024:  # 大于50MB
        await context.bot.send_message(
            chat_id=chat_id, 
            text="⚠️ 视频文件过大，可能超出处理能力。将尝试自动压缩，但成功率较低。建议手动压缩后重新上传。"
        )
    
    # 告知用户视频正在处理
    progress_message = await context.bot.send_message(
        chat_id=chat_id, 
        text="📥 正在接收视频文件，请稍等..."
    )
    
    # 更新进度信息
    await asyncio.sleep(2)  # 等待文件上传
    await progress_message.edit_text("📥 正在接收视频文件，请稍等...\n⏳ 正在下载文件...")
    
    # 处理视频
    caption = update.message.caption or "请分析这个视频"
    result = await media_handler.process_video(context.bot, file_id, caption, chat_id)
    
    # 更新进度消息
    if "下载视频失败" in result["description"] or "视频压缩后仍然过大" in result["description"] or "视频压缩失败" in result["description"]:
        await progress_message.edit_text(f"❌ {result['description']}")
        return
    
    await progress_message.edit_text("📥 视频接收完成\n🔍 正在使用Google Gemini 2.0 Flash分析视频内容...\n⏳ 这可能需要较长时间，请耐心等待")
    
    # 构建消息内容
    if result["description"]:
        # 视频分析完成，更新进度消息
        if "分析失败" in result["description"]:
            await progress_message.edit_text(f"❌ {result['description']}")
            return
            
        await progress_message.edit_text("📥 视频接收完成\n✅ 视频分析完成\n💬 正在生成详细回复...")
        
        # 构建提示
        prompt = f"""以下是一个视频的分析（由Google Gemini 2.0 Flash模型生成）：

视频分析:
{result["description"]}

用户说明: {caption}

请根据上述视频分析和用户说明，详细回答用户的问题。如果用户没有特定问题，请对视频内容进行深入解读。"""
        
        # 添加到用户上下文
        message = fp.ProtocolMessage(role="user", content=prompt)
        
        # 获取或创建用户上下文
        if user_id not in user_context:
            user_context[user_id] = {'messages': [message], 'bot_name': bot_names['claude35']}  # 视频处理默认使用Claude-3.5-Sonnet
        else:
            if user_context[user_id]['bot_name'] != bot_names['claude35']:
                # 临时记住原来的模型
                original_model = user_context[user_id]['bot_name']
                # 切换到Claude-3.5-Sonnet
                user_context[user_id]['bot_name'] = bot_names['claude35']
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"视频处理已临时切换到 {bot_names['claude35']} 模型"
                )
            user_context[user_id]['messages'].append(message)
        
        # 处理用户请求
        if user_id not in user_tasks or user_tasks[user_id].done():
            user_tasks[user_id] = asyncio.create_task(handle_user_request(user_id, update, context))
    else:
        # 处理视频失败
        await progress_message.edit_text(f"❌ 处理视频时出错: {result.get('description', '未知错误')}")

# 处理用户音频
async def handle_audio(update: Update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    # 检查使用限制
    allow_request, daily_used, daily_limit = usage_stats.usage_stats.record_request(
        user_id=user_id, 
        model="Gemini-2.0-Flash",  # 音频处理使用Gemini-2.0-Flash
        is_image=True  # 音频也算作多模态请求
    )
    
    if not allow_request:
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"🚫 您今日的请求配额已用尽（{daily_used}/{daily_limit}）。请明天再试或联系管理员提高限制。"
        )
        return
    
    logging.info(f"开始处理用户 {user_id} 的音频请求 (今日第 {daily_used}/{daily_limit} 次请求)")
    
    # 获取音频文件ID (支持voice和audio两种消息类型)
    if update.message.voice:
        audio = update.message.voice
        audio_type = "语音"
        file_format = "ogg"  # Telegram的语音消息默认为OGG格式
    else:
        audio = update.message.audio
        audio_type = "音频"
        file_format = audio.mime_type.split('/')[-1] if audio.mime_type else "未知"
    
    file_id = audio.file_id
    duration = getattr(audio, 'duration', None)
    file_size = getattr(audio, 'file_size', None)
    
    logging.info(f"接收到{audio_type}，格式: {file_format}, 大小: {file_size} 字节, 时长: {duration}秒")
    
    # 检查音频时长和大小
    if duration and duration > 300:  # 大于5分钟的音频
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"⚠️ {audio_type}时长超过5分钟，可能无法完整分析。建议上传较短的{audio_type}片段。"
        )
    
    if file_size and file_size > 20*1024*1024:  # 大于20MB
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"⚠️ {audio_type}文件过大，可能导致处理失败。建议上传小于20MB的{audio_type}文件。"
        )
    
    # 告知用户音频正在处理
    progress_message = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"📥 正在接收{audio_type}文件，请稍等..."
    )
    
    # 更新进度信息
    await asyncio.sleep(2)  # 等待文件上传
    await progress_message.edit_text(f"📥 正在接收{audio_type}文件，请稍等...\n⏳ 正在下载文件...")
    
    # 处理音频
    caption = update.message.caption or f"请分析这个{audio_type}"
    result = await media_handler.process_audio(context.bot, file_id, caption, chat_id)
    
    # 更新进度消息
    if "下载音频失败" in result["description"] or "音频文件过大" in result["description"]:
        await progress_message.edit_text(f"❌ {result['description']}")
        return
    
    try:
        await progress_message.edit_text(f"📥 {audio_type}接收完成\n🔍 正在使用Google Gemini 2.0 Flash分析{audio_type}内容...\n⏳ 这可能需要较长时间，请耐心等待")
    except Exception as e:
        logging.warning(f"更新进度消息失败: {e}")
        # 可能是由于消息已被其他更新替换，创建新消息
        progress_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔍 正在使用Google Gemini 2.0 Flash分析{audio_type}内容...\n⏳ 这可能需要较长时间，请耐心等待"
        )
    
    # 构建消息内容
    if result["description"]:
        # 音频分析完成，更新进度消息
        if "分析失败" in result["description"]:
            try:
                await progress_message.edit_text(f"❌ {result['description']}")
            except:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ {result['description']}"
                )
            return
            
        try:
            await progress_message.edit_text(f"📥 {audio_type}接收完成\n✅ {audio_type}分析完成\n💬 正在生成详细回复...")
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {audio_type}分析完成\n💬 正在生成详细回复..."
            )
        
        # 构建提示
        prompt = f"""以下是一个{audio_type}的分析（由Google Gemini 2.0 Flash模型生成）：

{audio_type}分析:
{result["description"]}

用户说明: {caption}

请根据上述{audio_type}分析和用户说明，详细回答用户的问题。如果用户没有特定问题，请对{audio_type}内容进行深入解读。如果分析结果表明无法处理或识别该音频，请礼貌地告知用户，并建议提供不同格式的音频。"""
        
        # 添加到用户上下文
        message = fp.ProtocolMessage(role="user", content=prompt)
        
        # 获取或创建用户上下文
        if user_id not in user_context:
            user_context[user_id] = {'messages': [message], 'bot_name': bot_names['claude35']}  # 音频处理默认使用Claude-3.5-Sonnet
        else:
            if user_context[user_id]['bot_name'] != bot_names['claude35']:
                # 临时记住原来的模型
                original_model = user_context[user_id]['bot_name']
                # 切换到Claude-3.5-Sonnet
                user_context[user_id]['bot_name'] = bot_names['claude35']
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"{audio_type}处理已临时切换到 {bot_names['claude35']} 模型"
                )
            user_context[user_id]['messages'].append(message)
        
        # 处理用户请求
        if user_id not in user_tasks or user_tasks[user_id].done():
            user_tasks[user_id] = asyncio.create_task(handle_user_request(user_id, update, context))
    else:
        # 处理音频失败
        try:
            await progress_message.edit_text(f"❌ 处理{audio_type}时出错: {result.get('description', '未知错误')}")
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ 处理{audio_type}时出错: {result.get('description', '未知错误')}"
            )

# 处理用户消息
async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    # 获取当前或默认模型
    current_model = default_bot_name
    if user_id in user_context:
        current_model = user_context[user_id]['bot_name']
    
    # 检查使用限制
    allow_request, daily_used, daily_limit = usage_stats.usage_stats.record_request(
        user_id=user_id, 
        model=current_model,
        is_image=False
    )
    
    if not allow_request:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"🚫 您今日的请求配额已用尽（{daily_used}/{daily_limit}）。请明天再试或联系管理员提高限制。"
        )
        return
    
    logging.info(f"开始处理用户 {user_id} 的请求 (今日第 {daily_used}/{daily_limit} 次请求)")
    user_input = update.message.text
    message = fp.ProtocolMessage(role="user", content=user_input)

    # 获取或创建用户上下文
    if user_id not in user_context:
        user_context[user_id] = {'messages': [message], 'bot_name': default_bot_name}
    else:
        user_context[user_id]['messages'].append(message)

    # 处理用户请求
    if user_id not in user_tasks or user_tasks[user_id].done():
        user_tasks[user_id] = asyncio.create_task(handle_user_request(user_id, update, context))

# 开始命令处理程序
async def start(update: Update, context):
    user_id = update.effective_user.id
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f"欢迎使用Poe AI助手! 请输入您的问题或发送图片。[基于Claude-3-Opus]\n您的用户ID是: {user_id}"
    )
    
    if user_id not in allowed_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，您没有权限使用此机器人。请联系管理员添加您的ID。"
        )

# 新对话命令处理程序
async def new_conversation(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    bot_name = default_bot_name
    if user_id in user_context:
        bot_name = user_context[user_id]['bot_name']
        user_context[user_id] = {'messages': [], 'bot_name': bot_name}
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"====== 新的对话开始（{bot_name}） ======")

# 切换到GPT-4
async def gpt4(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    bot_name = bot_names['gpt4']
    await switch_model(user_id, bot_name, update, context)

# 切换到Claude-3-Opus
async def claude3(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    bot_name = bot_names['claude3']
    await switch_model(user_id, bot_name, update, context)

# 切换到Claude-3.5-Sonnet
async def claude35(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    bot_name = bot_names['claude35']
    await switch_model(user_id, bot_name, update, context)

# 切换模型通用函数
async def switch_model(user_id, bot_name, update, context):
    if user_id not in user_context or user_context[user_id]['bot_name'] != bot_name:
        user_context[user_id] = {'messages': [], 'bot_name': bot_name}
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"已切换到 {bot_name} 模型,并清空上下文。")
        await new_conversation(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"当前已经是 {bot_name} 模型。")

# 添加用户到白名单
async def add_user(update: Update, context):
    user_id = update.effective_user.id
    
    # 只有管理员可以添加用户
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="⚠️ 只有管理员可以执行此命令。"
        )
        return
    
    # 检查是否提供了用户ID
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ 请提供要添加的用户ID，例如：/adduser 123456789"
        )
        return
    
    # 获取要添加的用户ID
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ 无效的用户ID。用户ID必须是数字。"
        )
        return
    
    # 检查用户是否已经在白名单中
    if target_user_id in allowed_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"ℹ️ 用户ID {target_user_id} 已在白名单中。"
        )
        return
    
    # 添加用户到白名单
    allowed_users.append(target_user_id)
    
    # 使用init_data.py脚本更新白名单
    try:
        # 运行脚本添加用户
        import subprocess
        result = subprocess.run(['python3', 'init_data.py', '--add', str(target_user_id)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            logging.info(f"已成功添加用户 {target_user_id} 到白名单并同步")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"✅ 已成功添加用户 {target_user_id} 到白名单。"
            )
        else:
            logging.error(f"添加用户时出错: {result.stderr}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"❌ 添加用户时出错: {result.stderr}"
            )
    except Exception as e:
        logging.error(f"调用init_data.py脚本时出错: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"❌ 同步白名单时出错: {str(e)}"
        )

# 从白名单中移除用户
async def remove_user(update: Update, context):
    user_id = update.effective_user.id
    
    # 只有管理员可以移除用户
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="⚠️ 只有管理员可以执行此命令。"
        )
        return
    
    # 检查是否提供了用户ID
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ 请提供要移除的用户ID，例如：/removeuser 123456789"
        )
        return
    
    # 获取要移除的用户ID
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ 无效的用户ID。用户ID必须是数字。"
        )
        return
    
    # 检查要移除的是否为管理员
    if target_user_id in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="⚠️ 不能移除管理员用户。"
        )
        return
    
    # 检查用户是否在白名单中
    if target_user_id not in allowed_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"ℹ️ 用户ID {target_user_id} 不在白名单中。"
        )
        return
    
    # 从白名单中移除用户
    allowed_users.remove(target_user_id)
    
    # 使用init_data.py脚本更新白名单
    try:
        # 运行脚本移除用户
        import subprocess
        result = subprocess.run(['python3', 'init_data.py', '--remove', str(target_user_id)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            logging.info(f"已成功从白名单移除用户 {target_user_id} 并同步")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"✅ 已成功从白名单移除用户 {target_user_id}。"
            )
        else:
            logging.error(f"移除用户时出错: {result.stderr}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"❌ 移除用户时出错: {result.stderr}"
            )
    except Exception as e:
        logging.error(f"调用init_data.py脚本时出错: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"❌ 同步白名单时出错: {str(e)}"
        )

# 列出所有允许的用户（仅管理员可用）
async def list_users(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 构建用户列表消息
    admin_id_list = ", ".join([str(id) for id in admin_users])
    user_id_list = ", ".join([str(id) for id in allowed_users if id not in admin_users])
    
    message = f"管理员列表: {admin_id_list}\n\n"
    if user_id_list:
        message += f"普通用户列表: {user_id_list}"
    else:
        message += "普通用户列表: 无"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=message
    )

# 查看个人使用统计
async def stats(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    # 获取用户统计数据
    user_stats = usage_stats.usage_stats.get_user_stats(user_id)
    
    # 构建统计消息
    today = datetime.now().strftime("%Y-%m-%d")
    
    message = f"📊 <b>您的使用统计</b>\n\n"
    message += f"📅 <b>今日使用情况</b>: {user_stats['today_used']}/{user_stats['daily_limit']} 次请求\n"
    message += f"📆 <b>本周使用总计</b>: {user_stats['week_total']} 次请求\n"
    message += f"🔢 <b>累计请求总数</b>: {user_stats['total_requests']} 次\n"
    message += f"🖼️ <b>图片处理总数</b>: {user_stats['image_requests']} 次\n\n"
    
    # 添加模型使用统计
    if user_stats['model_usage']:
        message += "<b>模型使用统计</b>:\n"
        for model, count in user_stats['model_usage'].items():
            percentage = (count / user_stats['total_requests']) * 100 if user_stats['total_requests'] > 0 else 0
            message += f"- {model}: {count} 次 ({percentage:.1f}%)\n"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        parse_mode="HTML"
    )

# 管理员查看所有用户使用统计
async def all_stats(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 获取所有用户统计数据
    all_users_stats = usage_stats.usage_stats.get_all_users_stats()
    
    if not all_users_stats:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="目前没有用户使用记录。"
        )
        return
    
    # 构建统计消息
    today = datetime.now().strftime("%Y-%m-%d")
    message = f"📊 <b>所有用户使用统计</b> (共 {len(all_users_stats)} 位用户)\n\n"
    
    # 添加前10位用户统计
    for i, user_stat in enumerate(all_users_stats[:10], 1):
        message += f"{i}. 用户 <code>{user_stat['user_id']}</code>\n"
        message += f"   - 今日: {user_stat['today_used']}/{user_stat['daily_limit']} 次\n"
        message += f"   - 总计: {user_stat['total_requests']} 次\n"
        message += f"   - 图片: {user_stat['image_requests']} 次\n"
    
    # 总体统计
    total_requests = sum(user['total_requests'] for user in all_users_stats)
    total_image_requests = sum(user['image_requests'] for user in all_users_stats)
    today_total = sum(user['today_used'] for user in all_users_stats)
    
    message += f"\n<b>总体统计</b>:\n"
    message += f"- 今日总请求: {today_total} 次\n"
    message += f"- 总请求数: {total_requests} 次\n"
    message += f"- 总图片请求: {total_image_requests} 次"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        parse_mode="HTML"
    )

# 设置用户使用限制
async def set_limit(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 检查参数
    if not context.args or len(context.args) != 2:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="请提供用户ID和限制次数，例如：/setlimit 12345678 100"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        limit = int(context.args[1])
        
        if limit < 1:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="限制次数必须大于0。"
            )
            return
            
        # 设置用户限制
        result = usage_stats.usage_stats.set_user_limit(target_user_id, limit)
        
        if result:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"已将用户 {target_user_id} 的每日限制设置为 {limit} 次。"
            )
            logging.info(f"管理员 {user_id} 将用户 {target_user_id} 的使用限制设为 {limit}")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="设置用户限制失败。"
            )
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="请提供有效的用户ID和限制次数。"
        )

# 重置用户今日使用量
async def reset_usage(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 检查参数
    if not context.args:
        # 重置所有用户
        usage_stats.usage_stats.reset_daily_usage()
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="已重置所有用户的今日使用量。"
        )
        logging.info(f"管理员 {user_id} 重置了所有用户的今日使用量")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # 重置特定用户
        result = usage_stats.usage_stats.reset_daily_usage(target_user_id)
        
        if result:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"已重置用户 {target_user_id} 的今日使用量。"
            )
            logging.info(f"管理员 {user_id} 重置了用户 {target_user_id} 的今日使用量")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="重置用户使用量失败。"
            )
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="请提供有效的用户ID。"
        )

def main():
    # 检查环境变量
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not telegram_token or not api_key:
        logging.error("请设置环境变量 TELEGRAM_BOT_TOKEN 和 POE_API_KEY")
        return
    
    # 检查Google API Key
    google_api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not google_api_key:
        logging.warning("未设置 GOOGLE_API_KEY 环境变量，图片识别功能将不可用")
    
    # 创建应用
    application = Application.builder().token(telegram_token).build()

    # 添加处理程序
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('new', new_conversation))
    application.add_handler(CommandHandler('gpt4', gpt4))
    application.add_handler(CommandHandler('claude3', claude3))
    application.add_handler(CommandHandler('claude35', claude35))
    application.add_handler(CommandHandler('adduser', add_user))
    application.add_handler(CommandHandler('removeuser', remove_user))
    application.add_handler(CommandHandler('listusers', list_users))
    
    # 添加使用统计相关命令
    application.add_handler(CommandHandler('stats', stats))  # 查看个人使用统计
    application.add_handler(CommandHandler('allstats', all_stats))  # 管理员查看所有用户统计
    application.add_handler(CommandHandler('setlimit', set_limit))  # 设置用户使用限制
    application.add_handler(CommandHandler('resetusage', reset_usage))  # 重置用户今日使用量
    
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))  # 添加图片处理
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))  # 添加视频处理
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))  # 添加音频处理
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 运行机器人
    logging.info("机器人已启动...")
    application.run_polling()

if __name__ == '__main__':
    main() 