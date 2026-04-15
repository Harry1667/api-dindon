# ibgateway JVM 優化指南

> 伺服器：57.182.129.192（AWS Lightsail Tokyo，2 vCPU / 3.7GB RAM）
> 路徑：`/www/claud/ibgateway/docker-compose.yml`

---

## 現況問題

| 容器 | RAM 使用 | 上限 | Swap |
|------|----------|------|------|
| ib-gateway-live | ~133MB | 700MB | ✅ 正常 |
| ib-gateway-paper | ~636MB | 700MB | 🔴 主要元兇（java 進程 swap 286MB）|
| ibgateway-api | ~70MB | 300MB | ✅ 正常 |

**根本原因**：paper gateway JVM 實際使用接近 700MB（JVM heap + metaspace + JIT + GC），超出實體 RAM，OS 把部分 page 推到 swap。

---

## 優化方向

### 方向 A：調低 paper JVM heap（最直接）

paper 已有 `TWS_HEAP_SIZE: 512m`，但 JVM 總用量遠超 512m。
加入更激進的 JVM flags 壓低記憶體：

```yaml
# ib-gateway-paper 的 environment 區塊
JAVA_TOOL_OPTIONS: >-
  -XX:ParallelGCThreads=1
  -XX:CICompilerCount=2
  -Xss512k
  -XX:MaxMetaspaceSize=128m
  -XX:CompressedClassSpaceSize=64m
  -XX:ReservedCodeCacheSize=64m
  -XX:+UseG1GC
  -XX:MaxGCPauseMillis=200
```

**預期效果**：JVM 總佔用從 ~700MB → ~450MB，swap 壓力大幅降低

---

### 方向 B：live gateway 補上 JVM 限制

`ib-gateway-live` 目前沒有 `JAVA_TOOL_OPTIONS`，JVM 會自動偵測宿主機 2 CPU 並開多個 GC 執行緒。

```yaml
# ib-gateway-live 的 environment 區塊新增
JAVA_TOOL_OPTIONS: >-
  -XX:ParallelGCThreads=2
  -XX:CICompilerCount=2
  -Xss512k
  -XX:MaxMetaspaceSize=128m
  -XX:+UseG1GC
```

> 注意：live 的 Install4j launcher 硬編碼 heap 為 768m，TWS_HEAP_SIZE 無效。
> JAVA_TOOL_OPTIONS 可以覆蓋部分參數但無法改變 -Xmx。

---

### 方向 C：不同時跑 live + paper（最省資源）

目前 live + paper 各 ~400-700MB，合計快 1.2GB。
如果交易邏輯允許，非交易時段只跑一個：

```bash
# 只啟動 paper（一般開發/測試）
docker compose up -d ib-gateway-paper api redis

# 需要 live 時才啟動（用 profiles）
docker compose --profile live up -d
```

**預期省下**：~400-500MB RAM

---

### 方向 D：調低 Docker 記憶體上限（觸發 OOM 前先測試）

目前兩個容器都是 700M。如果 A 方向有效，可以調低：

```yaml
# paper gateway
deploy:
  resources:
    limits:
      memory: 512M   # 從 700M 降到 512M
    reservations:
      memory: 256M

# live gateway
deploy:
  resources:
    limits:
      memory: 600M   # 從 700M 降到 600M（heap 硬編碼 768m，不能太激進）
    reservations:
      memory: 300M
```

> ⚠️ 調太低會導致 OOM kill，IB Gateway 會重啟並需要重新 2FA 登入。
> 建議先做方向 A，觀察一天後再調低 Docker 上限。

---

## 操作步驟

1. **編輯 docker-compose.yml**（在 `/www/claud/ibgateway/`）
2. **重啟 paper gateway**（live 交易時段避免重啟）：
   ```bash
   cd /www/claud/ibgateway
   docker compose restart ib-gateway-paper
   ```
3. **觀察記憶體**（重啟後 3-5 分鐘等 JVM warm up）：
   ```bash
   docker stats --no-stream ibgateway-ib-gateway-paper-1
   ```
4. **確認 swap 改善**：
   ```bash
   free -h
   cat /proc/$(pgrep -f java)/status | grep VmSwap
   ```

---

## 驗證標準

| 指標 | 目標 |
|------|------|
| paper 容器 RAM | < 500MB |
| java 進程 swap | < 50MB |
| IB Gateway 連線 | 正常（port 4004 可達）|
| 整體 swap 使用 | < 300MB |

```bash
# 一鍵驗證
ssh aapanel "free -h && docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' ibgateway-ib-gateway-paper-1 ibgateway-ib-gateway-live-1"
```

---

## 背景知識

- **JVM heap** (`-Xmx`)：Java 物件存放區，最大 512m
- **Metaspace**：類別定義存放區，預設無限制 → 需加 `-XX:MaxMetaspaceSize`
- **JIT Code Cache**：JVM 編譯後的 native code，預設 256m → 可降到 64m
- **Thread stack** (`-Xss`)：每個執行緒的 stack，預設 512k-1m，降到 512k 省記憶體
- **G1GC**：比預設 ParallelGC 更適合低延遲 + 記憶體受限環境
