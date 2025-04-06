import asyncio
import fastapi_poe as fp
from telegram import Update, constants, BotCommand
from telegram.ext import Application, MessageHandler, filters, CommandHandler
import logging
import os
import image_handler

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
    
    logging.info(f"开始处理用户 {user_id} 的图片请求")
    
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

# 处理用户消息
async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查用户是否有权限
    if not check_user_permission(user_id, update, context):
        return
    
    logging.info(f"开始处理用户 {user_id} 的请求")
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

# 添加用户命令处理程序（仅管理员可用）
async def add_user(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 获取要添加的用户ID
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="请提供要添加的用户ID，例如：/adduser 12345678"
        )
        return
    
    try:
        new_user_id = int(context.args[0])
        if new_user_id in allowed_users:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"用户ID {new_user_id} 已在白名单中。"
            )
        else:
            allowed_users.append(new_user_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"已将用户ID {new_user_id} 添加到白名单。"
            )
            logging.info(f"管理员 {user_id} 添加了用户 {new_user_id} 到白名单")
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="无效的用户ID，请提供有效的数字ID。"
        )

# 移除用户命令处理程序（仅管理员可用）
async def remove_user(update: Update, context):
    user_id = update.effective_user.id
    
    # 检查是否为管理员
    if user_id not in admin_users:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="抱歉，只有管理员可以使用此命令。"
        )
        return
    
    # 获取要移除的用户ID
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="请提供要移除的用户ID，例如：/removeuser 12345678"
        )
        return
    
    try:
        remove_user_id = int(context.args[0])
        # 不允许移除管理员
        if remove_user_id in admin_users:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"无法移除管理员用户ID {remove_user_id}。"
            )
        elif remove_user_id in allowed_users:
            allowed_users.remove(remove_user_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"已将用户ID {remove_user_id} 从白名单中移除。"
            )
            logging.info(f"管理员 {user_id} 从白名单中移除了用户 {remove_user_id}")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"用户ID {remove_user_id} 不在白名单中。"
            )
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="无效的用户ID，请提供有效的数字ID。"
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
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))  # 添加图片处理
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 运行机器人
    logging.info("机器人已启动...")
    application.run_polling()

if __name__ == '__main__':
    main() 