FROM python:3.9-slim

WORKDIR /app

COPY . /app/

RUN pip install --no-cache-dir -r requirements.txt

# 创建启动脚本
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'echo "🔄 初始化用户数据..."' >> /app/start.sh && \
    echo 'python init_data.py' >> /app/start.sh && \
    echo 'echo "🔄 设置机器人命令..."' >> /app/start.sh && \
    echo 'python set_commands.py' >> /app/start.sh && \
    echo 'echo "✅ 启动机器人..."' >> /app/start.sh && \
    echo 'python main.py' >> /app/start.sh && \
    chmod +x /app/start.sh

# 使用启动脚本作为入口点
CMD ["/app/start.sh"] 