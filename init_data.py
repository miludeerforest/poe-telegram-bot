#!/usr/bin/env python3
import os
import json
import logging
from usage_stats import UsageStats, STATS_FILE, DATA_DIR

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_env_variables():
    """从.env文件加载环境变量"""
    env_vars = {}
    try:
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key] = value
        return env_vars
    except Exception as e:
        logging.error(f"从.env文件加载环境变量时出错: {e}")
        return {}

def init_data():
    """初始化用户数据"""
    logging.info("开始初始化用户数据...")
    
    # 数据文件路径
    data_export_file = os.path.join(DATA_DIR, "users_backup.json")
    
    # 确保数据目录存在
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
            logging.info(f"已创建数据目录: {DATA_DIR}")
        except Exception as e:
            logging.error(f"创建数据目录时出错: {e}")
    
    # 获取当前环境变量中的用户
    env_vars = load_env_variables()
    admin_users_str = env_vars.get("ADMIN_USERS", "")
    allowed_users_str = env_vars.get("ALLOWED_USERS", "")
    
    # 转换为列表
    if admin_users_str:
        admin_users = list(map(int, admin_users_str.split(',')))
    else:
        admin_users = []
    
    if allowed_users_str:
        allowed_users = list(map(int, allowed_users_str.split(',')))
    else:
        allowed_users = []
    
    # 确保管理员在白名单中
    for admin_id in admin_users:
        if admin_id not in allowed_users:
            allowed_users.append(admin_id)
    
    # 读取用户统计数据
    stats = UsageStats()
    
    # 如果有备份文件，尝试导入
    if os.path.exists(data_export_file):
        try:
            logging.info(f"发现备份文件: {data_export_file}")
            with open(data_export_file, "r") as f:
                data = json.load(f)
                
                backup_allowed_users = data.get("allowed_users", [])
                backup_user_limits = data.get("user_limits", {})
                
                # 合并允许的用户
                for user_id in backup_allowed_users:
                    if user_id not in allowed_users:
                        allowed_users.append(user_id)
                
                # 设置用户限制
                for user_id, limit in backup_user_limits.items():
                    stats.set_user_limit(int(user_id), int(limit))
                
                logging.info(f"已从备份导入 {len(backup_allowed_users)} 个用户和 {len(backup_user_limits)} 个用户限制")
        except Exception as e:
            logging.error(f"导入备份数据时出错: {e}")
    
    # 更新.env文件中的ALLOWED_USERS
    if allowed_users:
        try:
            # 读取当前.env文件
            env_content = []
            with open(".env", "r") as f:
                env_content = f.readlines()
            
            # 更新ALLOWED_USERS行
            allowed_users_str = ",".join(map(str, allowed_users))
            updated = False
            for i, line in enumerate(env_content):
                if line.startswith("ALLOWED_USERS="):
                    env_content[i] = f"ALLOWED_USERS={allowed_users_str}\n"
                    updated = True
                    break
            
            # 如果没有找到ALLOWED_USERS行，添加一行
            if not updated:
                env_content.append(f"ALLOWED_USERS={allowed_users_str}\n")
            
            # 写回.env文件
            with open(".env", "w") as f:
                f.writelines(env_content)
            
            logging.info(f"已更新.env文件中的ALLOWED_USERS: {allowed_users_str}")
        except Exception as e:
            logging.error(f"更新.env文件时出错: {e}")
    
    # 保存当前的用户数据作为备份
    try:
        export_data = {
            "allowed_users": allowed_users,
            "user_limits": stats.daily_limits
        }
        
        with open(data_export_file, "w") as f:
            json.dump(export_data, f, indent=2)
        
        logging.info(f"已保存当前用户数据到备份文件: {data_export_file}")
    except Exception as e:
        logging.error(f"保存备份数据时出错: {e}")
    
    logging.info("用户数据初始化完成")

if __name__ == "__main__":
    init_data() 