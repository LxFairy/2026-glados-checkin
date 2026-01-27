#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 GLaDOS 自动签到
- 极致钉钉 Markdown 美化
- 账户隐私脱敏
- 智能积分变化高亮
"""

import requests
import json
import os
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta, timezone

# 解决环境编码问题
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 极客配置 =================
DOMAINS = ["https://glados.cloud", "https://glados.rocks", "https://glados.network"]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
}

def get_beijing_time():
    """获取精准的北京时间 (UTC+8)"""
    return datetime.now(timezone(timedelta(hours=8)))

def log(msg):
    ts = get_beijing_time().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ================= 信息中枢模块 =================

def get_geek_daily():
    """构建专属信息中枢：一言 + 天气"""
    report = "\n---\n#### 📰 极客早报\n"
    
    # 1. 每日一言 (Hitokoto)
    try:
        res = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=5).json()
        report += f"> “{res['hitokoto']}” —— *{res['from']}*\n\n"
    except:
        report += "> “代码即诗，逻辑即美。”\n\n"
    
    # 2. 实时天气 (wttr.in 极客源)
    try:
        # 自动定位，使用简洁的 format=3
        weather = requests.get("https://wttr.in/?format=3&lang=zh-cn", timeout=5).text
        report += f"🌡️ **实时天气**: `{weather.strip()}`\n"
    except:
        log("⚠️ 天气接口请求超时")
        
    return report

# ================= 核心逻辑模块 =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.email = "?"
        self.left_days = 0
        self.points = 0
        self.points_change = "?"
        self.last_msg = ""

    def req(self, method, path, data=None):
        for d in DOMAINS:
            try:
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
                if method == 'GET':
                    resp = requests.get(f"{d}{path}", headers=h, timeout=10)
                else:
                    resp = requests.post(f"{d}{path}", headers=h, json=data, timeout=10)
                if resp.status_code == 200: return resp.json()
            except: continue
        return None

    def get_status(self):
        res = self.req('GET', '/api/user/status')
        if res and 'data' in res:
            self.email = res['data'].get('email', 'Unknown')
            # 兼容处理天数
            self.left_days = int(float(res['data'].get('leftDays', 0)))
            return True
        return False

    def get_points(self):
        res = self.req('GET', '/api/user/points')
        if res and 'points' in res:
            self.points = int(float(res['points']))
            history = res.get('history', [])
            if history:
                change = str(history[0].get('change', '0')).split('.')[0]
                self.points_change = f"+{change}" if not change.startswith('-') else change
            return True
        return False

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 推送引擎 =================

def push_dingtalk(webhook, secret, title, results_objs):
    if not webhook: return
    
    # 签名逻辑
    timestamp = str(round(time.time() * 1000))
    url = webhook
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"

    md_text = f"## 🚀 {title} \n\n"
    
    for g in results_objs:
        # 1. 账号掩码
        email_parts = g.email.split('@')
        masked = f"{email_parts[0][:3]}***{email_parts[0][-2:]}@{email_parts[1]}"
        
        # 2. 决策参考：预测到期日期
        expire_date = (get_beijing_time() + timedelta(days=g.left_days)).strftime('%Y-%m-%d')
        
        # 3. 智能库存预警
        if g.left_days < 7:
            warning_label = " <font color='#e74c3c'>⚠️ 库存紧张</font>"
            status_desc = "请尽快登录官网手动兑换"
        else:
            warning_label = " <font color='#27ae60'>✅ 储备充足</font>"
            status_desc = "资产状态良好"
        
        status_icon = "🟢" if "Success" in g.last_msg or "Repeats" in g.last_msg else "🔴"
        change_color = "#27ae60" if "+" in g.points_change else "#e74c3c"

        md_text += f"#### 👤 账号: `{masked}`\n"
        md_text += f"> **决策参考报告**\n"
        md_text += f"> - 💰 **当前积分**: `{g.points}` <font color='{change_color}'>({g.points_change})</font>\n"
        md_text += f"> - ⏳ **可用天数**: `{g.left_days}` 天 {warning_label}\n"
        md_text += f"> - 📅 **断粮日期**: `{expire_date}`\n"
        md_text += f"> - {status_icon} **签到结果**: {g.last_msg}\n"
        md_text += f"> - 💡 **策略建议**: {status_desc}\n\n"

    # 4. 注入极客信息中枢
    md_text += get_geek_daily()
    
    # 5. 任务底栏
    bj_now = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
    md_text += f"\n---\n<font color='#999999' size='2'>🕒 信息中枢更新于: {bj_now}</font>"

    data = {"msgtype": "markdown", "markdown": {"title": "GLaDOS 极客日报", "text": md_text}}
    try:
        requests.post(url, json=data, timeout=10)
        log("✅ 极客情报推送成功")
    except Exception as e:
        log(f"⚠️ 推送失败: {e}")

# ================= 流程控制 =================

def main():
    log("🚀 GLaDOS 极客情报系统启动...")
    
    raw_cookie = os.environ.get("GLADOS_COOKIE", "")
    if not raw_cookie:
        log("❌ 缺失 GLADOS_COOKIE 环境变量")
        sys.exit(1)
        
    cookies = [c.strip() for c in raw_cookie.split('\n') if c.strip()]
    results_objs = []
    success_cnt = 0
    
    for cookie in cookies:
        g = GLaDOS(cookie)
        # 签到
        checkin_res = g.checkin()
        g.last_msg = checkin_res.get('message', 'Network Error') if checkin_res else "Net Error"
        # 抓取资产
        g.get_status()
        g.get_points()
        
        if "Success" in g.last_msg or "Repeats" in g.last_msg:
            success_cnt += 1
        results_objs.append(g)

    # 推送
    d_webhook = os.environ.get("DINGTALK_WEBHOOK")
    d_secret = os.environ.get("DINGTALK_SECRET")
    title = f"GLaDOS 情报摘要: {success_cnt}/{len(cookies)}"
    push_dingtalk(d_webhook, d_secret, title, results_objs)

if __name__ == '__main__':
    main()
