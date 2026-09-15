# 经营归因分析系统

面向经营分析场景的多轮归因分析系统：支持围绕业务问题持续追问、补充证据、生成阶段性结论与最终报告。

## 技术栈

- 后端：Python FastAPI + SQLAlchemy + Alembic + WebSocket
- 前端：React + Vite + TypeScript
- 数据库：PostgreSQL
- 认证：Mock OAuth（开发一键登录）
- 分析引擎：无 `LLM_API_KEY` 时走规则演示引擎；配置 Key 后走 OpenAI 兼容接口

## 快速启动

### 方式一：Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- 前端：http://localhost:5173
- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 方式二：本地开发

> 若本机 `5432` / `8000` 已被占用：Postgres 映射为 **55433**，后端可用 **8001**。  
> 前端通过 Vite 同源代理访问后端（`/auth`、`/api`），**请用 http://localhost:5173 打开**，不要直连后端端口登录。

```bash
# 1. 启动数据库
docker compose up -d db

# 2. 后端
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # DATABASE_URL 默认连 localhost:55433
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8001

# 3. 前端（另开终端）
cd frontend
cp .env.example .env      # VITE_API_BASE / VITE_WS_BASE 留空，走代理
npm install
npm run dev
```

- 前端：http://localhost:5173
- 后端：http://localhost:8001
- API 文档：http://localhost:8001/docs

## 演示流程

1. 打开前端，点击「授权登录」进入工作台
2. 新建会话，可上传附件
3. 发送问题，例如：
   - `近30天商品目录搜索转化为什么下降？`（商品目录优化场景）
   - `最近退款率上升的主要原因是什么？`（退款模式分析场景）
4. 右侧查看六段结构化结果；可复制 / 导出 Markdown
5. 管理员登录后可调用「重载配置」

## 示例数据

位于 `data/samples/`：

- `catalog/`：商品、类目、曝光、点击、转化
- `refund/`：退款申请、退款原因、订单、用户

规则引擎会读取各场景 `summary.json` 生成分析结论。

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/login` | Mock 授权登录 |
| GET | `/auth/callback` | 回调换取 JWT |
| POST | `/api/chat/create` | 创建会话 |
| POST | `/api/chat/delete` | 删除会话（级联清理） |
| POST | `/api/chat/update` | 重命名 |
| GET | `/api/chat/ls` | 会话列表 |
| GET | `/api/chat/ls/{id}` | 历史消息 |
| POST | `/api/chat/send` | 发送消息并创建分析任务 |
| POST | `/api/chat/ws-token` | 签发 WebSocket 临时令牌 |
| WS | `/api/chat/ws/chat` | 实时推送分析过程 |
| POST | `/api/attachment/upload` | 上传附件 |
| POST | `/api/attachment/delete` | 删除附件 |
| GET | `/api/attachment/get` | 下载附件 |
| GET | `/api/tasks/{task_id}` | 任务状态 |
| GET | `/api/results/{task_id}` | 结构化结果 |
| POST | `/api/admin/reload` | 配置热更新（管理员） |

### WebSocket 事件

`message_start` / `message_delta` / `tool_start` / `tool_finish` / `task_status` / `result_ready` / `error` / `done`

客户端连接后发送：

```json
{"action": "start_task", "task_id": 1}
```

## 环境变量

见 [.env.example](.env.example)。关键项：

- `DATABASE_URL`
- `JWT_SECRET`
- `AUTH_MODE=mock`
- `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（可选）
