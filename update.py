# -*- coding: utf-8 -*-
"""
福彩3D 通杀一码 — 云端全自动更新 (GitHub Actions)
====================================================
7源降级抓取 → 追加CSV → Hedge13专家重算 → 生成 index.html
GitHub Actions 三重 cron: 北京 22:00 / 23:30 / 01:00 (3次机会兜底)
"""
import csv
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

import core
import export_static

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "fc3d-history.csv")


# ─── 数据抓取（多源降级链）─────────────────────────────
def http_get(url, timeout=15):
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200:
            r.encoding = "utf-8"
            return r.text
    except Exception:
        pass
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        pass
    return None


def fetch_huiniao():
    """① 灰鸟API (JSON, 带 next_code, 跨年安全)"""
    url = "http://api.huiniao.top/interface/home/lotteryHistory?type=fcsd&page=1&limit=1"
    text = http_get(url)
    if not text:
        return None
    data = json.loads(text)
    if data.get("code") != 1:
        return None
    item = data["data"]["data"]["list"][0]
    return {"issue": str(item["code"]), "date": item["day"],
            "b": int(item["one"]), "s": int(item["two"]), "g": int(item["three"])}


def fetch_17500():
    """② 17500.cn 官方级全量TXT (2002至今), 取最新一行; GBK"""
    url = "http://www.17500.cn/getData/3d.TXT"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("gbk", errors="ignore")
        last = None
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            p = line.split()
            if len(p) >= 5 and len(p[0]) == 7 and p[0].isdigit():
                last = {"issue": p[0], "date": p[1],
                        "b": int(p[2]), "s": int(p[3]), "g": int(p[4])}
        return last
    except Exception:
        return None


def fetch_zhcw():
    """③ 中彩网"""
    url = "https://www.zhcw.com/kjxx/fc3d/"
    text = http_get(url)
    if not text:
        return None
    m = re.search(r'<em>(\d{7})</em>.*?<em>(\d{4}-\d{2}-\d{2})</em>.*?<i>(\d)</i>\s*<i>(\d)</i>\s*<i>(\d)</i>', text, re.DOTALL)
    if not m:
        m = re.search(r'(\d{7})期.*?(\d{4}-\d{2}-\d{2}).*?(\d)\s*(\d)\s*(\d)', text, re.DOTALL)
    if not m:
        return None
    return {"issue": m.group(1), "date": m.group(2),
            "b": int(m.group(3)), "s": int(m.group(4)), "g": int(m.group(5))}


def fetch_apihz():
    """④ apihz JSON API"""
    for url in ("https://api.apihz.cn/api/kaijiang/fc3d/list.php",
                "https://api.apihz.cn/api/caipiao/fc3d.php?id=10005145&key=c4d6c4c6a8d1a05ba2a01b17b7b1c56b&type=json"):
        text = http_get(url)
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        item = None
        if isinstance(data, dict) and data.get("data"):
            lst = data["data"]
            if isinstance(lst, list) and lst:
                item = lst[0]
            elif isinstance(lst, dict):
                item = lst
        if not item:
            continue
        expect = item.get("expect") or item.get("qihao") or item.get("issue") or item.get("code")
        nums = item.get("code") or item.get("number") or item.get("num") or ""
        ns = str(nums)
        if len(ns) >= 3 and expect:
            return {"issue": str(expect), "date": str(item.get("time") or "")[:10],
                    "b": int(ns[-3]), "s": int(ns[-2]), "g": int(ns[-1])}
    return None


def fetch_8200():
    """⑤ 8200 JSON API"""
    url = "https://api.8200.cn/hall/fc3d/getFc3dLotteryList?pageNo=1&pageSize=1"
    text = http_get(url)
    if not text:
        return None
    data = json.loads(text)
    if data.get("code") != 0:
        return None
    item = data["data"]["list"][0]
    return {"issue": str(item["lotteryNo"]), "date": item["lotteryTime"][:10],
            "b": int(item["lotteryNumber"][0]), "s": int(item["lotteryNumber"][1]),
            "g": int(item["lotteryNumber"][2])}


def fetch_55128():
    """⑥ 55128 网页解析"""
    url = "https://www.55128.cn/kjh/fcsd-history-61.htm"
    text = http_get(url)
    if not text:
        return None
    m = re.search(r'<td>(\d{7})</td>\s*<td>(\d{4}-\d{2}-\d{2})</td>\s*<td[^>]*>\s*(\d)\s*</td>\s*<td[^>]*>\s*(\d)\s*</td>\s*<td[^>]*>\s*(\d)\s*</td>', text)
    if not m:
        m = re.search(r'(\d{7}).*?(\d{4}-\d{2}-\d{2}).*?(\d)\s+(\d)\s+(\d)', text, re.DOTALL)
    if not m:
        return None
    return {"issue": m.group(1), "date": m.group(2),
            "b": int(m.group(3)), "s": int(m.group(4)), "g": int(m.group(5))}


def fetch_cjcp():
    """⑦ 彩经网 网页解析"""
    url = "https://www.cjcp.com.cn/kaijiang/fc3d/"
    text = http_get(url)
    if not text:
        return None
    m = re.search(r'(\d{7})\s*期.*?(\d{4}-\d{2}-\d{2}).*?(\d)\s*(\d)\s*(\d)', text, re.DOTALL)
    if not m:
        m = re.search(r'<td>(\d{7})</td>.*?<td>(\d{4}-\d{2}-\d{2})</td>.*?<td>(\d)</td>.*?<td>(\d)</td>.*?<td>(\d)</td>', text, re.DOTALL)
    if not m:
        return None
    return {"issue": m.group(1), "date": m.group(2),
            "b": int(m.group(3)), "s": int(m.group(4)), "g": int(m.group(5))}


def load_last_issue():
    r = None
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pass
        return r["issue"] if r else None
    except Exception:
        return None


def append_csv(data):
    """追加一期到 CSV, 返回 1=新增 0=重复"""
    existing = set()
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing.add(r.get("issue", ""))
    except FileNotFoundError:
        pass
    iss = str(data["issue"])
    if iss in existing:
        return 0
    if not (0 <= data["b"] <= 9 and 0 <= data["s"] <= 9 and 0 <= data["g"] <= 9):
        print(f"  ⚠️ 数据非法: {data}")
        return -1
    with open(CSV_PATH, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([iss, data["b"], data["s"], data["g"]])
    print(f"  ✅ 已追加: {iss} ({data.get('date','')}) {data['b']}{data['s']}{data['g']}")
    return 1


def fetch_latest():
    """多源降级链: 灰鸟 → 17500 → 中彩网 → apihz → 8200 → 55128 → 彩经网"""
    sources = [
        ("灰鸟API", fetch_huiniao),
        ("17500", fetch_17500),
        ("中彩网", fetch_zhcw),
        ("apihz", fetch_apihz),
        ("8200", fetch_8200),
        ("55128", fetch_55128),
        ("彩经网", fetch_cjcp),
    ]
    last_issue = load_last_issue()
    for name, fn in sources:
        try:
            data = fn()
            if not data:
                print(f"  ⏭️ {name}: 无数据")
                continue
            if last_issue and str(data["issue"]) <= str(last_issue):
                print(f"  ⏭️ {name}: {data['issue']} <= 本地 {last_issue}, 已最新")
                continue
            print(f"  📡 {name}: {data['issue']} {data['b']}{data['s']}{data['g']}")
            return data
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")
    return None


# ─── 主流程 ────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=== 福彩3D通杀一码 云端全自动更新 ===")
    # 1. 抓取追加
    try:
        data = fetch_latest()
        if data:
            r = append_csv(data)
            if r == -1:
                print("  ❌ 数据非法, 不重算")
                return 1
            if r == 1:
                print("  → 有新数据, 触发重算")
            else:
                print("  → 无新增, 仍重算确保页面最新")
    except Exception as e:
        print(f"  ⚠️ 抓取异常: {e}")
    # 2. 重算 (Hedge 13专家, 完整 walk-forward)
    try:
        res = core.compute_all(force=True)
        s = res["summary"]
        n = res["next"]
        print(f"  回测: {s['hit']}/{s['total']} = {s['rate']*100:.2f}%")
        print(f"  下一期 {n['target_issue']}: 通杀 {n['kill']}")
    except Exception as e:
        print(f"  ❌ 重算失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    # 3. 生成 index.html
    try:
        export_static.main()
    except Exception as e:
        print(f"  ❌ 生成页面失败: {e}")
        return 1
    print(f"  总用时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
