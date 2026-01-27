#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLaDOS 乔布斯禅意对齐版 v2.2
- 深度优化：解决 Markdown 进度条对齐错位问题
- 视觉规范：采用垂直引用块布局，确保 UI 纵向一致性
- 核心功能：断粮预警 + 必应美学 + 杭州天气
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

# --- 基础工具 ---
def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

def log(msg):
    ts = get_beijing_time().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_zen_bar(current, target):
    """渲染定宽进度条"""
    percent = min(current / target, 1.0)
    filled = int(percent * 8)
    bar = "█" * filled + "░" * (8 - filled)
    return f"`{bar}` {int(percent*100):>3}%"

# --- 信息中枢 ---
def get_geek_daily():
    report = "\n---\n#### 📰 极客早报\n"
    # 1. 必应美图
    try:
        bing_res = requests.get("https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1", timeout=10).json()
        report += f"![Daily Photo](https://cn.bing.com{bing_res['images'][0]['url']})\n\n"
    except: pass
    # 2. 一言
    try:
        res = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=5).json()
        report += f"> “{res['hitokoto']}” —— *{res['from']}*\n\n"
    except:
        report += "> “Stay Hungry, Stay Foolish.”\n\n"
    # 3. 杭州天气
    try:
        w_url = "https://api.open-meteo.com/v1/forecast?latitude=30.24&longitude=120.20&current_weather=true&timezone=Asia%2FShanghai"
        w_res = requests.get(w_url, timeout=5).json()
        curr = w_res['current_weather']
        emoji = "🌤️" if curr['weathercode'] < 3 else "☁️" if curr['weathercode'] < 50 else "🌧️"
        report += f"🌡️ **今日天气预报**: `杭州 {emoji} {curr['temperature']}°C`\n"
    except: pass
    return report

# --- 核心逻辑 ---
class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.email = "?"
        self.left_days = 0
        self.points = 0
        self.points_change = "?"
        self.last_msg = ""
        self.exchange_advice = ""

    def req(self, method, path, data=None):
        for d in ["https://glados.cloud", "https://glados.rocks", "https://glados.network"]:
            try:
                h = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json;charset=UTF-8', 'Cookie': self.cookie}
                resp = requests.request(method, f"{d}{path}", headers=h, json=data, timeout=10)
                if resp.status_code == 200: return resp.json()
            except: continue
        return None

    def fetch_data(self):
        status = self.req('GET', '/api/user/status')
        if status and 'data' in status:
            self.email = status['data'].get('email', 'Unknown')
            self.left_days = int(float(status['data'].get('leftDays', 0)))
        
        pts_res = self.req('GET', '/api/user/points')
        if pts_res and 'points' in pts_res:
            self.points = int(float(pts_res['points']))
            history = pts_res.get('history', [])
            self.points_change = f"+{str(history[0].get('change', '0')).split('.')[0]}" if history else "+0"
            
            # --- 深度优化：完美对齐的垂直布局 ---
            checkpoints = [(100, 10), (200, 30), (500, 100)]
            advice_lines = ["**🎁 资产增值路径：**"]
            for target_pts, target_days in checkpoints:
                bar_str = get_zen_bar(self.points, target_pts)
                status_label = "<font color='#27ae60'>[就绪]</font>" if self.points >= target_pts else "<font color='#999999'>[积攒]</font>"
                
                # 每一行使用固定的格式化，确保 UI 对齐
                line = f"> {bar_str} {status_label} **{target_days:>3}天**档 | `{self.points}/{target_pts}pt`"
                if self.points < target_pts:
                    line += f" (缺 {target_pts - self.points}pt)"
                advice_lines.append(line)
            self.exchange_advice = "\n".join(advice_lines)

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# --- 推送引擎 ---
def push_dingtalk(webhook, secret, results_objs):
    if not webhook: return
    timestamp = str(round(time.time() * 1000))
    sign_str = ""
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign_str = f"&timestamp={timestamp}&sign={urllib.parse.quote_plus(base64.b64encode(hmac_code))}"

    bj_now = get_beijing_time()
    greeting = "早上好" if 5 <= bj_now.hour < 12 else "下午好" if 12 <= bj_now.hour < 18 else "晚上好"
    
    md_text = f"##  {greeting}。这是您的资产简报 \n\n"
    for g in results_objs:
        masked_email = f"{g.email.split('@')[0][:3]}***@{g.email.split('@')[1]}"
        expire_date = (bj_now + timedelta(days=g.left_days)).strftime('%Y-%m-%d')
        warning = " <font color='#e74c3c'>⚠️ 库存紧张</font>" if g.left_days < 7 else " <font color='#27ae60'>✅ 储备充足</font>"
        
        md_text += f"#### 👤 账号: `{masked_email}`\n"
        md_text += f"> **核心状态**：可用 `{g.left_days}` 天 {warning}\n"
        md_text += f"> **断粮日期**：`{expire_date}` | 积分 `{g.points}` ({g.points_change})\n\n"
        if g.exchange_advice: md_text += f"{g.exchange_advice}\n\n"

    md_text += get_geek_daily()
    md_text += f"\n---\n<font color='#999999' size='2'>🕒 数据同步于: {bj_now.strftime('%H:%M:%S')}</font>"

    try: requests.post(webhook + sign_str, json={"msgtype": "markdown", "markdown": {"title": "GLaDOS 禅意简报", "text": md_text}}, timeout=10)
    except: pass

def main():
    log("🚀 GLaDOS 对齐优化版启动...")
    raw_cookie = os.environ.get("GLADOS_COOKIE", "")
    if not raw_cookie: return
    cookies = [c.strip() for c in raw_cookie.split('\n') if c.strip()]
    results_objs = []
    for cookie in cookies:
        g = GLaDOS(cookie)
        res = g.checkin()
        g.last_msg = res.get('message', 'Net Error') if res else "Net Error"
        g.fetch_data()
        results_objs.append(g)
    push_dingtalk(os.environ.get("DINGTALK_WEBHOOK"), os.environ.get("DINGTALK_SECRET"), results_objs)

if __name__ == '__main__':
    main()
