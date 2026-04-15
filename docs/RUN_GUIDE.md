# 运行说明

## 1. 环境要求

- Python 3.11+
- Windows 本地环境优先
- 浏览器访问

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

Windows 下也可以双击：

- `安装依赖.bat`

## 3. 准备配置文件

1. 复制：

- `config/local_settings.example.json`

2. 新建本地配置文件：

- `config/local_settings.json`

3. 至少修改这些字段：

- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `INITIAL_ADMIN_ACCESS_CODE`
- `INITIAL_VIEWER_ACCESS_CODE`
- `LAN_ACCESS_HOST`

## 4. 启动系统

```bash
python run.py
```

Windows 下也可以双击：

- `启动程序.bat`

## 5. 访问地址

默认端口为 `5050`。

- 本机访问：`http://127.0.0.1:5050`
- 局域网访问：`http://192.168.1.2:5050`

## 6. 默认权限模型

- `viewer`：只读浏览
- `admin`：上传、撤回、激活、删除、管理访问资格

默认访问码来自 `config/local_settings.json`。

## 7. 首次检查建议

启动后建议先检查：

1. 首页是否可打开
2. 历史页是否可打开
3. 文件库是否可打开
4. section 详情页是否可打开
5. 访问码登录是否正常

## 8. 常用命令

### 冒烟测试

```bash
python tests/smoke_test.py
```

### 迁移与重建

```bash
python scripts/migration_rebuild_entries.py
python scripts/normalize_entry_states.py
python scripts/dedupe_events.py
```

### 生成对外审查包

```bash
python scripts/export_review_bundle.py
```

生成结果会写入：

- `exports/review_packages/`

## 9. 当前运行中会产生的本地文件

- 数据库：`data/database/intelligence_browser.db`
- 文件库：`storage/file_library/`
- 上传缓存：`storage/cache/incoming/`
- 原始上传留存：`storage/uploads/`
- 解析快照：`data/processed/archive_parsed/`
- PDF 导出：`exports/pdf/`
- 报告输出：`exports/reports/`

这些内容都不建议直接提交到 Git。

## 10. 常见接手顺序

1. 先看 `README.md`
2. 再看 `docs/PROJECT_STRUCTURE.md`
3. 再看 `docs/KNOWN_ISSUES.md`
4. 再看 `docs/specs/TEMPLATE_SPEC_v2.md`
5. 最后进入代码：
   - `app/routes.py`
   - `app/services.py`
   - `app/rebuild_engine.py`
