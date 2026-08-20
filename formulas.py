# -*- coding: utf-8 -*-
"""
formulas.py — 福彩3D通杀一码 公式池 v2 (扩大版, 目标 6000+)
=============================================================
统一接口:
  fn(rc, feats, t) -> int   (滚动型公式, rc=RollingCtx, 只用 <t 的数据)
  vec(feats, N) -> np.array(N+1)  (向量化纯索引公式, pred[t] 直接取值)

八族: A频率热冷 B条件转移 C算术(向量化) D形态路数 E周期节律 F趋势统计
      G集成投票 H组合条件
"""
import numpy as np
from dataclasses import dataclass, field
from collections import deque

# ---------------------------------------------------------------- 基础工具

DIG = range(10)

def argmin10(v):
    """返回最小值下标 (纯Python, 支持任意长度, 10元素比numpy快3倍)"""
    best = 0
    bv = v[0]
    for i in range(1, len(v)):
        if v[i] < bv:
            bv = v[i]
            best = i
    return best

def argmax10(v):
    best = 0
    bv = v[0]
    for i in range(1, len(v)):
        if v[i] > bv:
            bv = v[i]
            best = i
    return best

@dataclass
class Formula:
    id: str
    name: str
    family: str
    fn: object = None
    vec: object = None
    dynamic: bool = False
    meta: dict = field(default_factory=dict)

# ---------------------------------------------------------------- 向量化辅助

def _vshift(feats, N, src, k=0, lag=1, mul=1, mapfn=None):
    """out[t] = mapfn((mul*feats[src][t-lag] + k) % 10); t<lag 时为 0"""
    v = (mul * feats[src] + k) % 10
    if mapfn is not None:
        v = mapfn(v)
    out = np.zeros(N + 1, dtype=np.int8)
    out[lag:] = v[:N - lag + 1]
    return out

def _c1v(feats, N, a, b, c, k):
    v = (a * feats["H"] + b * feats["T"] + c * feats["O"] + k) % 10
    out = np.zeros(N + 1, dtype=np.int8)
    out[1:] = v
    return out

def _c6v(feats, N, lag, a, b, c, k):
    v = (a * feats["H"] + b * feats["T"] + c * feats["O"] + k) % 10
    out = np.zeros(N + 1, dtype=np.int8)
    out[lag:] = v[:N - lag + 1]
    return out

def _c7v(feats, N, a, b, c, mp):
    v = (a * feats["H"] + b * feats["T"] + c * feats["O"]) % 10
    v = (9 - v) % 10 if mp == "inv" else (v + 5) % 10
    out = np.zeros(N + 1, dtype=np.int8)
    out[1:] = v
    return out

def _e1v(feats, N, var, n):
    v = feats[var]
    out = np.zeros(N + 1, dtype=np.int8)
    out[n:] = v[:N - n + 1]
    return out

# ---------------------------------------------------------------- 滚动计数器

class FreqRoller:
    """最近 W 期三码合并/分位频率滚动计数器"""
    __slots__ = ("W", "cnt", "pos", "ring")
    def __init__(self, W):
        self.W = W
        self.cnt = np.zeros(10, dtype=np.int32)
        self.pos = np.zeros((3, 10), dtype=np.int32)
        self.ring = deque()
    def add(self, dg):
        h, t, o = dg
        self.cnt[h] += 1; self.cnt[t] += 1; self.cnt[o] += 1
        self.pos[0, h] += 1; self.pos[1, t] += 1; self.pos[2, o] += 1
        self.ring.append(dg)
        if len(self.ring) > self.W:
            h2, t2, o2 = self.ring.popleft()
            self.cnt[h2] -= 1; self.cnt[t2] -= 1; self.cnt[o2] -= 1
            self.pos[0, h2] -= 1; self.pos[1, t2] -= 1; self.pos[2, o2] -= 1

class DecayRoller:
    __slots__ = ("g", "cnt")
    def __init__(self, g):
        self.g = g
        self.cnt = np.zeros(10, dtype=np.float64)
    def add(self, dg):
        self.cnt *= self.g
        self.cnt[dg[0]] += 1.0; self.cnt[dg[1]] += 1.0; self.cnt[dg[2]] += 1.0

class SumRoller:
    __slots__ = ("W", "s", "ring")
    def __init__(self, W):
        self.W = W
        self.s = np.zeros(3, dtype=np.float64)
        self.ring = deque()
    def add(self, dg):
        self.s[0] += dg[0]; self.s[1] += dg[1]; self.s[2] += dg[2]
        self.ring.append(dg)
        if len(self.ring) > self.W:
            d = self.ring.popleft()
            self.s[0] -= d[0]; self.s[1] -= d[1]; self.s[2] -= d[2]

class SlopeRoller:
    """最近 W 期每个数字出现序列对时间回归斜率"""
    __slots__ = ("W", "n", "sum_t", "denom", "idx", "ring")
    def __init__(self, W):
        self.W = W
        self.n = np.zeros(10, dtype=np.float64)
        self.sum_t = np.zeros(10, dtype=np.float64)
        self.denom = (W * (W * W - 1)) / 12.0
        self.idx = 0
        self.ring = deque()
    def add(self, dg):
        i = float(self.idx)
        self.n[dg[0]] += 1; self.n[dg[1]] += 1; self.n[dg[2]] += 1
        self.sum_t[dg[0]] += i; self.sum_t[dg[1]] += i; self.sum_t[dg[2]] += i
        self.ring.append(dg)
        self.idx += 1
        if len(self.ring) > self.W:
            d = self.ring.popleft()
            j = i - self.W
            self.n[d[0]] -= 1; self.n[d[1]] -= 1; self.n[d[2]] -= 1
            self.sum_t[d[0]] -= j; self.sum_t[d[1]] -= j; self.sum_t[d[2]] -= j
    def slope(self, d):
        if self.n[d] == 0 or self.denom <= 0:
            return 0.0
        mean_t = (self.W - 1) / 2.0
        return (self.sum_t[d] - self.n[d] * mean_t) / self.denom

class ARRoller:
    __slots__ = ("W", "sx", "sy", "sxy", "sx2", "ring")
    def __init__(self, W):
        self.W = W
        self.sx = self.sy = self.sxy = self.sx2 = 0.0
        self.ring = deque()
    def add(self, prev_x, x):
        self.sx += prev_x; self.sy += x
        self.sxy += prev_x * x; self.sx2 += prev_x * prev_x
        self.ring.append((prev_x, x))
        if len(self.ring) > self.W:
            p, q = self.ring.popleft()
            self.sx -= p; self.sy -= q; self.sxy -= p * q; self.sx2 -= p * p
    def coef(self):
        n = self.W
        denom = n * self.sx2 - self.sx * self.sx
        if abs(denom) < 1e-9:
            return 0.0, self.sy / n
        b = (n * self.sxy - self.sx * self.sy) / denom
        a = (self.sy - b * self.sx) / n
        return b, a

class CondRoller:
    """条件转移: order=1 X_{τ-1}, order=2 X_{τ-2}, order=0 X_τ(同期)"""
    __slots__ = ("W", "order", "m", "cnt", "n", "ring")
    def __init__(self, W, order, m):
        self.W = W; self.order = order; self.m = m
        self.cnt = np.zeros((m, 10), dtype=np.int32)
        self.n = np.zeros(m, dtype=np.int32)
        self.ring = deque()
    def add(self, s0, s1, s2, dg):
        if self.order == 0:
            s = s0
        elif self.order == 1:
            s = s1
        else:
            s = s2
        np.add.at(self.cnt[s], dg, 1)
        self.n[s] += 1
        self.ring.append((s, dg))
        if len(self.ring) > self.W:
            ps, d = self.ring.popleft()
            np.add.at(self.cnt[ps], d, -1)
            self.n[ps] -= 1
    def vec(self, s):
        return self.cnt[s], self.n[s]

# ---------------------------------------------------------------- 滚动上下文

class RollingCtx:
    def __init__(self, digits, feats, A_W, GAMMA, SLOPE_W, SUM_W, AR_W, CONDS):
        self.digits = digits
        self.feats = feats
        self.freq = {W: FreqRoller(W) for W in A_W}
        self.decay = {g: DecayRoller(g) for g in GAMMA}
        self.slope = {W: SlopeRoller(W) for W in SLOPE_W}
        self.sums = {W: SumRoller(W) for W in SUM_W}
        self.ar = {(pos, W): ARRoller(W) for pos in range(3) for W in AR_W}
        self.cond = {}
        for key, order, W, m, _fk in CONDS:
            self.cond[(key, order, W)] = CondRoller(W, order, m)
        self.CONDS = CONDS
    def add(self, idx):
        dg = self.digits[idx]
        for r in self.freq.values():
            r.add(dg)
        for r in self.decay.values():
            r.add(dg)
        for r in self.slope.values():
            r.add(dg)
        for r in self.sums.values():
            r.add(dg)
        if idx >= 1:
            for pos, W in self.ar:
                r = self.ar[(pos, W)]
                arr = self.feats[("H", "T", "O")[pos]]
                r.add(int(arr[idx - 1]), dg[pos])
        for key, order, W, m, fk in self.CONDS:
            f = self.feats
            cr = self.cond[(key, order, W)]
            dga = np.asarray(dg, dtype=np.int32)
            if order == 0:
                s0 = int(f[fk][idx])
                cr.add(s0, 0, 0, dga)
            else:
                s1 = int(f[fk][idx - 1]) if idx >= 1 else 0
                s2 = int(f[fk][idx - 2]) if idx >= 2 else 0
                cr.add(0, s1, s2, dga)

# ---------------------------------------------------------------- 通用条件公式构造器

def _cond_formula(rc, feats, t, key, fk, order, W, target, alpha):
    """条件转移查询: s = X[t-order]; 杀条件频率最低/最高 (拉普拉斯平滑)"""
    cr = rc.cond[(key, order, W)]
    if order == 0:
        s = int(feats[fk][t])
    elif order == 1:
        s = int(feats[fk][t - 1])
    else:
        s = int(feats[fk][t - 2])
    vec, n = cr.vec(s)
    p = (vec.astype(np.float64) + alpha) / (n + 10.0 * alpha + 1e-9)
    return argmin10(p) if target == "cold" else argmax10(p)

# ---------------------------------------------------------------- 族 A: 频率/热冷

def build_family_A(feats):
    out = []
    A_W = [8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80,
           90, 100, 110, 120, 130, 150, 160, 180, 200]
    # A1/A1b 冷码 + A2/A2b 热码反杀 (25W × 4)
    for W in A_W:
        def f1(rc, feats, t, W=W):
            cnt = rc.freq[W].cnt
            mn = int(cnt.min())
            cand = [d for d in DIG if cnt[d] == mn]
            m = feats["missM"]
            return max(cand, key=lambda d: m[t][d])
        out.append(Formula(f"A1_cold{W}", f"近{W}期冷码", "A", f1))
        def f1b(rc, feats, t, W=W):
            cnt = rc.freq[W].cnt
            mn = int(cnt.min())
            cand = [d for d in DIG if cnt[d] == mn]
            m = feats["missM"]
            return min(cand, key=lambda d: m[t][d])
        out.append(Formula(f"A1b_cold{W}", f"近{W}期冷码·新", "A", f1b))
        def f2(rc, feats, t, W=W):
            cnt = rc.freq[W].cnt
            mx = int(cnt.max())
            cand = [d for d in DIG if cnt[d] == mx]
            m = feats["missM"]
            return max(cand, key=lambda d: m[t][d])
        out.append(Formula(f"A2_hot{W}", f"近{W}期热码反杀", "A", f2))
        def f2b(rc, feats, t, W=W):
            cnt = rc.freq[W].cnt
            mx = int(cnt.max())
            cand = [d for d in DIG if cnt[d] == mx]
            m = feats["missM"]
            return min(cand, key=lambda d: m[t][d])
        out.append(Formula(f"A2b_hot{W}", f"近{W}期热码反杀·新", "A", f2b))
    # A3 分位频率
    for pos, pn in enumerate(("百", "十", "个")):
        for hot in (False, True):
            for W in A_W:
                def f3(rc, feats, t, pos=pos, hot=hot, W=W):
                    v = rc.freq[W].pos[pos]
                    m = feats["missP"][t][pos]
                    if hot:
                        mx = int(v.max()); cand = [d for d in DIG if v[d] == mx]
                    else:
                        mn = int(v.min()); cand = [d for d in DIG if v[d] == mn]
                    return max(cand, key=lambda d: m[d])
                kind = "热" if hot else "冷"
                out.append(Formula(f"A3_{pn}{kind}{W}", f"{pn}位近{W}期{kind}码", "A", f3))
    # A4 指数衰减频率
    for g in (0.88, 0.90, 0.92, 0.93, 0.95, 0.97, 0.99):
        for hot in (False, True):
            def f4(rc, feats, t, g=g, hot=hot):
                v = rc.decay[g].cnt
                return argmax10(v) if hot else argmin10(v)
            kind = "热" if hot else "冷"
            out.append(Formula(f"A4_decay{g}_{kind}", f"衰减频率{kind}(γ={g})", "A", f4))
    # A5 遗漏
    def f5a(rc, feats, t):
        m = feats["missM"][t]
        mx = int(m.max())
        cand = [d for d in DIG if m[d] == mx]
        cnt = rc.freq[200].cnt
        return min(cand, key=lambda d: cnt[d])
    out.append(Formula("A5_missMax", "遗漏最大·冷码优先", "A", f5a))
    def f5b(rc, feats, t):
        m = feats["missM"][t]
        mn = int(m.min())
        cand = [d for d in DIG if m[d] == mn]
        cnt = rc.freq[200].cnt
        return max(cand, key=lambda d: cnt[d])
    out.append(Formula("A5_missMin", "遗漏最小·热码优先", "A", f5b))
    for pos, pn in enumerate(("百", "十", "个")):
        for big in (True, False):
            def f5p(rc, feats, t, pos=pos, big=big):
                m = feats["missP"][t][pos]
                if big:
                    mx = int(m.max()); cand = [d for d in DIG if m[d] == mx]
                else:
                    mn = int(m.min()); cand = [d for d in DIG if m[d] == mn]
                cnt = rc.freq[200].pos[pos]
                return min(cand, key=lambda d: cnt[d]) if big else max(cand, key=lambda d: cnt[d])
            kind = "大" if big else "小"
            out.append(Formula(f"A5_{pn}miss{kind}", f"{pn}位遗漏{kind}", "A", f5p))
    for thr in (6, 8, 10, 12, 15, 18):
        for big in (True, False):
            def f5t(rc, feats, t, thr=thr, big=big):
                m = feats["missM"][t]
                if big:
                    cand = [d for d in DIG if m[d] >= thr]
                    if not cand:
                        cand = [d for d in DIG]
                    mx = max(m[d] for d in cand)
                    cand = [d for d in cand if m[d] == mx]
                else:
                    cand = [d for d in DIG if m[d] < thr]
                    if not cand:
                        cand = [d for d in DIG]
                    mn = min(m[d] for d in cand)
                    cand = [d for d in cand if m[d] == mn]
                cnt = rc.freq[100].cnt
                return min(cand, key=lambda d: cnt[d])
            kind = "逾" if big else "新"
            out.append(Formula(f"A5_thr{thr}{kind}", f"遗漏≥{thr}期·{kind}", "A", f5t))
    # A6 频率-遗漏复合
    for alpha in (-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0):
        for W in (10, 20, 30, 50, 100, 200):
            def f6(rc, feats, t, alpha=alpha, W=W):
                cnt = rc.freq[W].cnt.astype(np.float64)
                score = cnt + alpha * feats["missM"][t]
                return argmin10(score)
            out.append(Formula(f"A6_comp{alpha}_{W}", f"频率+{alpha}·遗漏(W{W})", "A", f6))
    # A7 排名均值
    for W in (15, 20, 30, 50, 100, 150, 200):
        for hot in (False, True):
            def f7(rc, feats, t, W=W, hot=hot):
                pos = rc.freq[W].pos
                rank_sum = np.zeros(10, dtype=np.float64)
                for p in range(3):
                    order = np.argsort(np.argsort(-pos[p])) if hot else np.argsort(np.argsort(pos[p]))
                    rank_sum += order
                return argmax10(rank_sum) if hot else argmin10(rank_sum)
            kind = "热" if hot else "冷"
            out.append(Formula(f"A7_rank{W}{kind}", f"排名均值{W}{kind}", "A", f7))
    # A8 近k期未出
    for k in (2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 20):
        for big in (True, False):
            def f8(rc, feats, t, k=k, big=big):
                m = feats["missM"][t]
                miss_set = [d for d in DIG if m[d] >= k]
                if not miss_set:
                    miss_set = list(DIG)
                if big:
                    mx = max(m[d] for d in miss_set)
                    cand = [d for d in miss_set if m[d] == mx]
                else:
                    mn = min(m[d] for d in miss_set)
                    cand = [d for d in miss_set if m[d] == mn]
                cnt = rc.freq[100].cnt
                return min(cand, key=lambda d: cnt[d])
            kind = "大" if big else "小"
            out.append(Formula(f"A8_miss{k}{kind}", f"近{k}期未出·miss{kind}", "A", f8))
    # A9 频率中位数
    for W in (20, 50, 100, 200):
        for side in ("low", "high"):
            def f9(rc, feats, t, W=W, side=side):
                order = np.argsort(rc.freq[W].cnt)
                idx = 5 if side == "low" else 4
                return int(order[idx])
            out.append(Formula(f"A9_med{W}_{side}", f"频率中位{W}({side})", "A", f9))
    # A10 双窗口差异
    for (W1, W2) in ((10, 20), (20, 40), (30, 60), (50, 100), (100, 200), (150, 200)):
        for hot in (True, False):
            def f10(rc, feats, t, W1=W1, W2=W2, hot=hot):
                diff = rc.freq[W1].cnt - rc.freq[W2].cnt
                return argmax10(diff) if hot else argmin10(diff)
            kind = "转热" if hot else "转冷"
            out.append(Formula(f"A10_diff{W1}v{W2}{kind}", f"短{W1}/长{W2}{kind}", "A", f10))
    # A11 三位置合并
    for W in (10, 20, 30, 50, 100, 200):
        for hot in (False, True):
            def f11(rc, feats, t, W=W, hot=hot):
                s = rc.freq[W].pos.sum(axis=0)
                if hot:
                    mx = int(s.max()); cand = [d for d in DIG if s[d] == mx]
                else:
                    mn = int(s.min()); cand = [d for d in DIG if s[d] == mn]
                m = feats["missM"][t]
                return max(cand, key=lambda d: m[d])
            kind = "热" if hot else "冷"
            out.append(Formula(f"A11_allpos{W}{kind}", f"三位合并{W}{kind}", "A", f11))
    # A12 窗口内从未出现数字(遗漏最大) / 该窗口出现数字中最热
    for W in (10, 20, 30, 50, 100, 200):
        for mode in ("never", "always"):
            def f12(rc, feats, t, W=W, mode=mode):
                cnt = rc.freq[W].cnt
                m = feats["missM"][t]
                if mode == "never":
                    cand = [d for d in DIG if cnt[d] == 0]
                    if not cand:
                        cand = list(DIG)
                    return max(cand, key=lambda d: m[d])
                cand = [d for d in DIG if cnt[d] > 0]
                if not cand:
                    cand = list(DIG)
                return min(cand, key=lambda d: m[d])
            kind = "未出" if mode == "never" else "常出"
            out.append(Formula(f"A12_{W}_{mode}", f"窗口{W}{kind}", "A", f12))
    return out

# ---------------------------------------------------------------- 族 B: 马尔可夫/条件转移

def build_family_B(feats):
    out = []
    COND_DEFS = [
        ("sw", 10, "和尾", "SW"), ("kd", 10, "跨度", "K"),
        ("h", 10, "百位", "H"), ("t", 10, "十位", "T"), ("o", 10, "个位", "O"),
        ("par", 8, "奇偶形态", "PAR8"), ("sz", 8, "大小形态", "SZ8"),
        ("f3", 3, "形态", "F3"), ("sv", 28, "和值", "S"),
        ("dh", 10, "百十差", "DHT"), ("dt", 10, "十个差", "DTO"), ("do", 10, "百个差", "DHO"),
        ("p3", 10, "乘积尾", "P3M10"),
        ("sk", 100, "和尾×跨度", "SWK"),
        ("rp", 4, "重码数", "RP"),
        # 新增条件族
        ("par3", 4, "奇偶比", "PAR3"), ("sz3", 4, "大小比", "SZ3"),
        ("sumod", 2, "和值奇偶", "SUMOD"), ("kod", 2, "跨度奇偶", "KOD"),
        ("kbig", 2, "跨度大小", "KBIG"), ("cont", 2, "连号", "CONT"),
        ("perm", 6, "三码排列", "PERM"), ("ndig", 3, "不同码数", "NDIG"),
        ("ampk", 10, "跨度振幅", "AMPK"),
    ]
    for key, m, cname, fk in COND_DEFS:
        for order in (1, 2):
            for W in (100, 200):
                for target in ("cold", "hot"):
                    ALPHAS = (0.2, 0.5, 1.0, 2.0)
                    _cache = {}
                    for ai, alpha in enumerate(ALPHAS):
                        tg = "冷" if target == "cold" else "热"
                        def mk(ai=ai, alpha=alpha, key=key, fk=fk, order=order, ALPHAS=ALPHAS,
                               W=W, target=target, _cache=_cache):
                            def fb(rc, feats, t):
                                return _cache_get(_cache, rc, feats, t, key, fk,
                                                  order, W, target, ALPHAS)[ai]
                            return fb
                        out.append(Formula(
                            f"B_{key}_o{order}_w{W}_{tg}_a{alpha}",
                            f"{cname}转移{order}阶{W}期·{tg}α{alpha}", "B", mk()))
    return out


def _cache_get(_cache, rc, feats, t, key, fk, order, W, target, ALPHAS):
    """B/H 族共享查询缓存: 同一 (条件,t) 只算一次 4 个 α 结果"""
    ck = t
    if ck not in _cache:
        cr = rc.cond[(key, order, W)]
        if order == 1:
            s = int(feats[fk][t - 1])
        elif order == 2:
            s = int(feats[fk][t - 2])
        else:
            s = int(feats[fk][t])
        vec, n = cr.vec(s)
        res = []
        for alpha in ALPHAS:
            p = (vec + alpha) / (n + 10.0 * alpha + 1e-9)
            res.append(argmin10(p) if target == "cold" else argmax10(p))
        _cache[ck] = res
        if len(_cache) > 1024:
            _cache.clear()
            _cache[ck] = res
    return _cache[ck]

# ---------------------------------------------------------------- 族 C: 算术关系 (向量化)

def build_family_C(feats):
    out = []
    # C1 线性组合: k 全取 0-9
    coeffs = []
    for a in (-3, -2, -1, 0, 1, 2, 3):
        for b in (-3, -2, -1, 0, 1, 2, 3):
            for c in (-3, -2, -1, 0, 1, 2, 3):
                if a == 0 and b == 0 and c == 0:
                    continue
                coeffs.append((a, b, c))
    for (a, b, c) in coeffs:
        for k in range(10):
            out.append(Formula(f"C1_{a}_{b}_{c}_{k}", f"线性({a}百{b}十{c}个+{k})",
                               "C", vec=lambda feats, N, a=a, b=b, c=c, k=k: _c1v(feats, N, a, b, c, k)))
    # C2 和值系
    for name, arr in (("S", "S"), ("SW", "SW")):
        for mul in (1, 2, 3):
            for k in DIG:
                out.append(Formula(f"C2_{name}x{mul}_{k}", f"{name}×{mul}+{k}",
                                   "C", vec=lambda feats, N, arr=arr, mul=mul, k=k: _vshift(feats, N, arr, k, mul=mul)))
    # C3 跨度系
    for k in DIG:
        out.append(Formula(f"C3_K_{k}", f"跨度+{k}", "C",
                           vec=lambda feats, N, k=k: _vshift(feats, N, "K", k)))
        out.append(Formula(f"C3_MX_{k}", f"最大+最小+{k}", "C",
                           vec=lambda feats, N, k=k: _vshift(feats, N, "MXM", k)))
    # C4 乘积系
    for cid, arr in (("P3M10", "P3M10"), ("P3M9", "P3M9"), ("P3M8", "P3M8"),
                     ("P3M7", "P3M7"), ("P3T10", "P3T10"), ("HTM10", "HTM10"),
                     ("TOM10", "TOM10"), ("HOM10", "HOM10")):
        out.append(Formula(f"C4_{cid}", f"乘积{arr}", "C",
                           vec=lambda feats, N, arr=arr: _vshift(feats, N, arr)))
    # C5 位间运算
    for cid, arr in (("DHT", "DHT"), ("DTO", "DTO"), ("DHO", "DHO"),
                     ("HTS", "HTS"), ("TOS", "TOS"), ("HOS", "HOS"),
                     ("HTD", "HTD"), ("TOD", "TOD"), ("HOD", "HOD")):
        for k in DIG:
            out.append(Formula(f"C5_{cid}_{k}", f"{cid}+{k}", "C",
                               vec=lambda feats, N, arr=arr, k=k: _vshift(feats, N, arr, k)))
    # C6 隔期引用
    for lag in (2, 3):
        for (a, b, c) in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0),
                          (1, 0, 1), (0, 1, 1), (1, 1, 1), (-1, 1, 0),
                          (1, -1, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2),
                          (1, 2, 0), (2, 1, 0), (-1, 0, 1), (1, 0, -1),
                          (0, -1, 1), (0, 1, -1), (3, 0, 0), (0, 3, 0)):
            for k in (0, 5):
                out.append(Formula(f"C6_l{lag}_{a}_{b}_{c}_{k}", f"隔{lag}期({a},{b},{c})+{k}",
                                   "C", vec=lambda feats, N, lag=lag, a=a, b=b, c=c, k=k: _c6v(feats, N, lag, a, b, c, k)))
    # C7 反转映射
    for (a, b, c) in coeffs[:80]:
        for mp in ("inv", "half"):
            nm = "镜像" if mp == "inv" else "对补"
            out.append(Formula(f"C7_{a}_{b}_{c}_{mp}", f"{nm}({a},{b},{c})", "C",
                               vec=lambda feats, N, a=a, b=b, c=c, mp=mp: _c7v(feats, N, a, b, c, mp)))
    return out

# ---------------------------------------------------------------- 族 D: 形态/路数

def build_family_D(feats):
    out = []
    # D1 012路
    for W in (10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 180, 200):
        for strat in ("strong", "weak"):
            def fd1(rc, feats, t, W=W, strat=strat):
                cnt = rc.freq[W].cnt
                road = np.zeros(3, dtype=np.float64)
                for d in DIG:
                    road[d % 3] += cnt[d]
                r = argmax10(road) if strat == "strong" else argmin10(road)
                inroad = [d for d in DIG if d % 3 == r]
                return min(inroad, key=lambda d: cnt[d])
            sname = "强路" if strat == "strong" else "弱路"
            out.append(Formula(f"D1_road{W}_{strat}", f"012路{sname}冷(W{W})", "D", fd1))
    # D2/D3/D4 偏离
    for thr in (52, 55, 58, 60, 63, 65, 68, 70, 72, 75):
        for W in (10, 15, 20, 30, 50):
            for mode in ("hot", "cold"):
                def fd2(rc, feats, t, thr=thr, W=W, mode=mode):
                    cnt = rc.freq[W].cnt
                    odd_sum = sum(cnt[d] for d in (1, 3, 5, 7, 9))
                    tot = float(cnt.sum())
                    if tot == 0:
                        return 0
                    if odd_sum / tot * 100 >= thr:
                        grp = [d for d in DIG if d % 2 == 1]
                    else:
                        grp = [d for d in DIG if d % 2 == 0]
                    return max(grp, key=lambda d: cnt[d]) if mode == "hot" else min(grp, key=lambda d: cnt[d])
                out.append(Formula(f"D2_par{thr}_{W}_{mode}", f"奇偶偏离{thr}%W{W}{mode}", "D", fd2))
                def fd3(rc, feats, t, thr=thr, W=W, mode=mode):
                    cnt = rc.freq[W].cnt
                    big_sum = sum(cnt[d] for d in (5, 6, 7, 8, 9))
                    tot = float(cnt.sum())
                    if tot == 0:
                        return 0
                    if big_sum / tot * 100 >= thr:
                        grp = [d for d in DIG if d >= 5]
                    else:
                        grp = [d for d in DIG if d < 5]
                    return max(grp, key=lambda d: cnt[d]) if mode == "hot" else min(grp, key=lambda d: cnt[d])
                out.append(Formula(f"D3_size{thr}_{W}_{mode}", f"大小偏离{thr}%W{W}{mode}", "D", fd3))
                def fd4(rc, feats, t, thr=thr, W=W, mode=mode):
                    cnt = rc.freq[W].cnt
                    primes = (1, 2, 3, 5, 7)
                    p_sum = sum(cnt[d] for d in primes)
                    tot = float(cnt.sum())
                    if tot == 0:
                        return 0
                    if p_sum / tot * 100 >= thr:
                        grp = [d for d in DIG if d in primes]
                    else:
                        grp = [d for d in DIG if d not in primes]
                    return max(grp, key=lambda d: cnt[d]) if mode == "hot" else min(grp, key=lambda d: cnt[d])
                out.append(Formula(f"D4_prime{thr}_{W}_{mode}", f"质合偏离{thr}%W{W}{mode}", "D", fd4))
    # D5 形态跟随
    for W in (20, 50, 100, 200):
        for mode in ("hot", "cold"):
            def fd5a(rc, feats, t, W=W, mode=mode):
                f = feats
                form = int(f["F3"][t - 1])
                cnt = rc.freq[W].cnt
                if form == 0:
                    return int(f["H"][t - 1])
                if form == 1:
                    h, tt, o = int(f["H"][t - 1]), int(f["T"][t - 1]), int(f["O"][t - 1])
                    pair = h if h == tt else (h if h == o else tt)
                    single = [d for d in (h, tt, o) if d != pair][0]
                    grp = [pair, single]
                    return max(grp, key=lambda d: cnt[d]) if mode == "hot" else min(grp, key=lambda d: cnt[d])
                grp = [int(f["H"][t - 1]), int(f["T"][t - 1]), int(f["O"][t - 1])]
                return max(grp, key=lambda d: cnt[d]) if mode == "hot" else min(grp, key=lambda d: cnt[d])
            out.append(Formula(f"D5_follow{W}_{mode}", f"形态跟随W{W}{mode}", "D", fd5a))
    # D6 连号延伸
    for W in (20, 50, 100, 200):
        for mode in ("ext", "mid"):
            def fd6(rc, feats, t, W=W, mode=mode):
                f = feats
                h, tt, o = int(f["H"][t - 1]), int(f["T"][t - 1]), int(f["O"][t - 1])
                s = sorted((h, tt, o))
                cnt = rc.freq[W].cnt
                cand = []
                if mode == "ext":
                    for i in range(2):
                        if s[i + 1] - s[i] == 1:
                            cand.append((s[i] - 1) % 10)
                            cand.append((s[i + 1] + 1) % 10)
                else:
                    cand = [(s[1] - 1) % 10, (s[1] + 1) % 10]
                if not cand:
                    cand = list(DIG)
                return min(cand, key=lambda d: cnt[d])
            out.append(Formula(f"D6_link{W}_{mode}", f"连号延伸W{W}{mode}", "D", fd6))
    # D7 AC值条件
    for target in ("cold", "hot"):
        for alpha in (0.2, 0.5, 1.0, 2.0):
            out.append(Formula(f"D7_ac_{target}_a{alpha}", f"AC值条件{target}α{alpha}", "D",
                               lambda rc, feats, t, target=target, alpha=alpha:
                               _cond_formula(rc, feats, t, "ac", "AC", 1, 100, target, alpha)))
    # D8 位和条件
    for ck, fk in (("w2", "W2"), ("w3", "W3"), ("w5", "W5")):
        for target in ("cold", "hot"):
            for alpha in (0.2, 0.5, 1.0, 2.0):
                out.append(Formula(f"D8_{ck}_{target}_a{alpha}", f"位和{ck}条件{target}α{alpha}", "D",
                                   lambda rc, feats, t, ck=ck, fk=fk, target=target, alpha=alpha:
                                   _cond_formula(rc, feats, t, ck, fk, 1, 100, target, alpha)))
    # D9 振幅条件
    for target in ("cold", "hot"):
        for alpha in (0.2, 0.5, 1.0, 2.0):
            out.append(Formula(f"D9_amp_{target}_a{alpha}", f"振幅形态{target}α{alpha}", "D",
                               lambda rc, feats, t, target=target, alpha=alpha:
                               _cond_formula(rc, feats, t, "amp", "AMP8", 1, 100, target, alpha)))
    # D10 除余类
    for mod in (3, 4, 5, 6, 7, 9):
        for big in (True, False):
            def fd10(rc, feats, t, mod=mod, big=big):
                cnt = rc.freq[100].cnt
                rem = np.zeros(mod, dtype=np.float64)
                for d in DIG:
                    rem[d % mod] += cnt[d]
                r = argmax10(rem) if big else argmin10(rem)
                inr = [d for d in DIG if d % mod == r]
                return min(inr, key=lambda d: cnt[d])
            kind = "多" if big else "少"
            out.append(Formula(f"D10_mod{mod}_{kind}", f"余数{mod}{kind}", "D", fd10))
    # D11 和值区间
    for W in (10, 20, 30, 50):
        for mode in ("high_hot", "high_cold", "low_hot", "low_cold"):
            def fd11(rc, feats, t, W=W, mode=mode):
                f = feats
                s = int(f["S"][t - 1])
                cnt = rc.freq[W].cnt
                if s >= 15:
                    grp = [d for d in DIG if d >= 5] if mode.startswith("high") else [d for d in DIG if d < 5]
                else:
                    grp = [d for d in DIG if d < 5] if mode.startswith("low") else [d for d in DIG if d >= 5]
                if mode.endswith("hot"):
                    return max(grp, key=lambda d: cnt[d])
                return min(grp, key=lambda d: cnt[d])
            out.append(Formula(f"D11_sv{W}_{mode}", f"和值区W{W}{mode}", "D", fd11))
    return out

# ---------------------------------------------------------------- 族 E: 周期/节律

def build_family_E(feats):
    out = []
    # E1 N期轮回 (2..50)
    for N in range(2, 51):
        for var in ("H", "T", "O", "SW", "K"):
            out.append(Formula(f"E1_n{N}_{var}", f"{N}期前{var}", "E",
                               vec=lambda feats, Nn, var=var, n=N: _e1v(feats, Nn, var, n)))
    # E2 期号节律
    for ck, fk, m in (("im10", "IM10", 10), ("im7", "IM7", 7), ("im5", "IM5", 5)):
        for target in ("cold", "hot"):
            for alpha in (0.2, 0.5, 1.0, 2.0):
                out.append(Formula(f"E2_{ck}_{target}_a{alpha}", f"期号{ck}条件{target}", "E",
                                   lambda rc, feats, t, ck=ck, fk=fk, target=target, alpha=alpha:
                                   _cond_formula(rc, feats, t, ck, fk, 0, 200, target, alpha)))
    # E3 年内期序
    for ck, fk in (("ym5", "YM5"), ("ym10", "YM10"), ("ym20", "YM20"), ("ym3", "YM3")):
        for target in ("cold", "hot"):
            for alpha in (0.2, 0.5, 1.0, 2.0):
                out.append(Formula(f"E3_{ck}_{target}_a{alpha}", f"年内{ck}条件{target}", "E",
                                   lambda rc, feats, t, ck=ck, fk=fk, target=target, alpha=alpha:
                                   _cond_formula(rc, feats, t, ck, fk, 0, 200, target, alpha)))
    # E4 跨年同期
    for target in ("cold", "hot"):
        for alpha in (0.2, 0.5, 1.0, 2.0):
            out.append(Formula(f"E4_cy_{target}_a{alpha}", f"跨年同期{target}", "E",
                               lambda rc, feats, t, target=target, alpha=alpha:
                               _cond_formula(rc, feats, t, "cy", "CY", 0, 200, target, alpha)))
    # E5 错位窗口频率
    for (W, k) in ((50, 5), (50, 10), (50, 20), (100, 5), (100, 10), (100, 20), (150, 10)):
        for hot in (False, True):
            def fe5(rc, feats, t, W=W, k=k, hot=hot):
                pref = feats["PREF"]
                lo = max(0, t - W - k)
                hi = max(0, t - k)
                v = pref[hi] - pref[lo]
                return argmax10(v) if hot else argmin10(v)
            kind = "热" if hot else "冷"
            out.append(Formula(f"E5_shift{W}_{k}_{kind}", f"错位窗口{W}/{k}{kind}", "E", fe5))
    # E6 遗漏周期
    for mode in ("over", "under"):
        def fe6(rc, feats, t, mode=mode):
            mu = feats["MUMISS"]
            m = feats["missM"][t].astype(np.float64)
            ratio = np.full(10, -1.0)
            for d in DIG:
                if mu[d] > 0:
                    ratio[d] = m[d] / mu[d]
            if mode == "over":
                return argmax10(ratio)
            cand = [d for d in DIG if mu[d] > 0 and m[d] < mu[d]]
            if not cand:
                return argmin10(m)
            return min(cand, key=lambda d: m[d])
        out.append(Formula(f"E6_{mode}", f"遗漏周期{('逾期' if mode=='over' else '提前')}", "E", fe6))
    return out

# ---------------------------------------------------------------- 族 F: 趋势/统计矩

def build_family_F(feats):
    out = []
    # F1 分位滑动均值
    for pos, pn in enumerate(("百", "十", "个")):
        for delta in (-2, -1, 0, 1, 2):
            for W in (5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60):
                def ff1(rc, feats, t, pos=pos, delta=delta, W=W):
                    mu = rc.sums[W].s[pos] / W
                    return int(round(mu + delta)) % 10
                out.append(Formula(f"F1_{pn}_m{delta}_w{W}", f"{pn}位均值+{delta}(W{W})", "F", ff1))
    # F2 和值回归
    for W in (8, 10, 15, 20, 30, 40, 50, 60):
        for mode in ("high_hot", "high_cold", "low_hot", "low_cold"):
            def ff2(rc, feats, t, W=W, mode=mode):
                mean_s = rc.sums[W].s.sum() / W
                cnt = rc.freq[W].cnt
                if mean_s >= 13.5:
                    grp = [d for d in DIG if d >= 5] if mode.startswith("high") else [d for d in DIG if d < 5]
                else:
                    grp = [d for d in DIG if d < 5] if mode.startswith("low") else [d for d in DIG if d >= 5]
                if mode.endswith("hot"):
                    return max(grp, key=lambda d: cnt[d])
                return min(grp, key=lambda d: cnt[d])
            out.append(Formula(f"F2_sv{W}_{mode}", f"和值回归W{W}{mode}", "F", ff2))
    # F3 AR(1)
    for pos, pn in enumerate(("百", "十", "个")):
        for W in (20, 50):
            for dk in (0, 1, -1):
                def ff3(rc, feats, t, pos=pos, W=W, dk=dk):
                    b, a = rc.ar[(pos, W)].coef()
                    last = feats[("H", "T", "O")[pos]][t - 1]
                    return int(round(a + b * last + dk)) % 10
                out.append(Formula(f"F3_{pn}_w{W}_{dk}", f"{pn}位AR1(W{W}){dk:+d}", "F", ff3))
    # F4 熵条件
    for W in (20, 50, 100):
        for mode in ("high_cold", "high_hot", "low_cold", "low_hot"):
            def ff4(rc, feats, t, W=W, mode=mode):
                cnt = rc.freq[W].cnt
                tot = float(cnt.sum())
                if tot == 0:
                    return 0
                p = cnt / tot
                ent = -np.sum(p[p > 0] * np.log2(p[p > 0]))
                high = ent > 2.6
                use_hot = (mode == "high_hot") or (mode == "low_hot")
                return argmax10(cnt) if use_hot else argmin10(cnt)
            out.append(Formula(f"F4_ent{W}_{mode}", f"熵条件W{W}{mode}", "F", ff4))
    # F5 Z-score
    for W in (10, 20, 30, 50, 60, 100, 150, 200):
        for hot in (False, True):
            def ff5(rc, feats, t, W=W, hot=hot):
                cnt = rc.freq[W].cnt
                n = 3 * W
                z = (cnt - 0.3 * n) / np.sqrt(n * 0.3 * 0.7)
                return argmax10(z) if hot else argmin10(z)
            kind = "热" if hot else "冷"
            out.append(Formula(f"F5_z{W}_{kind}", f"Z分数{W}{kind}", "F", ff5))
    # F6 斜率
    for W in (10, 15, 30, 45, 60):
        for hot in (False, True):
            def ff6(rc, feats, t, W=W, hot=hot):
                sl = np.array([rc.slope[W].slope(d) for d in DIG])
                return argmax10(sl) if hot else argmin10(sl)
            kind = "升" if hot else "降"
            out.append(Formula(f"F6_slope{W}_{kind}", f"斜率{W}{kind}", "F", ff6))
    # F7 均线差 (短窗均值 vs 长窗均值)
    for (Ws, Wl) in ((10, 50), (10, 100), (20, 100), (20, 150), (30, 200), (50, 200)):
        for pos, pn in enumerate(("百", "十", "个")):
            for mode in ("hot", "cold"):
                def ff7(rc, feats, t, Ws=Ws, Wl=Wl, pos=pos, mode=mode):
                    ms = rc.sums[Ws].s[pos] / Ws
                    ml = rc.sums[Wl].s[pos] / Wl
                    cnt = rc.freq[Wl].pos[pos]
                    if ms > ml:  # 短均线在上(近期走高)
                        grp = [d for d in DIG if d >= int(round(ms)) % 10 or d >= 5]
                        grp = [d for d in DIG if d >= 5]
                    else:
                        grp = [d for d in DIG if d < 5]
                    if mode == "hot":
                        return max(grp, key=lambda d: cnt[d])
                    return min(grp, key=lambda d: cnt[d])
                out.append(Formula(f"F7_ma{Ws}_{Wl}_{pn}_{mode}", f"{pn}均线{Ws}/{Wl}{mode}", "F", ff7))
    return out

# ---------------------------------------------------------------- 族 H: 组合条件

def build_family_H(feats):
    out = []
    COND_DEFS = [
        ("r27", 27, "012路形态", "R27"), ("swf3", 30, "和尾×形态", "SWF3"),
        ("kf3", 30, "跨度×形态", "KF3"), ("parsz", 64, "奇偶×大小", "PARSZ"),
        ("swpar", 80, "和尾×奇偶", "SWPAR"), ("ksz", 80, "跨度×大小", "KSZ"),
        ("htom5", 10, "百十差×个奇偶", "HTOM5"), ("f32", 9, "双期形态", "F32"),
        ("swd3f", 9, "和值走势×形态", "SWD3F"), ("parim", 16, "奇偶×期号", "PARIM"),
    ]
    for key, m, cname, fk in COND_DEFS:
        for order in (1, 2):
            for W in (100, 200):
                for target in ("cold", "hot"):
                    ALPHAS = (0.5, 1.0, 2.0)
                    _cache = {}
                    for ai, alpha in enumerate(ALPHAS):
                        tg = "冷" if target == "cold" else "热"
                        def mk(ai=ai, alpha=alpha, key=key, fk=fk, order=order, ALPHAS=ALPHAS,
                               W=W, target=target, _cache=_cache):
                            def fh(rc, feats, t):
                                return _cache_get(_cache, rc, feats, t, key, fk,
                                                  order, W, target, ALPHAS)[ai]
                            return fh
                        out.append(Formula(
                            f"H_{key}_o{order}_w{W}_{tg}_a{alpha}",
                            f"{cname}组合{order}阶{W}期·{tg}α{alpha}", "H", mk()))
    return out

# ---------------------------------------------------------------- 条件定义

def build_conds():
    conds = []
    # B 族条件 (order1/order2, W100/200)
    for key, m, fk in [
        ("sw", 10, "SW"), ("kd", 10, "K"), ("h", 10, "H"), ("t", 10, "T"),
        ("o", 10, "O"), ("par", 8, "PAR8"), ("sz", 8, "SZ8"), ("f3", 3, "F3"),
        ("sv", 28, "S"), ("dh", 10, "DHT"), ("dt", 10, "DTO"), ("do", 10, "DHO"),
        ("p3", 10, "P3M10"), ("sk", 100, "SWK"), ("rp", 4, "RP"),
        ("par3", 4, "PAR3"), ("sz3", 4, "SZ3"), ("sumod", 2, "SUMOD"),
        ("kod", 2, "KOD"), ("kbig", 2, "KBIG"), ("cont", 2, "CONT"),
        ("perm", 6, "PERM"), ("ndig", 3, "NDIG"), ("ampk", 10, "AMPK"),
    ]:
        for order in (1, 2):
            for W in (100, 200):
                conds.append((key, order, W, m, fk))
    # D 族条件
    for key, m, fk in (("ac", 5, "AC"), ("w2", 4, "W2"), ("w3", 9, "W3"),
                       ("w5", 5, "W5"), ("amp", 8, "AMP8")):
        conds.append((key, 1, 100, m, fk))
    # E 族期号类 (order=0 同期)
    for key, m, fk in (("im10", 10, "IM10"), ("im7", 7, "IM7"), ("im5", 5, "IM5"),
                       ("ym5", 5, "YM5"), ("ym10", 10, "YM10"),
                       ("ym20", 20, "YM20"), ("ym3", 3, "YM3"), ("cy", 30, "CY")):
        conds.append((key, 0, 200, m, fk))
    # H 族组合条件
    for key, m, fk in (("r27", 27, "R27"), ("swf3", 30, "SWF3"), ("kf3", 30, "KF3"),
                       ("parsz", 64, "PARSZ"), ("swpar", 80, "SWPAR"),
                       ("ksz", 80, "KSZ"), ("htom5", 10, "HTOM5"),
                       ("f32", 9, "F32"), ("swd3f", 9, "SWD3F"), ("parim", 16, "PARIM")):
        for order in (1, 2):
            for W in (100, 200):
                conds.append((key, order, W, m, fk))
    return conds

# ---------------------------------------------------------------- 总构建

def build_all_formulas(feats):
    """返回 (formulas, conds)"""
    conds = build_conds()
    out = []
    out += build_family_A(feats)
    out += build_family_B(feats)
    out += build_family_C(feats)
    out += build_family_D(feats)
    out += build_family_E(feats)
    out += build_family_F(feats)
    out += build_family_H(feats)
    # G 静态投票
    out.append(Formula("G1a_allvote", "全池等权投票", "G", None))
    out.append(Formula("G1b_bestvote", "各族最佳投票", "G", None))
    out.append(Formula("G2a_top50vote", "Top50等权投票", "G", None))
    out.append(Formula("G2b_top50wvote", "Top50加权投票", "G", None))
    # G 动态参考
    for K in (10, 20, 50):
        out.append(Formula(f"G3_top{K}vote", f"Top{K}动态投票", "G", None, dynamic=True))
    out.append(Formula("G4_formvote", "形态分治投票", "G", None, dynamic=True))
    out.append(Formula("G5_rev10", "反指Top10", "G", None, dynamic=True))
    out.append(Formula("G5_rev20", "反指Top20", "G", None, dynamic=True))
    return out, conds
