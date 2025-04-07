#!/usr/bin/env python3
import os
import json
import logging
import argparse
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

def update_env_file(allowed_users):
    """更新.env文件中的ALLOWED_USERS"""
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
        return True
    except Exception as e:
        logging.error(f"更新.env文件时出错: {e}")
        return False

def backup_data():
    """备份用户数据"""
    try:
        if os.path.exists(STATS_FILE):
            backup_file = f"{STATS_FILE}.backup"
            with open(STATS_FILE, "r") as src:
                with open(backup_file, "w") as dst:
                    dst.write(src.read())
            logging.info(f"已备份用户数据到 {backup_file}")
            return True
        else:
            logging.warning(f"找不到用户数据文件 {STATS_FILE}")
            return False
    except Exception as e:
        logging.error(f"备份用户数据时出错: {e}")
        return False

def import_allowed_users(allowed_users_file):
    """从文件导入允许的用户列表"""
    try:
        with open(allowed_users_file, "r") as f:
            data = json.load(f)
            allowed_users = data.get("allowed_users", [])
            
            # 确保都是整数
            allowed_users = [int(user_id) for user_id in allowed_users]
            
            # 获取当前管理员列表
            env_vars = load_env_variables()
            admin_users_str = env_vars.get("ADMIN_USERS", "")
            admin_users = list(map(int, admin_users_str.split(',') if admin_users_str else []))
            
            # 确保管理员在白名单中
            for admin_id in admin_users:
                if admin_id not in allowed_users:
                    allowed_users.append(admin_id)
            
            # 更新.env文件
            update_env_file(allowed_users)
            
            logging.info(f"已导入 {len(allowed_users)} 个允许的用户")
            return True
    except Exception as e:
        logging.error(f"导入允许的用户列表时出错: {e}")
        return False

def import_user_limits(limits_file):
    """从文件导入用户使用限制"""
    try:
        stats = UsageStats()
        
        with open(limits_file, "r") as f:
            data = json.load(f)
            user_limits = data.get("user_limits", {})
            
            # 设置每个用户的限制
            for user_id, limit in user_limits.items():
                stats.set_user_limit(int(user_id), int(limit))
            
            logging.info(f"已导入 {len(user_limits)} 个用户的使用限制")
            return True
    except Exception as e:
        logging.error(f"导入用户使用限制时出错: {e}")
        return False

def export_user_data(output_file):
    """导出用户数据（白名单和使用限制）"""
    try:
        stats = UsageStats()
        
        # 获取白名单用户
        env_vars = load_env_variables()
        allowed_users_str = env_vars.get("ALLOWED_USERS", "")
        if allowed_users_str:
            allowed_users = list(map(int, allowed_users_str.split(',')))
        else:
            allowed_users = []
        
        # 导出数据
        export_data = {
            "allowed_users": allowed_users,
            "user_limits": stats.daily_limits
        }
        
        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2)
        
        logging.info(f"已导出用户数据到 {output_file}")
        return True
    except Exception as e:
        logging.error(f"导出用户数据时出错: {e}")
        return False

def list_user_data():
    """列出所有用户数据"""
    try:
        stats = UsageStats()
        
        # 获取环境变量
        env_vars = load_env_variables()
        
        # 获取白名单用户
        allowed_users_str = env_vars.get("ALLOWED_USERS", "")
        if allowed_users_str:
            allowed_users = list(map(int, allowed_users_str.split(',')))
        else:
            allowed_users = []
        
        # 获取管理员用户
        admin_users_str = env_vars.get("ADMIN_USERS", "")
        if admin_users_str:
            admin_users = list(map(int, admin_users_str.split(',')))
        else:
            admin_users = []
        
        print("\n=== 用户数据摘要 ===")
        print(f"管理员数量: {len(admin_users)}")
        print(f"白名单用户数量: {len(allowed_users)}")
        print(f"统计用户数量: {len(stats.stats)}")
        print(f"自定义限制用户数量: {len(stats.daily_limits)}")
        
        # 列出管理员
        print("\n=== 管理员用户 ===")
        for admin_id in admin_users:
            print(f"管理员ID: {admin_id}")
        
        # 列出白名单用户和限制
        print("\n=== 白名单用户及限制 ===")
        for user_id in allowed_users:
            user_limit = stats.get_user_limit(str(user_id))
            user_stats = stats.get_user_stats(user_id)
            print(f"用户ID: {user_id}, 使用限制: {user_limit}, 总请求: {user_stats.get('total_requests', 0)}, 今日使用: {user_stats.get('today_used', 0)}")
        
        return True
    except Exception as e:
        logging.error(f"列出用户数据时出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="用户数据管理工具")
    
    # 创建子命令
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 备份命令
    backup_parser = subparsers.add_parser("backup", help="备份用户数据")
    
    # 导入白名单命令
    import_users_parser = subparsers.add_parser("import-users", help="导入允许的用户列表")
    import_users_parser.add_argument("file", help="包含允许用户的JSON文件")
    
    # 导入使用限制命令
    import_limits_parser = subparsers.add_parser("import-limits", help="导入用户使用限制")
    import_limits_parser.add_argument("file", help="包含用户限制的JSON文件")
    
    # 导出用户数据命令
    export_parser = subparsers.add_parser("export", help="导出用户数据")
    export_parser.add_argument("--output", "-o", default="user_data_export.json", help="输出文件名")
    
    # 列出用户数据命令
    list_parser = subparsers.add_parser("list", help="列出所有用户数据")
    
    # 解析参数
    args = parser.parse_args()
    
    # 处理命令
    if args.command == "backup":
        backup_data()
    elif args.command == "import-users":
        import_allowed_users(args.file)
    elif args.command == "import-limits":
        import_user_limits(args.file)
    elif args.command == "export":
        export_user_data(args.output)
    elif args.command == "list":
        list_user_data()
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 