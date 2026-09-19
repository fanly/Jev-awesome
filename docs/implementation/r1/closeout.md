# R1.1 Closeout

起始：`29be5f23e0ec06cf1c0cd87b3f18e7e8384b52a2`  
格式提交：`b551a557a9531d00d7ae2a779100293ad463be53`  
本文件随行为提交更新；最终 SHA 以提交后 `git rev-parse HEAD` 为准。

## 四项关闭

### 1. 全仓检查 ↔ CI

- `ci.yml` 现执行：`ruff check .`、`ruff format --check .`、`basedpyright`、`pytest`、validate、render --check
- 本地与干净克隆同等命令退出码 0（行为提交之后）

### 2. T21

- 合并 / squash 后从 main 续跑，新开 PR，不更新已合并 PR
- 合并后删除陈旧 robot ref 再推送（非 force main）
- 分支删除：从 PR head SHA 恢复候选；无证据 → `recovery_gap` paused
- 主线拒绝不被旧机器人数据恢复为 pending

### 3. T08

- `HttpBodyCache` + `OfficialMonitorAdapter`：If-None-Match、304 复用正文、缓存损坏无条件重取、请求预算

### 4. T26

- `Asia/Shanghai` 上一完整周；半开区间；稳定周 ID；重跑字节一致；无事件不新建空周报；pending/`first_discovered` 不进精选周报

## 正式数据

validate：pending=97 proposed=34 curated=0 inbox=131（未改审核状态）
