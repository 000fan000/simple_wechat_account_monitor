"""
定时任务调度模块
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from threading import Lock
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

TASKS_FILE = "data/tasks.json"
_next_job_id = 0
_tasks_data: List[Dict] = []
_lock = Lock()
_scheduler: Optional[AsyncIOScheduler] = None
_run_callback = None


def _load():
    global _tasks_data
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            _tasks_data = json.load(f)
    else:
        _tasks_data = []


def _save():
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(_tasks_data, f, ensure_ascii=False, indent=2)


def _cron_to_readable(cron: str) -> str:
    parts = cron.strip().split()
    if len(parts) != 5:
        return cron
    minute, hour, day, month, week = parts
    if minute == '0' and hour != '*' and day == '*' and month == '*' and week == '*':
        return f"每天 {hour}:00"
    if minute == '0' and hour != '*' and day != '*' and month == '*' and week == '*':
        return f"每月{day}日 {hour}:00"
    return cron


def init(callback=None):
    global _scheduler, _run_callback
    _load()
    _run_callback = callback
    _scheduler = AsyncIOScheduler()
    _reschedule_all()


def start():
    if _scheduler:
        _scheduler.start()


def shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)


def _reschedule_all():
    if _scheduler is None:
        return
    for job in list(_scheduler.get_jobs()):
        job.remove()
    for task in _tasks_data:
        if task.get('enabled') and task.get('cron'):
            _add_job(task)


def _add_job(task: Dict):
    global _next_job_id
    if _scheduler is None:
        return
    try:
        trigger = CronTrigger.from_crontab(task['cron'])
        job_id = f"task_{task.get('fakeid', _next_job_id)}"
        _next_job_id += 1
        _scheduler.add_job(
            _execute_task, trigger, args=[task],
            id=job_id, replace_existing=True,
            name=task.get('mp_name', 'unknown')
        )
    except Exception:
        pass


def _execute_task(task: Dict):
    fakeid = task.get('fakeid', '')
    mp_name = task.get('mp_name', '')
    max_pages = task.get('max_pages', 3)
    _update_task_status(fakeid, 'running', '')
    if _run_callback:
        success, count, msg = _run_callback(fakeid, mp_name, max_pages)
        _update_task_status(fakeid, 'success' if success else 'error', msg, count)
    else:
        _update_task_status(fakeid, 'error', '调度器未初始化')


def _update_task_status(fakeid: str, status: str, msg: str = '', count: int = 0):
    with _lock:
        for task in _tasks_data:
            if task.get('fakeid') == fakeid:
                task['last_run'] = datetime.now().isoformat()
                task['last_status'] = status
                task['last_msg'] = msg
                task['last_count'] = count
                break
        _save()


def get_all_tasks() -> List[Dict]:
    with _lock:
        tasks = []
        for t in _tasks_data:
            t2 = dict(t)
            t2['next_run'] = _get_next_run(t2.get('fakeid', ''))
            t2['cron_readable'] = _cron_to_readable(t2.get('cron', ''))
            tasks.append(t2)
        return tasks


def save_task(task: Dict) -> Dict:
    with _lock:
        fakeid = task.get('fakeid', '')
        for i, t in enumerate(_tasks_data):
            if t.get('fakeid') == fakeid:
                _tasks_data[i].update(task)
                break
        else:
            _tasks_data.append(task)
        _save()
    if _scheduler:
        _reschedule_all()
    return task


def delete_task(fakeid: str) -> bool:
    with _lock:
        before = len(_tasks_data)
        _tasks_data[:] = [t for t in _tasks_data if t.get('fakeid') != fakeid]
        if len(_tasks_data) < before:
            _save()
            if _scheduler:
                _reschedule_all()
            return True
    return False


def _get_next_run(fakeid: str) -> Optional[str]:
    if _scheduler is None:
        return None
    job_id = f"task_{fakeid}"
    job = _scheduler.get_job(job_id)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
