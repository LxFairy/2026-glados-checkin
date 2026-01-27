#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 GLaDOS 极客情报终极版
- 包含：兑换进度建议 (100/200/500分档位)
- 包含：断粮日期预测 + 7天倒计时预警
- 包含：极客早报 (天气 + 一言)
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

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 极客配置 =================
DOMAINS = ["https://glados.cloud", "https://glados.rocks", "https://glados.network"]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
}

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

def log(msg):
    ts = get_beijing_time().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ================= 信息中枢模块 =================

def get_geek_daily():
    """抓取一言、杭州天气（高可用版）和热搜"""
    report = "\n---\n#### 📰 极客早报\n"
    
    # 1. 一言 (Hitokoto)
    try:
        res = requests.get("https://v1.hitokoto.cn/?encode=json", timeout=5).json()
        report += f"> “{res['hitokoto']}” —— *{res['from']}*\n\n"
    except:
        report += "> “代码即诗，逻辑即美。”\n\n"
    
    # 2. 杭州天气 (Open-Meteo 备选方案)
    weather_str = "查询失败"
    try:
        # 杭州经纬度：30.24, 120.20
        weather_url = "https://api.open-meteo.com/v1/forecast?latitude=30.24&longitude=120.20&current_weather=true&timezone=Asia%2FShanghai"
        w_res = requests.get(weather_url, timeout=5).json()
        if 'current_weather' in w_res:
            curr = w_res['current_weather']
            temp = curr['temperature']
            # 简单的天气代码转换
            code = curr['weathercode']
            emoji = "🌤️" if code < 3 else "☁️" if code < 50 else "🌧️"
            weather_str = f"杭州 {emoji} {temp}°C"
    except:
        # 如果备选也挂了，尝试最后一次 wttr.in 简化版请求
        try:
            weather_str = requests.get("https://wttr.in/Hangzhou?format=1&lang=zh-cn", timeout=5).text.strip()
        except: pass

    report += f"🌡️ **今日环境**: `{weather_str}`\n"
        
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
        self.exchange_advice = ""

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
        # 获取基础状态
        status = self.req('GET', '/api/user/status')
        if status and 'data' in status:
            self.email = status['data'].get('email', 'Unknown')
            self.left_days = int(float(status['data'].get('leftDays', 0)))
        
        # 获取积分详情
        pts_res = self.req('GET', '/api/user/points')
        if pts_res and 'points' in pts_res:
            self.points = int(float(pts_res['points']))
            history = pts_res.get('history', [])
            if history:
                change = str(history[0].get('change', '0')).split('.')[0]
                self.points_change = f"+{change}" if not change.startswith('-') else change
            
            # 重新构建你要求的“兑换进度建议”
            checkpoints = [(100, 10), (200, 30), (500, 100)]
            advice_lines = ["**🎁 兑换进度建议：**"]
            for target_pts, target_days in checkpoints:
                if self.points >= target_pts:
                    line = f"- <font color='#27ae60'>[已满足]</font> {target_pts}分 ➟ {target_days}天"
                else:
                    line = f"- <font color='#999999'>[待达成]</font> {target_pts}分 ➟ {target_days}天 (还差{target_pts - self.points}分)"
                advice_lines.append(line)
            self.exchange_advice = "\n".join(advice_lines)

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 推送引擎 =================

def push_dingtalk(webhook, secret, title, results_objs):
    if not webhook: return
    timestamp = str(round(time.time() * 1000))
    url = webhook
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"

    md_text = f"## 🚀 {title} \n\n"
    for g in results_objs:
        email_parts = g.email.split('@')
        masked = f"{email_parts[0][:3]}***{email_parts[0][-2:]}@{email_parts[1]}"
        expire_date = (get_beijing_time() + timedelta(days=g.left_days)).strftime('%Y-%m-%d')
        
        warning_label = " <font color='#e74c3c'>⚠️ 库存紧张</font>" if g.left_days < 7 else " <font color='#27ae60'>✅ 储备充足</font>"
        status_icon = "🟢" if "Success" in g.last_msg or "Repeats" in g.last_msg else "🔴"
        change_color = "#27ae60" if "+" in g.points_change else "#e74c3c"

        md_text += f"#### 👤 账号: `{masked}`\n"
        md_text += f"> **资产状态汇报**\n"
        md_text += f"> - 💰 **当前积分**: `{g.points}` <font color='{change_color}'>({g.points_change})</font>\n"
        md_text += f"> - ⏳ **可用天数**: `{g.left_days}` 天 {warning_label}\n"
        md_text += f"> - 📅 **断粮日期**: `{expire_date}`\n"
        md_text += f"> - {status_icon} **状态**: {g.last_msg}\n\n"
        
        # 把你最喜欢的建议部分加回来
        if g.exchange_advice:
            md_text += f"{g.exchange_advice}\n\n"

    md_text += get_geek_daily()
    bj_now = get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')
    md_text += f"\n---\n<font color='#999999' size='2'>🕒 信息中枢更新于: {bj_now}</font>"

    data = {"msgtype": "markdown", "markdown": {"title": "GLaDOS 极客日报", "text": md_text}}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        log(f"推送失败: {e}")

def main():
    log("🚀 GLaDOS 终极整合版启动...")
    raw_cookie = os.environ.get("GLADOS_COOKIE", "")
    if not raw_cookie: sys.exit(1)
    cookies = [c.strip() for c in raw_cookie.split('\n') if c.strip()]
    results_objs = []
    success_cnt = 0
    for cookie in cookies:
        g = GLaDOS(cookie)
        res = g.checkin()
        g.last_msg = res.get('message', 'Net Error') if res else "Net Error"
        g.fetch_data()
        if "Success" in g.last_msg or "Repeats" in g.last_msg: success_cnt += 1
        results_objs.append(g)
    push_dingtalk(os.environ.get("DINGTALK_WEBHOOK"), os.environ.get("DINGTALK_SECRET"), f"GLaDOS 签到结果: {success_cnt}/{len(cookies)}", results_objs)

if __name__ == '__main__':
    main()
