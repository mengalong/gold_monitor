from database import init_db
from collectors import run_daily_update
from analytics import build_score
from config import ensure_valid_settings
from advice import refresh_and_save_advice

if __name__ == "__main__":
    ensure_valid_settings()
    init_db()
    print("开始更新黄金市场数据……")
    result = run_daily_update()
    for name, message in result.items():
        print(f"{name}: {message}")
    score = build_score()
    print("评分：", score)
    advice, _, _ = refresh_and_save_advice()
    print("建议：", advice.to_dict())
