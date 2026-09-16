FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Node 20（前端生产构建需要）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY api/requirements.txt /srv/api/requirements.txt
RUN pip install --no-cache-dir -r /srv/api/requirements.txt

# 预安装前端依赖（利用层缓存）
COPY web/package.json web/package-lock.json* /srv/web/
RUN cd /srv/web && npm ci --no-audit --no-fund

COPY api /srv/api
COPY web /srv/web
COPY verify /srv/verify

CMD ["python", "/srv/verify/verify.py"]
