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
from datetime import datetime

# 解决 Windows 环境输出乱码
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 配置 =================

DOMAINS = [
    "https://glados.cloud",
    "https://glados.rocks", 
    "https://glados.network",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json, text/plain, */*',
}

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def extract_cookie(raw: str):
    if not raw: return None
    raw = raw.strip()
    if 'koa:sess=' in raw or 'koa:sess.sig=' in raw: return raw
    if raw.startswith('{'):
        try: return 'koa.sess=' + json.loads(raw).get('token')
        except: pass
    if raw.count('.') == 2 and '=' not in raw and len(raw) > 50: return 'koa:sess=' + raw
    return raw

def get_cookies():
    raw = os.environ.get("GLADOS_COOKIE", "")
    if not raw:
        log("❌ 未配置 GLADOS_COOKIE")
        return []
    sep = '\n' if '\n' in raw else '&'
    return [extract_cookie(c) for c in raw.split(sep) if c.strip()]

# ================= 核心逻辑 =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.domain = DOMAINS[0]
        self.email = "?"
        self.left_days = "?"
        self.points = "?"
        self.points_change = "?"
        self.exchange_text = ""
        self.last_msg = ""
        
    def req(self, method, path, data=None):
        for d in DOMAINS:
            try:
                url = f"{d}{path}"
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
                h['Origin'] = d
                h['Referer'] = f"{d}/console/checkin"
                if method == 'GET':
                    resp = requests.get(url, headers=h, timeout=10)
                else:
                    resp = requests.post(url, headers=h, json=data, timeout=10)
                if resp.status_code == 200:
                    self.domain = d
                    return resp.json()
            except Exception as e:
                log(f"⚠️ {d} 请求失败: {e}")
                continue
        return None

    def get_status(self):
        res = self.req('GET', '/api/user/status')
        if res and 'data' in res:
            d = res['data']
            self.email = d.get('email', 'Unknown')
            self.left_days = str(d.get('leftDays', '?')).split('.')[0]
            return True
        return False

    def get_points(self):
        res = self.req('GET', '/api/user/points')
        if res and 'points' in res:
            self.points = str(res.get('points', '0')).split('.')[0]
            history = res.get('history', [])
            if history:
                last = history[0]
                change = str(last.get('change', '0')).split('.')[0]
                self.points_change = f"+{change}" if not change.startswith('-') else change
            
            plans = res.get('plans', {})
            pts = int(self.points)
            text_lines = []
            for plan_id, plan_data in plans.items():
                need, days = plan_data['points'], plan_data['days']
                if pts >= need:
                    text_lines.append(f"- <font color='#27ae60'>[已满额]</font> {need}分 ➟ {days}天")
                else:
                    text_lines.append(f"- <font color='#999999'>[待达成]</font> {need}分 ➟ {days}天 (还差{need-pts}分)")
            self.exchange_text = "\n".join(text_lines)
            return True
        return False

    def checkin(self):
        return self.req('POST', '/api/user/checkin', {'token': 'glados.cloud'})

# ================= 推送模块 =================

def push_dingtalk(webhook, secret, title, results_objs):
    """极致美化版钉钉推送"""
    if not webhook: return
    
    # 加签逻辑
    timestamp = str(round(time.time() * 1000))
    url = webhook
    if secret:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"

    # 构造 Markdown
    md_text = f"## 🚀 {title} \n\n"
    for g in results_objs:
        # 邮箱隐私处理
        email_parts = g.email.split('@')
        masked = f"{email_parts[0][:3]}***{email_parts[0][-2:]}@{email_parts[1]}" if len(email_parts) > 1 else g.email
        
        # 状态颜色
        status_icon = "🟢" if "Success" in g.last_msg or "Repeats" in g.last_msg else "🔴"
        change_color = "#27ae60" if "+" in g.points_change else "#e74c3c"

        md_text += f"#### 👤 账号: `{masked}`\n"
        md_text += f"> **核心资产报告**\n"
        md_text += f"> - 💰 **当前积分**: `{g.points}` <font color='{change_color}'>({g.points_change})</font>\n"
        md_text += f"> - ⏳ **剩余天数**: `{g.left_days}` 天\n"
        md_text += f"> - {status_icon} **结果**: {g.last_msg}\n\n"
        
        if g.exchange_text:
            md_text += f"**🎁 兑换进度建议：**\n{g.exchange_text}\n"
        md_text += "\n---\n"
    
    md_text += f"\n<font color='#999999' size='2'>🕒 任务时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>"

    data = {
        "msgtype": "markdown",
        "markdown": {"title": "GLaDOS 签到报告", "text": md_text}
    }
    try:
        requests.post(url, json=data, timeout=10)
        log("✅ 钉钉精美版推送成功")
    except Exception as e:
        log(f"⚠️ 推送异常: {e}")

# ================= 主程序 =================

def main():
    log("🚀 GLaDOS Checkin UI-Enhance Starting...")
    cookies = get_cookies()
    if not cookies: sys.exit(1)
    
    results_objs = []
    success_cnt = 0
    
    for cookie in cookies:
        g = GLaDOS(cookie)
        res = g.checkin()
        g.last_msg = res.get('message', 'Failure') if res else "Network Error"
        
        g.get_status()
        g.get_points()
        
        log(f"用户: {g.email} | 积分: {g.points} | 结果: {g.last_msg}")
        if "Checkin" in g.last_msg or "Repeats" in g.last_msg: success_cnt += 1
        results_objs.append(g)

    title = f"GLaDOS 签到结果: {success_cnt}/{len(cookies)}"
    
    # 尝试钉钉推送
    d_webhook = os.environ.get("DINGTALK_WEBHOOK")
    d_secret = os.environ.get("DINGTALK_SECRET")
    if d_webhook:
        push_dingtalk(d_webhook, d_secret, title, results_objs)

if __name__ == '__main__':
    main()
