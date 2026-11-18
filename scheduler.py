"""常驻定时任务：每天08:00更新数据，每周六09:00生成周报。"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from database import init_db
from collectors import run_daily_update
from analytics import build_score
from reporting import generate_weekly_report
from config import REPORTS_DIR, TIMEZONE, ensure_valid_settings

def daily_job():
    print("开始执行每日黄金数据更新")
    result = run_daily_update()
    for name, message in result.items():
        print(f"{name}: {message}")
    print("评分：", build_score())

def weekly_job():
    print("开始生成每周黄金市场报告")
    report = generate_weekly_report()
    path = REPORTS_DIR / "gold_weekly_report_latest.md"
    path.write_text(report, encoding="utf-8")
    dated = REPORTS_DIR / f"gold_weekly_report_{__import__('datetime').date.today().isoformat()}.md"
    dated.write_text(report, encoding="utf-8")
    print(f"周报已保存：{path}")

if __name__ == "__main__":
    ensure_valid_settings()
    init_db()
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(daily_job, CronTrigger(hour=8, minute=0), id="daily_update", max_instances=1, coalesce=True)
    scheduler.add_job(weekly_job, CronTrigger(day_of_week="sat", hour=9, minute=0), id="weekly_report", max_instances=1, coalesce=True)
    print(f"定时服务已启动，时区：{TIMEZONE}")
    scheduler.start()
