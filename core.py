# -*- coding: utf-8 -*-
"""
core.py — 福彩3D通杀一码 回测引擎
=================================
- 加载/校验 CSV
- 预计算特征矩阵
- 公式池 pred 预计算 (滚动计数器, 严格只用历史数据)
- 200 期逐期滚动评分选择 (命中率 - 连错惩罚 - 近期惩罚)
- 汇总统计 / Top 榜单 / 下一期预测 / JSON 缓存
"""
import os
import sys
import json
import time
import numpy as np

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

import formulas as FM

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CSV 路径统一: 优先根目录 fc3d-history.csv (云端/统一布局), 兼容旧 data/ 布局
if os.path.exists(os.path.join(BASE_DIR, "fc3d-history.csv")):
    DATA_CSV = os.path.join(BASE_DIR, "fc3d-history.csv")
else:
    DATA_CSV = os.path.join(BASE_DIR, "data", "fc3d-history.csv")
CACHE_JSON = os.path.join(BASE_DIR, "cache", "backtest.json")
SRC_CSV = r"D:\福彩3D资料\fc3d-history.csv"

W_SCORE = 200          # 回测展示窗口(期数)
MIN_T = 600            # pred 预计算起点(足够预热)
BASELINE = 0.9 ** 3    # 0.729

# ---- Hedge 加权投票参数 (学习自杀和尾项目, 网格搜索 WIN×K 实测最优) ----
HEDGE_WIN = 90         # 专家权重评估窗口 (网格: 30~200, 90 最优)
HEDGE_K = 13           # 参与投票的专家数 (K精细扫描 1~500: 13 综合分最高, 9~16 稳健平台)
HEDGE_SMOOTH = 0.02    # 权重下限(防专家消失; 0.005~0.1 无显著差异)
TOP1_WIN = 100         # 动态Top1 对比窗口

A_W = [8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80,
       90, 100, 110, 120, 130, 150, 160, 180, 200]
GAMMA = [0.88, 0.90, 0.92, 0.93, 0.95, 0.97, 0.99]
SLOPE_W = [10, 15, 30, 45, 60]
SUM_W = [5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 100, 150, 200]
AR_W = [20, 50]

# ---------------------------------------------------------------- 数据层

def ensure_data():
    """首次启动把源 CSV 复制到工作目录 data/"""
    if not os.path.exists(DATA_CSV) and os.path.exists(SRC_CSV):
        os.makedirs(os.path.dirname(DATA_CSV), exist_ok=True)
        with open(SRC_CSV, "rb") as fin, open(DATA_CSV, "wb") as fout:
            fout.write(fin.read())

def load_csv(path=DATA_CSV):
    """返回 (issues, digits)。digits: list of (h,t,o) int"""
    ensure_data()
    issues, digits = [], []
    bad = 0
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.read().strip().splitlines()
    for i, ln in enumerate(lines):
        if i == 0 and ln.lower().startswith("issue"):
            continue
        parts = ln.strip().split(",")
        if len(parts) < 4:
            bad += 1
            continue
        try:
            iss = int(parts[0])
            h, t, o = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            bad += 1
            continue
        if not (0 <= h <= 9 and 0 <= t <= 9 and 0 <= o <= 9):
            bad += 1
            continue
        if issues and iss <= issues[-1]:
            bad += 1
            continue
        issues.append(iss)
        digits.append((h, t, o))
    if bad:
        print(f"[warn] 跳过 {bad} 行异常数据")
    return issues, digits

def append_rows(rows, path=DATA_CSV):
    """追加新期 (issue,h,t,o) 列表到 CSV, 返回新增条数"""
    issues, digits = load_csv(path)
    existing = set(issues)
    added = 0
    lines = []
    for iss, h, t, o in rows:
        iss = int(iss)
        if iss in existing or not (0 <= h <= 9 and 0 <= t <= 9 and 0 <= o <= 9):
            continue
        if issues and iss <= issues[-1]:
            continue
        lines.append(f"{iss},{h},{t},{o}")
        issues.append(iss)
        existing.add(iss)
        added += 1
    if added:
        with open(path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
    return added

# ---------------------------------------------------------------- 特征预计算

def compute_features(issues, digits):
    N = len(digits)
    H = np.array([d[0] for d in digits], dtype=np.int8)
    T = np.array([d[1] for d in digits], dtype=np.int8)
    O = np.array([d[2] for d in digits], dtype=np.int8)
    S = (H.astype(np.int16) + T + O)
    SW = S % 10
    K = (np.maximum.reduce([H, T, O]) - np.minimum.reduce([H, T, O])).astype(np.int8)
    MXM = (np.maximum.reduce([H, T, O]) + np.minimum.reduce([H, T, O])) % 10
    P3 = H.astype(np.int16) * T * O
    feats = {
        "H": H, "T": T, "O": O,
        "S": S.astype(np.int8), "SW": SW.astype(np.int8), "K": K,
        "MXM": MXM.astype(np.int8),
        "P3M10": (P3 % 10).astype(np.int8),
        "P3M9": (P3 % 9).astype(np.int8),
        "P3M8": (P3 % 8).astype(np.int8),
        "P3M7": (P3 % 7).astype(np.int8),
        "P3T10": ((P3 // 10) % 10).astype(np.int8),
        "HTM10": ((H * T) % 10).astype(np.int8),
        "TOM10": ((T * O) % 10).astype(np.int8),
        "HOM10": ((H * O) % 10).astype(np.int8),
        "DHT": (np.abs(H - T)).astype(np.int8),
        "DTO": (np.abs(T - O)).astype(np.int8),
        "DHO": (np.abs(H - O)).astype(np.int8),
        "HTS": ((H + T) % 10).astype(np.int8),
        "TOS": ((T + O) % 10).astype(np.int8),
        "HOS": ((H + O) % 10).astype(np.int8),
        "HTD": ((H - T) % 10).astype(np.int8),
        "TOD": ((T - O) % 10).astype(np.int8),
        "HOD": ((H - O) % 10).astype(np.int8),
    }
    # 形态
    F3 = np.zeros(N, dtype=np.int8)
    eq = (H == T).astype(int) + (T == O).astype(int) + (H == O).astype(int)
    F3 = np.where(eq >= 3, 0, np.where(eq >= 1, 1, 2)).astype(np.int8)
    feats["F3"] = F3
    feats["PAR8"] = ((H % 2) * 4 + (T % 2) * 2 + (O % 2)).astype(np.int8)
    feats["SZ8"] = ((H >= 5) * 4 + (T >= 5) * 2 + (O >= 5)).astype(np.int8)
    # AC 值
    ac = np.zeros(N, dtype=np.int8)
    for i in range(N):
        s = {abs(int(H[i]) - int(T[i])), abs(int(T[i]) - int(O[i])), abs(int(H[i]) - int(O[i]))}
        ac[i] = len(s) - 1
    feats["AC"] = ac
    # 振幅形态
    amp = np.zeros((N, 3), dtype=np.int8)
    amp[1:] = np.abs(np.stack([H[1:], T[1:], O[1:]], 1) - np.stack([H[:-1], T[:-1], O[:-1]], 1))
    feats["AMP8"] = ((amp[:, 0] >= 4) * 4 + (amp[:, 1] >= 4) * 2 + (amp[:, 2] >= 4)).astype(np.int8)
    # 和尾×跨度联合
    feats["SWK"] = (SW.astype(np.int16) * 10 + K).astype(np.int16)
    # 位和条件特征 (D8)
    feats["W2"] = (((H + T) % 2) * 2 + ((T + O) % 2)).astype(np.int8)
    feats["W3"] = (((H + T) % 3) * 3 + ((T + O) % 3)).astype(np.int8)
    feats["W5"] = ((H.astype(np.int16) * T + O) % 5).astype(np.int8)
    # 重码数 RP[t] = |digits(t) ∩ digits(t-1)|
    rp = np.zeros(N, dtype=np.int8)
    for i in range(1, N):
        rp[i] = len(set(digits[i]) & set(digits[i - 1]))
    feats["RP"] = rp
    # B 族新增条件特征
    feats["PAR3"] = ((H % 2) + (T % 2) + (O % 2)).astype(np.int8)
    feats["SZ3"] = ((H >= 5) + (T >= 5) + (O >= 5)).astype(np.int8)
    feats["SUMOD"] = (S % 2).astype(np.int8)
    feats["KOD"] = (K % 2).astype(np.int8)
    feats["KBIG"] = (K >= 5).astype(np.int8)
    cont = np.zeros(N, dtype=np.int8)
    for i in range(N):
        s3 = sorted((int(H[i]), int(T[i]), int(O[i])))
        cont[i] = 1 if (s3[1] - s3[0] == 1 or s3[2] - s3[1] == 1) else 0
    feats["CONT"] = cont
    perm = np.zeros(N, dtype=np.int8)
    for i in range(N):
        order = tuple(np.argsort((int(H[i]), int(T[i]), int(O[i]))))
        mapping = {(0, 1, 2): 0, (0, 2, 1): 1, (1, 0, 2): 2,
                   (1, 2, 0): 3, (2, 0, 1): 4, (2, 1, 0): 5}
        perm[i] = mapping.get(order, 0)
    feats["PERM"] = perm
    ndig = np.zeros(N, dtype=np.int8)
    for i in range(N):
        ndig[i] = len(set(digits[i])) - 1
    feats["NDIG"] = ndig
    ampk = np.zeros(N, dtype=np.int8)
    ampk[1:] = np.abs(K[1:].astype(np.int16) - K[:-1].astype(np.int16))
    feats["AMPK"] = ampk.astype(np.int8)
    # H 族组合条件特征
    PAR8 = feats["PAR8"]; SZ8 = feats["SZ8"]
    feats["R27"] = ((H % 3) * 9 + (T % 3) * 3 + (O % 3)).astype(np.int8)
    feats["SWF3"] = (SW.astype(np.int16) * 3 + F3).astype(np.int8)
    feats["KF3"] = (K.astype(np.int16) * 3 + F3).astype(np.int8)
    feats["PARSZ"] = (PAR8.astype(np.int16) * 8 + SZ8).astype(np.int8)
    feats["SWPAR"] = (SW.astype(np.int16) * 8 + PAR8).astype(np.int8)
    feats["KSZ"] = (K.astype(np.int16) * 8 + SZ8).astype(np.int8)
    feats["HTOM5"] = (((H - T) % 5) * 2 + (O % 2)).astype(np.int8)
    f32 = np.zeros(N, dtype=np.int8)
    f32[1:] = F3[1:] * 3 + F3[:-1]
    f32[0] = F3[0] * 3
    feats["F32"] = f32
    swd3f = np.zeros(N, dtype=np.int8)
    diff_s = np.sign(S[1:].astype(np.int16) - S[:-1].astype(np.int16)) + 1
    swd3f[1:] = diff_s * 3 + F3[1:]
    swd3f[0] = F3[0]
    feats["SWD3F"] = swd3f.astype(np.int8)
    # 期号类特征 (扩展一行: 下一期虚拟期号, 供预测 t=N 使用)
    iss_ext = issues + [issues[-1] + 1]
    issx = np.array(iss_ext, dtype=np.int64)
    feats["IM10"] = (issx % 10).astype(np.int8)
    feats["IM7"] = (issx % 7).astype(np.int8)
    feats["IM5"] = (issx % 5).astype(np.int8)
    yseq = issx % 1000
    feats["YM5"] = (yseq % 5).astype(np.int8)
    feats["YM10"] = (yseq % 10).astype(np.int8)
    feats["YM20"] = (yseq % 20).astype(np.int8)
    feats["YM3"] = (yseq % 3).astype(np.int8)
    feats["CY"] = (yseq % 30).astype(np.int8)
    feats["PARIM"] = (PAR8.astype(np.int16) * 2 + (np.array(issues, dtype=np.int64) % 2)).astype(np.int8)
    # 遗漏 (N+1 行: 最后一行 = 截至最后一期的当前遗漏, 供预测下一期)
    missM = np.zeros((N + 1, 10), dtype=np.int16)
    missP = np.zeros((N + 1, 3, 10), dtype=np.int16)
    lastM = np.full(10, -1)
    lastP = np.full((3, 10), -1)
    for i in range(N + 1):
        missM[i] = i - 1 - lastM
        missP[i] = i - 1 - lastP
        if i < N:
            for p, d in enumerate(digits[i]):
                lastP[p, d] = i
            for d in set(digits[i]):
                lastM[d] = i
    feats["missM"] = missM
    feats["missP"] = missP
    # 合并前缀和 (E5 用)
    pref = np.zeros((N + 1, 10), dtype=np.int32)
    for i in range(N):
        pref[i + 1] = pref[i]
        for d in set(digits[i]):
            pref[i + 1, d] += 1
    feats["PREF"] = pref
    # 数字平均遗漏间隔 μ (E6 用)
    cnt = np.zeros(10, dtype=np.float64)
    for d in digits:
        cnt[d[0]] += 1; cnt[d[1]] += 1; cnt[d[2]] += 1
    feats["MUMISS"] = np.where(cnt > 0, N / np.maximum(cnt, 1), 1.0)
    return feats

# ---------------------------------------------------------------- pred 预计算

def precompute_pred(F, feats, digits, conds, N):
    nf = len(F)
    pred = np.zeros((nf, N + 1), dtype=np.int8)
    ctx = FM.RollingCtx(digits, feats, A_W, GAMMA, SLOPE_W, SUM_W, AR_W, conds)
    fn_ids = [i for i, f in enumerate(F) if f.fn is not None and not f.dynamic]
    vec_ids = [i for i, f in enumerate(F) if f.vec is not None and not f.dynamic]
    atomic_ids = fn_ids + vec_ids
    # 预热
    for idx in range(0, MIN_T):
        ctx.add(idx)
    t0 = time.time()
    for t in range(MIN_T, N + 1):
        if t > MIN_T:
            ctx.add(t - 1)
        for i in fn_ids:
            pred[i, t] = F[i].fn(ctx, feats, t)
    print(f"[pred] 滚动公式 {len(fn_ids)} 个 x 期 {N+1-MIN_T} 完成, 用时 {time.time()-t0:.1f}s")
    t1 = time.time()
    for i in vec_ids:
        pred[i, :] = F[i].vec(feats, N)
    print(f"[pred] 向量化公式 {len(vec_ids)} 个完成, 用时 {time.time()-t1:.2f}s")
    # G1a / G1b 静态投票
    g1a = next(i for i, f in enumerate(F) if f.id == "G1a_allvote")
    g1b = next(i for i, f in enumerate(F) if f.id == "G1b_bestvote")
    fams = [f.family for i, f in enumerate(F) if i in atomic_ids]
    fam_set = sorted(set(fams))
    for t in range(MIN_T, N + 1):
        votes = np.bincount(pred[atomic_ids, t].astype(np.int64), minlength=10)
        pred[g1a, t] = int(np.argmax(votes))
        fam_codes = []
        for fam in fam_set:
            idxs = [i for i in atomic_ids if F[i].family == fam]
            v = np.bincount(pred[idxs, t].astype(np.int64), minlength=10)
            fam_codes.append(int(np.argmax(v)))
        v2 = np.bincount(fam_codes, minlength=10)
        pred[g1b, t] = int(np.argmax(v2))
    return pred, ctx, atomic_ids

# ---------------------------------------------------------------- 评分

def score_window(hit_slice):
    """hit_slice: (nf, W) bool -> score, hit_rate, maxrun, rec50"""
    nf, W = hit_slice.shape
    hit_rate = hit_slice.mean(axis=1)
    lose = (~hit_slice).astype(np.int8)
    run = np.zeros(nf, dtype=np.int32)
    maxrun = np.zeros(nf, dtype=np.int32)
    for i in range(W):
        run = (run + 1) * lose[:, i]
        maxrun = np.maximum(maxrun, run)
    if W >= 50:
        rec50 = hit_slice[:, -50:].mean(axis=1)
    else:
        rec50 = hit_rate
    score = hit_rate - L1 * (maxrun / 20.0) - L2 * (1.0 - rec50)
    return score, hit_rate, maxrun, rec50

# ---------------------------------------------------------------- 回测

def build_hit_matrix(F, pred, digits, N):
    nf = len(F)
    hit = np.zeros((nf, N), dtype=bool)
    for t in range(N):
        m = np.zeros(10, dtype=bool)
        m[digits[t][0]] = True; m[digits[t][1]] = True; m[digits[t][2]] = True
        hit[:, t] = ~m[pred[:, t]]
    return hit

def hedge_kill(win, k, smooth, t, hit, pred, pool_arr):
    """Hedge 加权投票 (学习自杀和尾项目):
    在窗口 [t-WIN, t-1] 内取命中率 TopK 公式为专家, 权重=近窗命中率(下限smooth),
    专家们对 t 期的杀码投票, 得票最高者 = 最终杀码。
    返回 (kill, experts, weights, votes, top_rate)
      experts: 参与投票的公式全局下标
      weights: 对应权重
      votes:   0-9 票数分布
    """
    lo = t - win
    rates = hit[pool_arr, lo:t].mean(axis=1)
    ti = np.argsort(-rates)[:k]
    sel = pool_arr[ti]
    w = np.maximum(rates[ti], smooth)
    kills = pred[sel, t]
    votes = np.bincount(kills, weights=w, minlength=10)
    kill = int(np.argmax(votes))
    return kill, sel.tolist(), w.tolist(), votes, float(rates[ti[0]])


def run_backtest(issues, digits, feats, F, pred, atomic_ids):
    """Hedge 加权投票主机制: 200期逐期真实回测 (严格 walk-forward)。
    附对比: 固定公式(选择偏差口径) / 动态Top1(WIN=100)。"""
    N = len(digits)
    hit = build_hit_matrix(F, pred, digits, N)
    pool_arr = np.array([i for i in atomic_ids if not F[i].dynamic])
    t_end = N - 1
    t_start = t_end - W_SCORE + 1
    # ---- Hedge 逐期回测 ----
    rows = []
    for t in range(t_start, t_end + 1):
        kill, sel, w, votes, top_rate = hedge_kill(
            HEDGE_WIN, HEDGE_K, HEDGE_SMOOTH, t, hit, pred, pool_arr)
        win = kill not in digits[t]
        top_i = sel[0]
        # Top3 票码: 票王(正式kill) + 按票数第2/第3
        v_int = [int(x) for x in votes]
        order = sorted(range(10), key=lambda x: -v_int[x])
        top3 = [kill] + [c for c in order if c != kill][:2]
        rows.append({
            "issue": int(issues[t]),
            "num": f"{digits[t][0]}{digits[t][1]}{digits[t][2]}",
            "kill": kill,
            "hit": bool(win),
            "top3": top3,
            "fid": F[top_i].id,
            "fname": F[top_i].name,
            "fam": F[top_i].family,
            "rate200": round(top_rate, 4),
            "n_exp": len(sel),
            "votes": v_int,
        })
    # ---- 汇总 ----
    hits = [r["hit"] for r in rows]
    rate = sum(hits) / len(hits)
    cur_win = 0; cur_lose = 0
    for h in reversed(hits):
        if h: cur_win += 1
        else: break
    for h in reversed(hits):
        if not h: cur_lose += 1
        else: break
    max_win = max_lose = 0
    cw = cl = 0
    for h in hits:
        if h:
            cw += 1; cl = 0
        else:
            cl += 1; cw = 0
        max_win = max(max_win, cw)
        max_lose = max(max_lose, cl)
    pool_avg = float(hit[pool_arr, N - W_SCORE:N].mean())
    # ---- 对比1: 固定公式 (选择偏差口径) ----
    last_hr = hit[pool_arr, N - W_SCORE:N].mean(axis=1)
    top_fixed = pool_arr[int(np.argmax(last_hr))]
    fixed_hits = sum(1 for t in range(t_start, t_end + 1)
                     if int(pred[top_fixed, t]) not in digits[t])
    fixed_rate = fixed_hits / (t_end - t_start + 1)
    fixed_hist = float(hit[top_fixed, 600:N].mean()) if N > 600 else fixed_rate
    # ---- 对比2: 动态Top1 (WIN=TOP1_WIN, 严格 walk-forward) ----
    dyn_hits = 0
    for t in range(t_start, t_end + 1):
        lo = t - TOP1_WIN
        r = hit[pool_arr, lo:t].mean(axis=1)
        i = pool_arr[int(np.argmax(r))]
        if int(pred[i, t]) not in digits[t]:
            dyn_hits += 1
    dyn_rate = dyn_hits / (t_end - t_start + 1)
    # ---- Hedge 长期参考 (最近1000期) ----
    hedge_hits = 0
    for t in range(N - 1000, t_end + 1):
        k, *_ = hedge_kill(HEDGE_WIN, HEDGE_K, HEDGE_SMOOTH, t, hit, pred, pool_arr)
        if k not in digits[t]:
            hedge_hits += 1
    hedge1000 = hedge_hits / 1000
    summary = {
        "hit": int(sum(hits)), "total": len(hits), "rate": round(rate, 4),
        "baseline": BASELINE, "pool_avg": round(pool_avg, 4),
        "hedge1000": round(hedge1000, 4),
        "fixed_rate": round(fixed_rate, 4),
        "fixed_hist": round(fixed_hist, 4),
        "fixed_id": F[top_fixed].id, "fixed_name": F[top_fixed].name,
        "dyn_rate": round(dyn_rate, 4),
        "max_win": max_win, "max_lose": max_lose,
        "cur_win": cur_win, "cur_lose": cur_lose,
        "formula_id": F[top_fixed].id, "formula_name": F[top_fixed].name,
    }
    # ---- 榜单: 当前窗口(近90期) Top50 专家 ----
    cur_rates = hit[pool_arr, N - HEDGE_WIN:N].mean(axis=1)
    order = np.argsort(-cur_rates)
    leaderboard = []
    for pi in order:
        if len(leaderboard) >= 50:
            break
        i = int(pool_arr[int(pi)])
        leaderboard.append({
            "fid": F[i].id, "fname": F[i].name, "fam": F[i].family,
            "rate200": round(float(cur_rates[int(pi)]), 4),
            "hist": round(float(hit[i, 600:N].mean()), 4) if N > 600 else 0.0,
        })
    return summary, rows, leaderboard, top_fixed, hit

# ---------------------------------------------------------------- 下一期预测

def next_prediction(issues, digits, feats, F, pred, atomic_ids, hit, top_fixed):
    """Hedge 加权投票预测下一期; top_fixed 仅用于展示固定公式对比"""
    N = len(digits)
    t = N
    target_issue = int(issues[-1]) + 1
    pool_arr = np.array([i for i in atomic_ids if not F[i].dynamic])
    # Hedge 主预测
    kill, sel, w, votes, top_rate = hedge_kill(
        HEDGE_WIN, HEDGE_K, HEDGE_SMOOTH, t, hit, pred, pool_arr)
    # 参与投票的专家明细
    experts = []
    for i, wi in zip(sel, w):
        experts.append({
            "fid": F[i].id, "fname": F[i].name, "fam": F[i].family,
            "kill": int(pred[i, t]), "weight": round(wi, 4),
        })
    # 动态Top1 参考 (WIN=TOP1_WIN)
    lo = t - TOP1_WIN
    r = hit[pool_arr, lo:t].mean(axis=1)
    top1_i = pool_arr[int(np.argmax(r))]
    refs = [
        {"id": "Hedge", "name": f"Hedge投票(K={HEDGE_K})", "kill": kill},
        {"id": "DynTop1", "name": f"动态Top1(WIN={TOP1_WIN})", "kill": int(pred[top1_i, t])},
        {"id": "Fixed", "name": f"固定公式({F[top_fixed].name})", "kill": int(pred[top_fixed, t])},
    ]
    # Top3 票数参考
    top3_kills = [int(np.argsort(-votes)[i]) for i in range(3)]
    return {
        "target_issue": target_issue,
        "kill": kill,
        "formula_id": "Hedge",
        "formula_name": f"Hedge {HEDGE_K}专家加权投票",
        "family": "H",
        "win_rate_200": round(top_rate, 4),
        "top3_vote": top3_kills,
        "top3_vote_dist": [int(x) for x in votes],
        "n_experts": len(experts),
        "experts": experts,
        "refs": refs,
    }

# ---------------------------------------------------------------- 缓存

def fingerprint(issues):
    return f"{len(issues)}_{issues[-1] if issues else 0}"

def load_cache():
    if os.path.exists(CACHE_JSON):
        try:
            with open(CACHE_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_cache(data):
    os.makedirs(os.path.dirname(CACHE_JSON), exist_ok=True)
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# ---------------------------------------------------------------- 总入口

def compute_all(force=False, progress=None):
    """完整计算流程; 返回结果 dict。progress: callable(msg)"""
    def _p(msg):
        if progress:
            progress(msg)
    issues, digits = load_csv()
    fp = fingerprint(issues)
    if not force:
        cache = load_cache()
        if cache and cache.get("fingerprint") == fp:
            return cache
    _p("预计算特征...")
    t0 = time.time()
    feats = compute_features(issues, digits)
    F, conds = FM.build_all_formulas(feats)
    _p(f"公式池构建完成: {len(F)} 个公式")
    N = len(digits)
    pred, ctx, atomic_ids = precompute_pred(F, feats, digits, conds, N)
    _p(f"pred 预计算完成 ({time.time()-t0:.0f}s)")
    _p("Hedge 加权投票回测...")
    summary, rows, leaderboard, top_fixed, hit = run_backtest(issues, digits, feats, F, pred, atomic_ids)
    _p("计算下一期预测...")
    nxt = next_prediction(issues, digits, feats, F, pred, atomic_ids, hit, top_fixed)
    rows.sort(key=lambda r: r["issue"], reverse=True)  # 近期在上
    result = {
        "fingerprint": fp,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_last_issue": int(issues[-1]),
        "data_count": N,
        "formula_count": len(F),
        "baseline": BASELINE,
        "summary": summary,
        "next": nxt,
        "rows": rows,
        "leaderboard": leaderboard,
    }
    save_cache(result)
    _p(f"完成, 总用时 {time.time()-t0:.0f}s")
    return result

if __name__ == "__main__":
    res = compute_all(force=True)
    s = res["summary"]
    n = res["next"]
    print("=" * 60)
    print(f"数据: {res['data_count']} 期, 末期 {res['data_last_issue']}")
    print(f"公式池: {res['formula_count']} 个")
    print(f"机制: Hedge {HEDGE_K}专家加权投票 (WIN={HEDGE_WIN}, 权重下限{HEDGE_SMOOTH})")
    print(f"200期回测(walk-forward): {s['hit']}/{s['total']} = {s['rate']*100:.2f}%  (基线 {s['baseline']*100:.1f}%, 池均值 {s['pool_avg']*100:.2f}%)")
    print(f"Hedge近1000期: {s['hedge1000']*100:.2f}% | 动态Top1(WIN={TOP1_WIN}): {s['dyn_rate']*100:.2f}% | 固定公式(选择偏差): {s['fixed_rate']*100:.2f}% (全史{s['fixed_hist']*100:.2f}%)")
    print(f"最大连中 {s['max_win']}, 最大连错 {s['max_lose']}, 当前连中 {s['cur_win']}, 当前连错 {s['cur_lose']}")
    print(f"下一期 {n['target_issue']}: 通杀 {n['kill']}  <- {n['formula_name']} ({n['n_experts']}专家)")
    print(f"Top3 票数: {n['top3_vote_dist']} | 参考: " + " | ".join(f"{r['name']}→{r['kill']}" for r in n['refs']))
