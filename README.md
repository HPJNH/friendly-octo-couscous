# 闻脉台

闻脉台当前仍以 SQLite 作为默认数据库，但现在已经从“本地默认可跑项目”推进到“具备单实例服务进程与反向代理前准备条件的项目”。当前阶段只收口运行面与部署说明，不扩展 MySQL、Redis、多实例、对象存储，也不改 parser / rebuild / 前台功能。

## 当前两个启动入口

- 本地入口：`python run.py`
  只服务 `local` 模式，保留桌面本地语义，可打印本机 / 局域网访问地址，并在本地自动打开浏览器。
- 服务器入口：`wsgi.py`
  只暴露 `app` / `application`，不包含浏览器行为。当前单实例服务进程统一推荐使用 `wsgi:app`。

如果要在服务器侧运行，请不要再把 `run.py` 当成唯一入口。

## 当前运行模式

当前只支持两种模式：

- `APP_ENV=local`
- `APP_ENV=production`

兼容别名：

- `DEPLOYMENT_MODE`

## 当前推荐部署姿态

当前版本明确推荐以下姿态：

1. 单实例
2. 持久卷
3. SQLite 默认数据库

这意味着当前仍然不建议直接做：

- 多实例水平扩展
- 多 worker 并发写
- MySQL / Redis
- 对象存储
- 完整 Nginx / HTTPS 成品部署

## SQLite 单实例边界

当前默认数据库仍是 SQLite，因此边界已经写死：

- `SINGLE_INSTANCE_ONLY=true`
- 当前部署模型只支持单机或单容器
- 不建议多 worker 并发写
- 不建议多副本横向扩展

当前配置里已经有单实例守卫：

- 当数据库仍为 SQLite 且 `APP_SERVER_WORKERS` / `WEB_CONCURRENCY` 大于 `1` 时
- `local` 模式给出警告
- `production` 模式直接拒绝启动

## 运行根路径设计

本轮已经统一了运行根路径：

- `APP_RUNTIME_ROOT`

如果不显式配置，默认回落到项目目录；如果显式配置，所有相对运行路径都会收束到这个根目录下。当前核心目录分层如下：

- `DATA_ROOT`
- `STORAGE_ROOT`
- `EXPORTS_ROOT`
- `ARCHIVE_ROOT`

在此基础上继续派生实际叶子路径：

- `DATABASE_PATH`
- `TEMP_UPLOAD_ROOT`
- `FILE_LIBRARY_ROOT`
- `EXPORT_ROOT`
- `REPORT_EXPORT_ROOT`
- `RAW_DATA_ROOT`
- `REVIEW_DATA_ROOT`
- `VERIFICATION_DATA_ROOT`
- `LINKED_DATA_ROOT`
- `LOG_ROOT`

这意味着后续上云时，可以通过一个 `APP_RUNTIME_ROOT` 或几个分类根路径，把运行数据整体挂到持久卷，而不必再把路径散着绑在当前工作目录上。

## 哪些目录需要持久化

当前推荐持久化这些运行目录：

- `DATA_ROOT`
  默认包含 SQLite 数据库和运行期数据归档。
- `STORAGE_ROOT`
  默认包含上传缓存、文件库和日志。
- `EXPORTS_ROOT`
  默认包含 PDF 导出与重建报告。
- `ARCHIVE_ROOT`
  默认仍落在 `data/processed/archive_parsed/`，用于运行期底稿归档。

补充说明：

- 项目根目录下的 `archive/` 当前是历史审阅材料归档区，不是运行时写入目录。
- 运行期 archive 路径由 `ARCHIVE_ROOT` 配置控制。

## 日志与备份建议

当前还不做完整云平台接入，但部署姿态已经需要按“服务端应用”来准备：

- `LOG_ROOT`
  建议放在 `STORAGE_ROOT/logs` 或同类持久卷目录，不要让日志跟随临时容器目录一起丢失。
- SQLite 备份
  至少覆盖 `DATABASE_PATH`。推荐按天备份，并在大批上传、重建前或升级前额外做一次快照。
- 文件与导出备份
  至少评估 `STORAGE_ROOT`、`EXPORTS_ROOT`、`ARCHIVE_ROOT` 是否需要跟随数据库同周期备份；如果这些目录承载业务原件或追溯材料，建议同步纳入。
- 保留原则
  `exports/` 和运行期 `archive/` 可按业务需要做较短保留；数据库和文件库应优先保证可恢复性。

## 启动时的目录初始化与守卫

应用启动时会自动执行：

1. 目录初始化
2. 关键目录可写性检查

当前重点检查：

- `DATA_ROOT`
- `STORAGE_ROOT`
- `EXPORTS_ROOT`
- `ARCHIVE_ROOT`
- 数据库父目录

如果关键目录不存在，会自动创建；如果关键目录不可写，启动会直接失败并给出清晰错误，而不是等到上传或导出时再炸。

## 本地启动

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 复制配置模板

- 源文件：`config/local_settings.example.json`
- 目标文件：`config/local_settings.json`

3. 至少修改以下字段

- `APP_ENV`
- `SECRET_KEY`
- `ADMIN_PASSWORD` 或 `ADMIN_PASSWORD_HASH`
- `INITIAL_ADMIN_ACCESS_CODE`
- `INITIAL_VIEWER_ACCESS_CODE`
- `APP_RUNTIME_ROOT`

4. 启动本地入口

```bash
python run.py
```

## 单实例服务进程运行

当前阶段的服务器启动只要求把程序跑成单实例服务进程，不要求在这一轮完成完整云部署。

推荐方式：

```bash
waitress-serve --listen=0.0.0.0:5050 wsgi:app
```

或任何等价的单实例 WSGI 运行方式，但要遵守：

- 入口使用 `wsgi:app`
- 保持单进程 / 单实例姿态
- 如果后续改用支持 worker 的 WSGI 服务器，worker 数也必须为 `1`
- 运行目录挂到持久卷
- 不要继续依赖 `run.py`

## production 模式继续拦截的风险

当 `APP_ENV=production` 时，程序会在启动前继续校验：

- `SECRET_KEY`
- `SESSION_COOKIE_SECURE=true`
- `BOOTSTRAP_ADMIN_ENABLED=false`
- 默认管理员口令 / 默认访问码不能继续使用
- `HIDE_INTERNAL_PATHS=true`
- 必须有真实配置来源
- SQLite 下 `APP_SERVER_WORKERS` 不能大于 `1`

## PUBLIC_BASE_URL

本轮把 `PUBLIC_BASE_URL` 从“占位字段”推进成了真正的准备层配置：

- 本地可留空
- 服务器 / 域名环境下应显式填写完整公网基础地址，例如 `https://intel.example.com`
- 只能填写基础地址，不要带 path、query、fragment
- 当前已经参与 `next` / 登录回跳 / 页面回跳的合法来源判断
- 后续如接反向代理或 HTTPS，外部域名语义应优先以它为准

## TRUST_PROXY_HEADERS

如果未来接入反向代理，本轮也预留了：

- `TRUST_PROXY_HEADERS`
- `PROXY_FIX_X_FOR`
- `PROXY_FIX_X_PROTO`
- `PROXY_FIX_X_HOST`
- `PROXY_FIX_X_PORT`
- `PROXY_FIX_X_PREFIX`

当前默认保持关闭。只有在你明确把应用放在“自己可控的可信反向代理”后面时，才应显式打开；不要无脑信任所有转发头。

## 文档入口

- `docs/RUN_GUIDE.md`
- `docs/specs/TEMPLATE_SPEC_v2.md`
- `docs/specs/CN_闻脉台_豆包稳定输出指令模板_v2.md`
- `docs/specs/CN_闻脉台_持续跟踪标题规范.md`
- `docs/CN_闻脉台_收尾状态说明_20260420.md`
- `deploy/部署说明.md`

## 常用脚本

```bash
python run.py
python tests/smoke_test.py
python tests/runtime_config_guard_test.py
python tests/single_instance_runtime_test.py
python tests/proxy_public_base_url_test.py
python scripts/export_review_bundle.py
```

## 当前这一阶段没有做的事

这一轮只做了服务进程方式、`PUBLIC_BASE_URL`、安全回跳和部署说明收口，没有动：

- parser / rebuild_engine
- services / db 主逻辑
- 前台模板 / style / js
- 上传契约
- business_tags
- MySQL / Redis / 对象存储
- 正式云部署与完整反向代理配置
