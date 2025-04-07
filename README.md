# Poe Telegram Bot 与 Gemini Vision 集成

一个强大的 Telegram 机器人，集成了 Poe API 和 Google Gemini 图像识别，支持多种 AI 模型。

## 功能特点

- 支持多种 AI 模型：GPT-4、Claude-3-Opus 和 Claude-3.5-Sonnet
- 图像分析：使用 Google Gemini 2.0 Flash 模型进行图像识别
- 视频分析：使用 Google Gemini 2.0 Flash 模型分析视频内容
- 音频分析：使用 Google Gemini 2.0 Flash 模型分析音频内容
- 用户白名单管理：限制机器人使用权限
- 使用统计和限制：监控和控制用户请求配额
- 会话上下文管理：记住对话历史
- 命令菜单：轻松访问机器人功能

## 安装说明

### 前提条件

- Docker 和 Docker Compose
- Telegram Bot Token（从 BotFather 获取）
- Poe API Key（从 Poe 网站获取）
- Google Gemini API Key（从 Google AI Studio 获取）

### 安装过程

1. 克隆仓库：

```bash
git clone https://github.com/miludeerforest/poe-telegram-bot.git
cd poe-telegram-bot
```

2. 配置环境变量：

复制 `.env.example` 文件到 `.env` 并填写您的 API 密钥：

```bash
cp .env.example .env
# 编辑 .env 文件
```

或者直接在 `docker-compose.yml` 文件中填写相应的 API 密钥。

3. 构建并启动 Docker 容器：

```bash
docker compose up -d
```

## 使用说明

### 基本命令

- `/start` - 开始与机器人聊天
- `/new` - 开始新对话，清除上下文
- `/gpt4` - 切换到 GPT-4 模型
- `/claude3` - 切换到 Claude-3-Opus 模型
- `/claude35` - 切换到 Claude-3.5-Sonnet 模型
- `/stats` - 查看您的使用统计

### 管理员命令

- `/adduser <用户ID>` - 将用户添加到白名单
- `/removeuser <用户ID>` - 从白名单中移除用户
- `/listusers` - 列出所有允许的用户
- `/allstats` - 查看所有用户的使用统计
- `/setlimit <用户ID> <限制>` - 设置用户的每日使用限制
- `/resetusage [用户ID]` - 重置每日使用计数（针对所有用户或特定用户）

### 多媒体处理功能

1. **图片处理**：
直接发送图片给机器人，系统将使用 Google Gemini 2.0 Flash 模型分析图片内容，然后将分析结果和图片部分 base64 编码发送给 Claude-3.5-Sonnet 处理。

2. **视频处理**：
发送视频文件给机器人，系统将使用 Google Gemini 2.0 Flash 模型分析视频内容，然后将分析结果发送给 Claude-3.5-Sonnet 进行进一步处理。

3. **音频处理**：
发送语音消息或音频文件给机器人，系统将使用 Google Gemini 2.0 Flash 模型分析音频内容，然后将分析结果发送给 Claude-3.5-Sonnet 进行进一步处理。

您可以在发送多媒体文件时添加说明文字，指明您希望了解的具体方面。所有分析将以中文进行。

### 使用统计和限制

机器人会跟踪每个用户的使用统计并强制执行每日请求限制：
- 普通用户：每天 50 个请求
- 管理员用户：每天 200 个请求
- 管理员可以为每个用户设置自定义限制

跟踪的统计数据包括：
- 每日使用计数
- 总请求计数
- 图像处理计数
- 模型使用分布
- 每周使用摘要

## 配置说明

在 `docker-compose.yml` 文件中，您可以设置以下环境变量：

- `TELEGRAM_BOT_TOKEN`：Telegram 机器人令牌
- `POE_API_KEY`：Poe API 密钥
- `GOOGLE_API_KEY`：Google Gemini API 密钥
- `ADMIN_USERS`：管理员用户 ID 列表（逗号分隔）
- `ALLOWED_USERS`：允许使用机器人的普通用户 ID 列表（逗号分隔）

## 贡献指南

欢迎提交 Pull Requests 或 Issues 来改进此项目。

## 许可证

MIT

## 免责声明

此项目仅用于学习和研究目的。请遵守相应 API 的使用条款。 