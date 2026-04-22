# 闻脉台 rebuild 单独验证报告

## 1. 验证前备份位置

- 备份时间：2026-04-22 17:10:44
- 备份目录：`C:\Users\A\Desktop\情报浏览系统_forensic_backups\wenmai_before_rebuild_validation_20260422-171044`

本次备份覆盖了以下关键运行材料：

- `config/local_settings.json`
- `data/database/intelligence_browser.db`
- `data/raw`
- `storage/file_library`
- `data/processed/archive_parsed`

## 2. rebuild 前关键计数

- `entries_all = 548`
- `entries_real = 526`
- `documents = 26`
- `sections = 180`
- `access_identities = 3`
- `entry_marks = 0`

关键目录状态：

- `data/raw`：11 个文件，688485 字节
- `storage/file_library`：26 个文件，1606498 字节
- `data/processed/archive_parsed`：58 个文件，31332820 字节

验证前访问结果：

- 首页未登录访问：`302 -> /access/login?next=/`
- 当时使用一组临时恢复 viewer 访问码：最终 `/`，状态 `200`
- 当时使用一组临时恢复 admin 访问码：最终 `/upload`，状态 `200`
- 上传页 `/upload`：状态 `200`

## 3. rebuild 执行方式

本次只执行了一次受控 rebuild，没有混入目录清理、迁移同步、部署或其他修复动作。

执行命令：

```powershell
python scripts/migration_rebuild_entries.py
```

脚本执行摘要：

- `迁移与重建已完成`
- `entry_count: 293`
- `kept_real_entries: 200`
- `placeholder_entries: 19`
- `deleted_entries: 74`
- `needs_review_entries: 16`
- `display_counts: {'新增': 49, '历史保留': 92, '背景补充': 59, '占位项': 19}`
- `run_key: 20260422-171117-full`

## 4. rebuild 后关键计数

- `entries_all = 548`
- `entries_real = 526`
- `documents = 26`
- `sections = 180`
- `access_identities = 3`
- `entry_marks = 0`

补充观察：

- `entry_type_counts = [('placeholder', 22), ('real', 526)]`

关键目录状态：

- `data/raw`：11 个文件，688485 字节
- `storage/file_library`：26 个文件，1606498 字节
- `data/processed/archive_parsed`：58 个文件，31332820 字节

## 5. 前后差异对比

从主仓库关键运行态来看，本次 rebuild 没有出现以下风险：

- 没有归零
- 没有翻倍
- 没有异常删除核心业务表
- 没有让 `documents / sections / access_identities` 漂移
- 没有破坏 `raw / file_library / archive_parsed` 目录

关键计数前后对比：

| 指标 | rebuild 前 | rebuild 后 | 结论 |
| --- | ---: | ---: | --- |
| entries_all | 548 | 548 | 无异常 |
| entries_real | 526 | 526 | 无异常 |
| documents | 26 | 26 | 无异常 |
| sections | 180 | 180 | 无异常 |
| access_identities | 3 | 3 | 无异常 |
| entry_marks | 0 | 0 | 无异常 |

说明：

- `migration_rebuild_entries.py` 输出中的 `entry_count: 293` 是脚本内部这次重建过程的摘要，不等于主库最终总条目数。
- 从最终数据库计数和页面行为看，本次 rebuild 没有把当前恢复后的主仓库打成空壳，也没有制造明显重复。

## 6. 首页 / viewer / admin / upload 验证结果

rebuild 后重新按真实表单流程验证：

- 首页未登录访问：`302 -> /access/login?next=/`
- 当时使用一组临时恢复 viewer 访问码：最终 `/`，状态 `200`
- 当时使用一组临时恢复 admin 访问码：最终 `/upload`，状态 `200`
- 上传页 `/upload`：状态 `200`

相关回归：

- `python tests/smoke_test.py`：通过
- `python tests/runtime_config_guard_test.py`：通过
- `python tests/single_instance_runtime_test.py`：通过

## 7. rebuild 是否安全

结论：**本次单独 rebuild 验证通过，可以认为当前 rebuild 在这份已恢复主仓库运行态上是安全的。**

理由：

1. rebuild 前有独立冻结备份
2. rebuild 只执行一次
3. 核心数据库计数前后保持稳定
4. 关键运行目录未被清空或替换
5. 首页、viewer、admin、upload 全部仍然可访问

## 8. 若失败，是否已恢复

本次 rebuild 验证**未失败**，因此没有触发回滚恢复。

如果后续还要做进一步 rebuild 相关试验，应继续以本次验证前备份目录作为首选回退点：

- `C:\Users\A\Desktop\情报浏览系统_forensic_backups\wenmai_before_rebuild_validation_20260422-171044`

## 9. 当前是否还能进入部署阶段

从“rebuild 是否安全”这一点看，当前主仓库已经比恢复前更接近部署前准备阶段。

但本轮结论仍然是：

- **可以进入下一步部署准备评估**
- **当前不建议立刻部署**
- **当前不建议立刻 push**

更稳妥的下一步是：

1. 保持当前状态为可信运行基线
2. 基于本次验证结果继续做部署前准备检查
3. 在真正部署前，再单独确认配置、路径、服务进程和外部环境接线
