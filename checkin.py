  #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLaDOS 乔布斯禅意情报版 v3.0
- 核心：同时支持 钉钉(DingTalk) + 微信(Server酱)
- 优化：推送内容统一构建，Markdown 渲染完美对齐
- 视觉：必应美图 + 杭州天气 + 禅意进度条
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

# 1. 基础工具函数
def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

def log(msg):
    ts = get_beijing_time().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 极客配置 =================
DOMAINS = ["https://glados.cloud", "https://glados.rocks", "https://glados.network"]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
}

def get_zen_bar(current, target):
    """渲染极简进度条"""
    percent = min(current / target, 1.0)
    filled = int(percent * 8)
    bar = "█" * filled + "░" * (8 - filled)
    return f"`{bar}` {int(percent*100):>3}% ({current}/{target}pt)"

# ================= 信息中枢模块 =================

def get_geek_daily():
    report = "\n---\n#### 📰 极客早报\n"
    # 1. 必应每日美图
    try:
        bing_res = requests.get("https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1", timeout=10).json()
        img_url = "https://cn.bing.com" + bing_res['images'][0]['url']
        report += f"![Daily Photo]({img_url})\n\n"
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

# ================= 核心逻辑模块 =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.email, self.left_days, self.points = "?", 0, 0
        self.points_change, self.last_msg, self.exchange_advice = "+0", "", ""

    def req(self, method, path, data=None):
        for d in DOMAINS:
            try:
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
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
            if history:
                change = str(history[0].get('change', '0')).split('.')[0]
                self.points_change = f"+{change}" if not change.startswith('-') else change
            
             # 进度建议逻辑
            checkpoints = [(100, 10), (200, 30), (500, 100)]
            advice_lines = ["**🎁 资产增值路径：**"]
            for target_pts, target_days in checkpoints:
                bar_str = get_zen_bar(self.points, target_pts)
                if self.points >= target_pts:
                    status_text = "<font color='#27ae60'>[就绪]</font>"
                    gap = "可兑换"
                else:
                    status_text = "<font color='#999999'>[积攒]</font>"
                    gap = f"还差 {target_pts - self.points}"
                advice_lines.append(f"> {bar_str} {status_text} **{target_days}天** ({gap})")
            self.exchange_advice = "\n".join(advice_lines)

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 推送引擎模块 =================

def push_dingtalk(webhook, secret, title, content):
    if not webhook: return
    timestamp = str(round(time.time() * 1000))
    url = webhook
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"
    
    try:
        requests.post(url, json={"msgtype": "markdown", "markdown": {"title": title, "text": content}}, timeout=10)
        log("✅ 钉钉推送完成")
    except: log("❌ 钉钉推送异常")

def push_server_chan(sendkey, title, content):
    if not sendkey:
        log("⚠️ 未设置 SERVER_CHAN_SENDKEY，跳过微信推送")
        return
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        res = requests.post(url, data={"title": title, "desp": content}, timeout=10).json()
        if res.get('code') == 0: log("✅ 微信推送完成")
        else: log(f"❌ 微信推送报错: {res.get('message')}")
    except: log("❌ 微信请求异常")

# ================= 主程序入口 =================

def main():
    log("🚀 GLaDOS 极客双端推送版启动...")
    
    # 1. 环境变量读取
    raw_cookie = os.environ.get("GLADOS_COOKIE")
    dd_webhook = os.environ.get("DINGTALK_WEBHOOK")
    dd_secret = os.environ.get("DINGTALK_SECRET")
    sc_sendkey = os.environ.get("SERVER_CHAN_SENDKEY")
    
    if not raw_cookie:
        log("❌ 未配置 GLADOS_COOKIE")
        return

    # 2. 执行核心逻辑
    cookies = [c.strip() for c in raw_cookie.split('\n') if c.strip()]
    results_objs = []
    for cookie in cookies:
        g = GLaDOS(cookie)
        res = g.checkin()
        g.last_msg = res.get('message', 'Net Error') if res else "Net Error"
        g.fetch_data()
        results_objs.append(g)
        log(f"账号 {g.email} 处理完成")

    # 3. 统一构建内容 (针对 Markdown 优化)
    bj_now = get_beijing_time()
    greeting = "早上好" if 5 <= bj_now.hour < 12 else "下午好" if 12 <= bj_now.hour < 18 else "晚上好"
    title = f"GLaDOS {greeting}简报"
    
    md_text = f"##  {greeting}。这是您的资产简报 \n\n"
    for g in results_objs:
        email_parts = g.email.split('@')
        masked = f"{email_parts[0][:3]}***{email_parts[0][-2:]}@{email_parts[1]}"
        expire_date = (bj_now + timedelta(days=g.left_days)).strftime('%Y-%m-%d')
        warning = " <font color='#e74c3c'>⚠️ 库存紧张</font>" if g.left_days < 7 else " <font color='#27ae60'>✅ 储备充足</font>"
        
        md_text += f"#### 👤 账号: `{masked}`\n"
        md_text += f"> **核心资产报告**\n"
        md_text += f"> - 💰 **当前积分**: `{g.points}` ({g.points_change})\n"
        md_text += f"> - ⏳ **可用天数**: `{g.left_days}` 天 {warning}\n"
        md_text += f"> - 📅 **断粮日期**: `{expire_date}`\n"
        md_text += f"> - 🔔 **状态反馈**: {g.last_msg}\n\n"
        if g.exchange_advice:
            md_text += f"{g.exchange_advice}\n\n"

    md_text += get_geek_daily()
    md_text += f"\n---\n<font color='#999999' size='2'>🕒 数据更新于: {bj_now.strftime('%H:%M:%S')}</font>"

    # 4. 执行双端分发
    push_dingtalk(dd_webhook, dd_secret, title, md_text)
    push_server_chan(sc_sendkey, title, md_text)

if __name__ == '__main__':
    main()
