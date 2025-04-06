# Poe Telegram Bot

一个强大的Telegram机器人，集成了Poe API和Google Gemini图像识别功能，支持多种AI模型。

## 功能特点

- 支持多种AI模型：GPT-4、Claude-3-Opus和Claude-3.5-Sonnet
- 支持图片分析：使用Google Gemini 2.0 Flash模型识别图片内容
- 支持用户白名单管理：限制机器人使用权限
- 支持会话上下文管理：记住对话历史
- 支持命令菜单：便捷访问机器人功能

## 安装步骤

### 前提条件

- Docker和Docker Compose
- Telegram Bot Token（从BotFather获取）
- Poe API Key（从Poe网站获取）
- Google Gemini API Key（从Google AI Studio获取）

### 安装过程

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/poe-telegram-bot.git
cd poe-telegram-bot
```

2. 配置环境变量：

复制`.env.example`文件为`.env`并填入你的API密钥：

```bash
cp .env.example .env
# 编辑.env文件
```

或者直接在`docker-compose.yml`文件中填入相应的API密钥。

3. 构建并启动Docker容器：

```bash
docker compose up -d
```

## 使用方法

### 基本命令

- `/start` - 开始与机器人对话
- `/new` - 开始一个新的对话，清空上下文
- `/gpt4` - 切换到GPT-4模型
- `/claude3` - 切换到Claude-3-Opus模型
- `/claude35` - 切换到Claude-3.5-Sonnet模型

### 管理员命令

- `/adduser <用户ID>` - 添加用户到白名单
- `/removeuser <用户ID>` - 从白名单移除用户
- `/listusers` - 列出所有允许的用户

### 图片处理功能

直接发送图片给机器人，系统将使用Google Gemini 2.0 Flash模型分析图片内容，然后将分析结果和图片的部分base64编码发送给Claude-3.5-Sonnet处理。

您可以在发送图片时添加说明文字，指定您想了解的图片方面。

## 配置说明

在`docker-compose.yml`文件中，可以设置以下环境变量：

- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token
- `POE_API_KEY`: Poe API Key
- `GOOGLE_API_KEY`: Google Gemini API Key
- `ADMIN_USERS`: 管理员用户ID列表（逗号分隔）
- `ALLOWED_USERS`: 允许使用机器人的普通用户ID列表（逗号分隔）

## 贡献指南

欢迎提交Pull Request或Issue来改进此项目。

## 许可证

MIT

## 免责声明

本项目仅供学习和研究使用，请遵循相关API的使用条款。 