# 卡密管理系统

软件许可证密钥管理平台。管理后台可视化操作 + 客户端 API 验证卡密。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 模板引擎 | Jinja2 |
| 数据库 | SQLite（SQLAlchemy ORM） |
| 认证 | JWT + TOTP 两步验证 |
| 前端样式 | Tailwind CSS（build_css.py 生成） |
| 部署 | Docker / Docker Compose |

## 项目结构

```
卡密管理系统/
├── app/
│   ├── main.py                # 应用入口，动态前缀中间件
│   ├── config.py               # 环境变量配置
│   ├── database.py             # 数据库引擎 & Session
│   ├── models.py               # 5 张数据表
│   ├── schemas.py              # Pydantic 请求/响应模型
│   ├── dependencies.py         # JWT、限流、设置读写
│   ├── routers/
│   │   ├── auth.py             # 管理端登录 & OTP 验证
│   │   ├── client.py           # 客户端卡密认证（固定路径）
│   │   ├── applications.py     # 应用 CRUD
│   │   ├── keys.py             # 卡密 CRUD、筛选、导出、批次管理
│   │   ├── dashboard.py        # 仪表盘统计
│   │   ├── settings_router.py  # 系统设置 & OTP 管理
│   │   ├── recycle.py          # 回收站
│   │   └── pages.py            # Web 页面路由
│   ├── templates/              # 8 个 Jinja2 页面
│   └── static/
│       └── tailwind.min.css
├── build_css.py                # CSS 构建脚本
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── API接口文档.md               # 全部 API 文档
├── 设计文档.md                  # 架构设计文档
└── 客户端调用文档.md             # 客户端认证接口说明
```

## 功能设计

### 管理后台（Web 界面）
- **仪表盘** — 全局统计 + 每应用卡片（卡密数、在线数、已过期、即将过期、绑定设备数）
- **应用管理** — 增删改查，自定义 app_code
- **卡密管理** — 批量生成（前缀/后缀/自定义天数）、全字段筛选、多选批量删除、批次分组、CSV 导出（含设备码）
- **回收站** — 按批次恢复或永久删除
- **系统设置** — API 路由前缀、心跳阈值、OTP 安全配置

### 客户端 API
- `/api/client/auth` — 卡密验证 + 设备绑定 + 心跳（固定路径，不受前缀影响）

### 安全特性
- JWT 双令牌（Access 2h + Refresh 7d）
- TOTP 两步验证（支持 Google Authenticator）
- 动态 API 路由前缀（防目录爆破）
- bcrypt 密码哈希
- 登录/OTP 频率限制 & 锁定

## 本地开发

```bash
# 创建虚拟环境
python -m venv venv && source venv/bin/activate  # Linux
# 或 python -m venv venv && venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 生成 CSS
python build_css.py

# 启动
uvicorn app.main:app --reload --port 8000
```

访问 `http://127.0.0.1:8000`，默认账号 `admin` / `admin123`。

修改模板样式后重新运行 `python build_css.py` 即可更新 CSS。

## Docker 部署

### 方式一：docker-compose（推荐）

```bash
# 1. 修改环境变量
cp .env .env.prod
vim .env.prod    # 改 ADMIN_PASSWORD 和 JWT_SECRET

# 2. 启动
docker-compose --env-file .env.prod up -d

# 3. 查看日志
docker-compose logs -f

# 4. 停止
docker-compose down
```

数据库持久化在 `./data/app.db`，容器删除后数据不丢失。

### 方式二：手动构建镜像

```bash
# 构建镜像
docker build -t key-manager:latest .

# 运行容器
docker run -d \
  --name key-manager \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=your_strong_password \
  -e JWT_SECRET=your_random_secret \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  key-manager:latest
```

### 导出镜像（离线部署）

```bash
# 构建后导出
docker build -t key-manager:latest .
docker save key-manager:latest | gzip > key-manager.tar.gz

# 在目标机器导入
docker load < key-manager.tar.gz
docker-compose up -d
```

## 客户端接入

参见 [客户端调用文档.md](客户端调用文档.md)，核心接口：

```
POST /api/client/auth
{
    "machine_code": "32位MD5机器码",
    "key_code": "卡密",
    "app_code": "应用编号",
    "ip_address": "可选"
}
```

Python 示例：

```python
import requests

resp = requests.post("http://your-server:8000/api/client/auth", json={
    "machine_code": "1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P",
    "key_code": "YOUR-KEY-CODE",
    "app_code": "YOUR-APP-CODE",
})
print(resp.json())
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| ADMIN_USERNAME | admin | 管理员用户名（首次启动创建） |
| ADMIN_PASSWORD | admin123 | 管理员密码（生产环境务必修改） |
| JWT_SECRET | change-me... | JWT 签名密钥（生产环境务必修改） |
| DATABASE_URL | sqlite:///./data/app.db | 数据库路径 |
| TZ | Asia/Shanghai | 时区 |
