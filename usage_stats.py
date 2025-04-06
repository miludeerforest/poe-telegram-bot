import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 文件路径
STATS_FILE = "user_stats.json"

# 默认使用限制
DEFAULT_DAILY_LIMIT = 50  # 每日默认请求数量限制
DEFAULT_ADMIN_DAILY_LIMIT = 200  # 管理员每日默认请求数量限制

# 用户使用统计
class UsageStats:
    def __init__(self):
        self.stats = {}
        self.daily_limits = {}
        self.load_stats()
    
    def load_stats(self):
        """从文件加载统计数据"""
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, 'r') as f:
                    data = json.load(f)
                    self.stats = data.get('stats', {})
                    self.daily_limits = data.get('daily_limits', {})
                    logging.info(f"已加载用户统计数据，共 {len(self.stats)} 个用户记录")
            except Exception as e:
                logging.error(f"加载用户统计数据时出错: {e}")
                self.stats = {}
                self.daily_limits = {}
        else:
            self.stats = {}
            self.daily_limits = {}
            logging.info("未找到统计数据文件，已创建新的统计记录")
    
    def save_stats(self):
        """保存统计数据到文件"""
        data = {
            'stats': self.stats,
            'daily_limits': self.daily_limits
        }
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"保存用户统计数据时出错: {e}")
    
    def record_request(self, user_id: int, model: str, is_image: bool = False) -> Tuple[bool, int, int]:
        """
        记录用户请求并检查是否超过限制
        
        返回: 
            Tuple[bool, int, int] - (是否允许请求, 今日已用次数, 每日限制)
        """
        user_id = str(user_id)  # 转换为字符串作为键
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 初始化用户记录
        if user_id not in self.stats:
            self.stats[user_id] = {
                "total_requests": 0,
                "image_requests": 0,
                "model_usage": {},
                "daily_usage": {}
            }
        
        # 获取或设置用户限制
        daily_limit = self.get_user_limit(user_id)
        
        # 初始化今日使用记录
        if today not in self.stats[user_id]["daily_usage"]:
            self.stats[user_id]["daily_usage"][today] = 0
        
        # 检查是否超过每日限制
        daily_used = self.stats[user_id]["daily_usage"][today]
        if daily_used >= daily_limit:
            return False, daily_used, daily_limit
        
        # 记录请求
        self.stats[user_id]["total_requests"] += 1
        self.stats[user_id]["daily_usage"][today] += 1
        
        # 记录图片请求
        if is_image:
            self.stats[user_id]["image_requests"] += 1
        
        # 记录模型使用
        if model not in self.stats[user_id]["model_usage"]:
            self.stats[user_id]["model_usage"][model] = 0
        self.stats[user_id]["model_usage"][model] += 1
        
        # 清理旧数据(保留30天)
        self._cleanup_old_data(user_id)
        
        # 保存统计数据
        self.save_stats()
        
        return True, daily_used + 1, daily_limit
    
    def _cleanup_old_data(self, user_id: str):
        """清理30天前的数据"""
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        daily_usage = self.stats[user_id]["daily_usage"]
        
        # 创建一个新的日期使用字典，只包含30天内的数据
        new_daily_usage = {
            date: count for date, count in daily_usage.items()
            if date >= cutoff_date
        }
        
        self.stats[user_id]["daily_usage"] = new_daily_usage
    
    def get_user_stats(self, user_id: int) -> Dict:
        """获取用户统计数据"""
        user_id = str(user_id)
        
        if user_id not in self.stats:
            return {
                "total_requests": 0,
                "image_requests": 0,
                "model_usage": {},
                "daily_usage": {},
                "daily_limit": self.get_user_limit(user_id)
            }
        
        stats = self.stats[user_id].copy()
        stats["daily_limit"] = self.get_user_limit(user_id)
        
        # 获取今日使用量
        today = datetime.now().strftime("%Y-%m-%d")
        stats["today_used"] = stats["daily_usage"].get(today, 0)
        
        # 计算过去7天的使用量
        week_total = 0
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            week_total += stats["daily_usage"].get(date, 0)
        stats["week_total"] = week_total
        
        return stats
    
    def get_all_users_stats(self) -> List[Dict]:
        """获取所有用户的统计数据"""
        result = []
        for user_id in self.stats:
            user_stats = self.get_user_stats(int(user_id))
            user_stats["user_id"] = user_id
            result.append(user_stats)
        
        # 按总请求量排序
        result.sort(key=lambda x: x["total_requests"], reverse=True)
        return result
    
    def set_user_limit(self, user_id: int, limit: int) -> bool:
        """设置用户每日限制"""
        user_id = str(user_id)
        if limit < 1:
            return False
        
        self.daily_limits[user_id] = limit
        self.save_stats()
        return True
    
    def get_user_limit(self, user_id: str) -> int:
        """获取用户每日限制"""
        # 检查是否有特定用户设置
        if user_id in self.daily_limits:
            return self.daily_limits[user_id]
        
        # 如果是管理员，使用管理员默认限制
        admin_users_str = os.environ.get("ADMIN_USERS", "")
        admin_users = list(map(str, admin_users_str.split(',')))
        if user_id in admin_users:
            return DEFAULT_ADMIN_DAILY_LIMIT
        
        # 其他用户使用默认限制
        return DEFAULT_DAILY_LIMIT
    
    def reset_daily_usage(self, user_id: Optional[int] = None) -> bool:
        """重置用户今日使用量"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if user_id is not None:
            # 重置特定用户
            user_id = str(user_id)
            if user_id in self.stats:
                self.stats[user_id]["daily_usage"][today] = 0
                self.save_stats()
            return True
        else:
            # 重置所有用户
            for uid in self.stats:
                if today in self.stats[uid]["daily_usage"]:
                    self.stats[uid]["daily_usage"][today] = 0
            self.save_stats()
            return True

# 创建全局实例
usage_stats = UsageStats() 