#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys
import time
import json
import cloudscraper  # 替代 requests，自动处理 Cloudflare


# ===== 全局配置 =====
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
CUR_TIME = time.strftime("%Y%m%d", time.localtime())

LOG_OUTPUT = os.path.join(CUR_PATH, "log.output.txt")
LOG_SUCCESS = os.path.join(CUR_PATH, "log.success.txt")

GB_TIMEOUT = 20
MAX_RETRY = 3

uname = os.environ['T00LS_USERNAME'] # 用户名
pswd = os.environ['T00LS_PASSWORD']  # 明文密码或密码MD5
#password_hash = ("T00LS_MD5" in os.environ) and os.environ['T00LS_MD5']=='False' or False  # 密码为md5时设置为True
qesnum = ("T00LS_QID" in os.environ) and os.environ['T00LS_QID'] or '' # 安全提问 参考下面
qan = ("T00LS_QANS" in os.environ) and os.environ['T00LS_QANS'] or '' #安全提问答案

# 用户信息（请务必修改为你的真实信息！）
USER_INFO_LIST = [
    {
        'username': uname,          # ← 改成你的用户名
        'password': pswd,   # ← 改成你的密码
        'questionid': qesnum,
        'answer': qan               # 安全提问答案
    }
]



# 安全提问ID
# 0 = 没有安全提问
# 1 = 母亲的名字
# 2 = 爷爷的名字
# 3 = 父亲出生的城市
# 4 = 您其中一位老师的名字
# 5 = 您个人计算机的型号
# 6 = 您最喜欢的餐馆名称
# 7 = 驾驶执照的最后四位数字

def output(msg, time_fmt="%Y%m%d%H%M%S"):
    current_time = time.strftime(time_fmt, time.localtime())
    line = f"[{current_time}] <-> {msg}"
    print(line)
    with open(LOG_OUTPUT, "a+", encoding="utf-8") as f:
        f.write(line + "\n")


def record_success(username):
    mark = f"[{CUR_TIME}] [{username}] SignIn SUCCESS"
    with open(LOG_SUCCESS, "a+", encoding="utf-8") as f:
        f.write(mark + "\n")


def is_already_signed(username):
    mark = f"[{CUR_TIME}] [{username}] SignIn SUCCESS"
    if os.path.isfile(LOG_SUCCESS):
        with open(LOG_SUCCESS, "r", encoding="utf-8") as f:
            return mark in f.read()
    return False


def login_and_get_formhash(session, user_info, retry=MAX_RETRY):
    output(f"[*] 尝试登录用户: {user_info['username']} (重试剩余: {retry})")

    try:
        login_url = "https://www.t00ls.com/login.json"
        data = {
            "action": "login",
            "username": user_info["username"],
            "password": user_info["password"],
            "questionid": str(user_info.get("questionid", 0)),
            "answer": str(user_info.get("answer", ""))
        }

        resp = session.post(login_url, data=data, timeout=GB_TIMEOUT)
        output(f"[+] 登录响应状态码: {resp.status_code}")

        # 检查是否被 Cloudflare 拦截（返回 HTML）
        if "<title>Attention Required! | Cloudflare</title>" in resp.text:
            raise Exception("请求被 Cloudflare 拦截，请检查 IP 或 User-Agent")

        # 尝试解析 JSON
        try:
            result = resp.json()
        except json.JSONDecodeError:
            raise Exception(f"登录返回非 JSON 内容（可能是拦截页）:\n{resp.text[:500]}")

        if result.get("status") == "success":
            formhash = result.get("formhash")
            if formhash:
                output(f"[+] 登录成功，获取 formhash: {formhash}")
                return formhash
            else:
                raise Exception("登录成功但未返回 formhash")
        else:
            msg = result.get("message", "未知错误")
            raise Exception(f"登录失败: {msg}")

    except Exception as e:
        output(f"[-] 登录异常: {e}")
        if retry > 0:
            time.sleep(2)
            return login_and_get_formhash(session, user_info, retry - 1)
        else:
            output("[-] 登录失败，已达最大重试次数")
            return None


def do_signin(session, formhash, username, retry=MAX_RETRY):
    output(f"[*] 开始签到 (重试剩余: {retry})")

    try:
        sign_url = "https://www.t00ls.com/ajax-sign.json"
        data = {
            "signsubmit": "apply",
            "formhash": formhash
        }

        # 设置 Referer（T00ls 可能校验）
        session.headers.update({"Referer": "https://www.t00ls.com/members-profile.html"})

        resp = session.post(sign_url, data=data, timeout=GB_TIMEOUT)
        output(f"[+] 签到响应状态码: {resp.status_code}")

        try:
            result = resp.json()
        except json.JSONDecodeError:
            raise Exception(f"签到返回非 JSON: {resp.text[:500]}")

        status = result.get("status", "").lower()
        message = result.get("message", "")

        if status == "success":
            output("[+] 签到成功！")
            record_success(username)
            return True
        elif "alreadysign" in message.lower() or "已签" in message:
            output("[+] 今日已签到")
            record_success(username)
            return True
        else:
            raise Exception(f"签到失败: {message}")

    except Exception as e:
        output(f"[-] 签到异常: {e}")
        if retry > 0:
            time.sleep(2)
            return do_signin(session, formhash, username, retry - 1)
        else:
            output("[-] 签到失败，已达最大重试次数")
            return False


def main():
    for user in USER_INFO_LIST:
        username = user["username"]
        output("*" * 100)
        output(f"[+] 处理用户: {username}")
        # 检查今日是否已签到
        if is_already_signed(username):
            output(f"[+] 今日已成功签到，跳过。")
            continue
        session = cloudscraper.create_scraper()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        # 登录并获取 formhash
        formhash = login_and_get_formhash(session, user)
        if not formhash:
            output(f"[-] 无法获取 formhash，跳过签到")
            continue

        # 执行签到
        do_signin(session, formhash, username)

        output("*" * 100)

    # 日志轮转（防过大）
    for log_file in [LOG_SUCCESS, LOG_OUTPUT]:
        if os.path.exists(log_file) and os.path.getsize(log_file) > 2 * 1024 * 1024:  # 2MB
            bak = f"{log_file}.{CUR_TIME}.bak"
            os.rename(log_file, bak)
            output(f"[!] 日志文件过大，已备份为: {bak}")


if __name__ == "__main__":
    main()
