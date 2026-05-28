# api-dindon

叮咚到號後端 — FastAPI + Celery + 29 家醫院爬蟲，支援 LINE Bot、LIFF 與 `/simple` 老人版。

- **Production**：https://dd.dl-app.com
- 涵蓋 29 家醫院，三軍總醫院拆 3 院區 = 31 張卡
- 設計性休爬：22:00–07:00 / 週日 / TW 國定假日

## 技術棧
- **API**：FastAPI + Uvicorn
- **任務佇列**：Celery + Redis
- **資料庫**：MySQL
- **爬蟲**：29 家醫院自定義 scraper（`app/scrapers/`）
- **前端**：LINE Bot + LIFF + `/simple` 老人版靜態頁面
- **部署**：Docker Compose + Nginx（aaPanel）

## 快速開始
```bash
cp .env.example .env
docker compose up -d
```

## 相關
iOS App：[DingDong](https://github.com/Harry1667/DingDong)

---

## English

Backend for DingDong (叮咚到號) — FastAPI + Celery, with custom scrapers for 29 Taiwanese hospitals. Powers a LINE bot, a LIFF mini-app, and a `/simple` view designed for elderly users.

- **Production**: https://dd.dl-app.com
- 29 hospitals; Tri-Service General Hospital is split into 3 campuses → 31 cards total
- Scrapers intentionally sleep 22:00–07:00, Sundays, and Taiwan public holidays

### Tech stack
- **API**: FastAPI + Uvicorn
- **Task queue**: Celery + Redis
- **Database**: MySQL
- **Scrapers**: one custom scraper per hospital under `app/scrapers/`
- **Frontend**: LINE bot + LIFF + `/simple` static page for elderly users
- **Deployment**: Docker Compose + Nginx (aaPanel)

### Quick start
```bash
cp .env.example .env
docker compose up -d
```

### Related
iOS app: [DingDong](https://github.com/Harry1667/DingDong)
