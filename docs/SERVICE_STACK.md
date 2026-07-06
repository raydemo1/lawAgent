# LawAgent 服务栈 (Elasticsearch + PostgreSQL/pgvector)

本目录下的 `docker-compose.yml` 用于本地启动 LawAgent 项目真实混合检索所需的两个基础服务：

- **Elasticsearch 8.13.0**：全文检索引擎，容器首次启动会自动安装中文分词插件 IK（`analysis-ik` 8.13.0），承担 BM25 / 关键词全文检索。
- **PostgreSQL 16 + pgvector**：关系型存储与向量检索，承担语义向量近邻搜索（HNSW）。

## 默认连接信息

| 服务 | 地址 / DSN |
| --- | --- |
| Elasticsearch | http://localhost:9200 |
| PostgreSQL | `postgresql://lawagent:lawagent@localhost:5432/lawagent` |

> 账号密码均为 `lawagent`，仅供本地开发，请勿用于生产。

## 启动服务

在 `docker-compose.yml` 所在目录执行：

```bash
docker compose up -d --build
```

首次构建时 Elasticsearch 镜像会联网下载并安装 IK 插件（通过 `docker/elasticsearch.Dockerfile` 烘焙进镜像，一次性完成）；数据持久化到命名卷 `esdata`、`pgdata`，重启不丢失。后续启动无需 `--build`，直接 `docker compose up -d` 即可。

查看状态（两个服务的 healthcheck 均为 `healthy` 即可接入）：

```bash
docker compose ps

# 快速验证
curl http://localhost:9200
docker exec -it lawagent-pg psql -U lawagent -d lawagent -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

验证 IK 中文分词是否就绪：

```bash
curl -X POST http://localhost:9200/_analyze \
  -H 'Content-Type: application/json' \
  -d '{"analyzer":"ik_max_word","text":"中华人民共和国民法典"}'
```

## 中文分词 (IK) 注意事项

- IK 插件版本必须与 Elasticsearch 完全一致（本栈均为 **8.13.0**），否则 ES 启动会因版本不匹配直接退出。
- 插件在镜像构建阶段（`docker/elasticsearch.Dockerfile`）安装到镜像层，不在 `esdata` 数据卷内；`docker compose down` 删除容器后再次 `up` 会直接复用已构建的镜像，无需重装。
- 离线环境需提前下载对应 zip 包，并修改 `docker/elasticsearch.Dockerfile` 中的安装地址为本地文件路径。
- 常用两种分词模式：`ik_max_word`（细粒度，适合写入索引）、`ik_smart`（粗粒度，适合查询）。自定义词典可在 `config/analysis-ik/` 下扩展。

## 停止服务

```bash
# 停止容器但保留数据
docker compose stop

# 删除容器，保留数据卷
docker compose down

# 删除容器并彻底清除数据卷（谨慎，数据将丢失）
docker compose down -v
```
