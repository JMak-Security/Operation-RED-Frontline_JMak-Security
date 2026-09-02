# =====================================================================
# 🔒 Corporate Minimal Sandbox (Zero-Trust Python Runtime)
# =====================================================================
FROM python:3.11-slim

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt

# 優先建立低權限安全主體
RUN useradd -m -u 10001 redteam_runner

# 1. 僅安裝核心執行期基礎依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# 2. Install the single project dependency contract.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ✨ 核心修正：將目前資料夾下的 main.py 等所有專案檔案複製進容器的 /workspace
COPY . /workspace

# 3. 實作零信任隔離沙盒目錄並修正擁有者權限
RUN mkdir -p /workspace/secure_vault && \
    chown -R redteam_runner:redteam_runner /workspace

# 4. 切換至低權限安全主體
USER redteam_runner

# 啟動紅隊自動化引擎流程
ENTRYPOINT ["python", "main.py"]
