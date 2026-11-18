from database import init_db
from collectors import run_daily_update
from analytics import build_score

if __name__ == "__main__":
    init_db()
    print("开始更新黄金市场数据……")
    result = run_daily_update()
    for name, message in result.items():
        print(f"{name}: {message}")
    score = build_score()
    print("评分：", score)
