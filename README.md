# 福彩3D 通杀一码 · 云端全自动更新

## 玩法
通杀一码 = 杀掉一个数字，下期百/十/个三位都不出现即命中（理论随机基线 72.9%）。

## 算法
- 公式池 **6294 个**暴力穷举（频率/条件转移/算术/形态/周期/趋势/组合七族）
- 主机制 **Hedge 13专家加权投票**（WIN=90，K=13）：每期取近90期命中率 Top13 公式为专家，按命中率加权投票，票王 = 通杀码
- 200期逐期真实回测（严格 walk-forward，不偷看未来）

## 云端全自动更新
- **GitHub Actions 三重 cron**：北京 22:00 / 23:30 / 01:00（UTC 14:00 / 15:30 / 17:00），3 次机会兜底，严格在 21:30 开奖后执行
- **7 源降级链**：灰鸟API → 17500.cn → 中彩网 → apihz → 8200 → 55128 → 彩经网
- 抓到新期 → **自动追加到 fc3d-history.csv** → 自动重算 → 自动更新 index.html
- 手机访问：https://ljq-hub-cmyk.github.io/fc3d-tongsha/

## 文件
| 文件 | 说明 |
|---|---|
| `update.py` | 云端主脚本：抓取→追加CSV→重算→生成HTML |
| `core.py` / `formulas.py` | Hedge 引擎与公式池 |
| `export_static.py` | 生成自包含 index.html（数据内嵌） |
| `fc3d-history.csv` | 全量历史数据（自动追加） |
| `.github/workflows/daily.yml` | 三重 cron 自动更新 |

> 仅供技术研究，不构成任何购彩建议。
