# 卡密管理系统

FastAPI + SQLite + Jinja2 的软件许可证密钥管理平台。

## 技术栈
- FastAPI 后端，Jinja2 模板渲染
- SQLite 数据库（SQLAlchemy ORM）
- 自定义 Tailwind CSS（build_css.py 生成）
- JWT 认证 + TOTP 两步验证
- Docker 部署

## 关键文件
- `app/main.py` — 应用入口，动态前缀中间件
- `app/models.py` — 数据模型
- `app/routers/client.py` — 客户端认证 API（固定路径 `/api/client/auth`）
- `app/routers/keys.py` — 卡密管理
- `build_css.py` — 模板改动后运行以更新 CSS

## 注意
- Python 3.8 兼容，类型注解用 `typing` 模块（不用 `X | Y` 语法）
- 客户端认证 API 与旧版完全兼容，修改时保持响应格式不变
