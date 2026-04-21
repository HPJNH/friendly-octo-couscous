# 闻脉台豆包稳定输出指令模板 v2

本文档不是原则讨论稿，而是一份可以直接交给豆包执行的上游模板。目标只有一个：稳定产出与当前系统正式兼容的 `v2 docx` 底稿。

关联规范：

- [TEMPLATE_SPEC_v2.md](./TEMPLATE_SPEC_v2.md)
- [CN_闻脉台_持续跟踪标题规范.md](./CN_闻脉台_持续跟踪标题规范.md)

## 一、硬性要求

请严格遵守以下规则，不要自由发挥：

1. 输出对象是 `Word docx 契约`，不是 Markdown 主生产链路。
2. 正式输出固定使用 `v2 9 列`。
3. 文档主标题固定为 `沉香行业情报研究底稿`。
4. 一级标题固定 10 个，顺序不可改变。
5. 模块 2-10 的二级标题固定为 4 个，不再自由命名。
6. `business_tags` 只能使用 machine key。
7. `delta_text` 只能写“本次新增事实”，不能写解释性改写。
8. `原始链接` 没有可靠来源就留空，不允许编造。
9. 同一事件持续跟踪时，标题必须尽量保持稳定。
10. 不允许在文末追加 AI 尾巴、建议、追问、免责声明。

## 二、固定结构

### 1. 文档主标题

`沉香行业情报研究底稿`

### 2. 固定 10 个一级标题

1. 报告说明
2. 自身品牌提醒
3. 重点对象动态
4. 自身主赛道情报
5. 邻近参考品牌观察
6. 主题型赛道观察
7. 消费趋势与市场风向
8. 政策与企业发展情报
9. 国际区市场动态
10. 抖音内容与博主监测

### 3. 固定二级标题

模块 1 只允许：

- `1.1 数据与规则`
- `1.2 编制原则`

模块 2-10 只允许：

- `x.1 本期新增`
- `x.2 近72小时重点`
- `x.3 延伸背景`
- `x.4 板块判断`

补充说明：

- `x.1 / x.2 / x.3` 必须是表格
- `x.4` 只能是说明段，不是表格
- 不再使用旧二级标题作为正式输出

## 三、固定 9 列表头

模块 `x.1 / x.2 / x.3` 的表格必须严格使用以下 9 列，顺序不可变：

1. 标题
2. 时间
3. 来源层级
4. 来源
5. 原始链接
6. 核心内容
7. 本次新增事实
8. 业务标签
9. 为什么值得纳入

禁止：

- 改列名
- 少列
- 多列
- 调换顺序
- 把结构化区写成自由段落

## 四、显式窗口 metadata

请在 `1.1 数据与规则` 中显式写出：

```text
本期新增窗口：{patch_window_start} 至 {patch_window_end}
近72小时窗口：{focus_window_start} 至 {focus_window_end}
底稿日期：{report_date}
契约版本：v2
```

注意：

- 不要只写“本期”“近三天”“最近窗口”这类模糊词
- 不要把窗口信息埋进长段说明里让程序自己猜

## 五、字段填写规则

### 1. 标题

- 同一事件持续跟踪时尽量保持标题不变
- 标题优先保留“对象 + 动作 + 关键限定词”
- 不要为了修辞或总结感频繁改标题
- 不要加入“重磅”“值得关注”“最新动态”等不稳定评价词

### 2. 原始链接

- 有可靠原始 URL 就填写
- 没有就留空
- 不要写“待补”“暂无”“见附件”这类假占位
- 不要编造链接

### 3. 核心内容

- 只写本条事实本身
- 保持简洁完整
- 不要把判断、总结、价值解释全部塞进去

### 4. 本次新增事实

`delta_text` 只写相对上一有效版本新增加的事实。

可写：

- 新增发布时间
- 新增渠道上线
- 新增价格和规格
- 新增合作对象
- 新增官方口径

不要写：

- 文案更完整了
- 内容更清晰了
- 值得继续关注
- 与 `核心内容` 完全重复的大段摘要

### 5. 业务标签

`business_tags` 只能使用 machine key。

推荐可直接使用的 key：

- `brand_release`
- `product_innovation`
- `exhibition_activity`
- `channel_commercialization`
- `qualification_patent`
- `industrial_layout`
- `hainan_core_competitors`
- `benchmark_institutions`
- `authoritative_figures`
- `competitor_background`
- `origin_hainan_danzhou`
- `origin_maoming_dianbai`
- `price_trade`
- `traceability_standard`
- `industry_extension`
- `guanxia`
- `wenxian`
- `other_premium_brands`
- `fragrance_paint`
- `space_home_fragrance`
- `emotional_fragrance`
- `agarwood_space_daily`
- `eastern_aesthetics`
- `cultural_space`
- `oriental_fragrance_consumer`
- `premium_fragrance_consumer`
- `home_space_consumer`
- `emotional_consumer`
- `young_consumer_preference`
- `retail_channel_shift`
- `national_policy`
- `hainan_policy`
- `danzhou_yangpu_policy`
- `free_trade_port_policy`
- `europe_market`
- `middle_east_market`
- `japan_market`
- `korea_market`
- `global_fragrance_trends`

不要写：

- `空间香 / 家居香氛`
- `家居香氛`
- `国家层产业政策与扶持`

这些是展示词，不是结构层标准值。

## 六、正确示例

下面是一条正确的 v2 行示例：

| 标题 | 时间 | 来源层级 | 来源 | 原始链接 | 核心内容 | 本次新增事实 | 业务标签 | 为什么值得纳入 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 观夏上线空间香氛礼盒 | 2026-04-11 | A2 | 品牌官网 | https://example.com/launch | 观夏发布空间香氛礼盒，并公布上线时间与礼盒规格。 | 新增上线时间和礼盒规格。 | space_home_fragrance | 可用于跟踪空间香氛赛道的新品动作。 |

这条是正确示例，因为：

- 标题稳定，不带修辞
- 原始链接真实存在
- `delta_text` 只写新增事实
- `business_tags` 使用 machine key

## 七、错误示例

下面是一条错误示例：

| 标题 | 时间 | 来源层级 | 来源 | 原始链接 | 核心内容 | 本次新增事实 | 业务标签 | 为什么值得纳入 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 观夏重磅发布超值得关注的空间香氛新动作 | 2026-04-11 | A2 | 品牌官网 | 待补 | 观夏发布空间香氛礼盒，并公布上线时间与礼盒规格。 | 这条内容更完整，更值得关注。 | 空间香 / 家居香氛 | 很重要。 |

这条是错误示例，因为：

- 标题不稳定，混入评价词
- 原始链接不是留空，而是写了无效占位
- `delta_text` 写成解释性判断
- `business_tags` 写成展示词

## 八、可直接复制给豆包的正式指令

```text
请输出一份用于闻脉台系统上传的《沉香行业情报研究底稿》，严格按 docx 主链路契约生成，不要自由发挥文档结构，不要在文末追加任何 AI 说明、追问、总结或免责声明。

一、文档主标题固定为：
沉香行业情报研究底稿

二、一级标题固定为以下 10 个，顺序不可改变：
1. 报告说明
2. 自身品牌提醒
3. 重点对象动态
4. 自身主赛道情报
5. 邻近参考品牌观察
6. 主题型赛道观察
7. 消费趋势与市场风向
8. 政策与企业发展情报
9. 国际区市场动态
10. 抖音内容与博主监测

三、二级标题固定规则：
1. 模块 1 只允许：
   - 1.1 数据与规则
   - 1.2 编制原则
2. 模块 2-10 只允许：
   - x.1 本期新增
   - x.2 近72小时重点
   - x.3 延伸背景
   - x.4 板块判断
3. x.1 / x.2 / x.3 必须写表格
4. x.4 只能写说明段，不写表格

四、请在 1.1 数据与规则 中显式写出：
本期新增窗口：{patch_window_start} 至 {patch_window_end}
近72小时窗口：{focus_window_start} 至 {focus_window_end}
底稿日期：{report_date}
契约版本：v2

五、模块 x.1 / x.2 / x.3 的表格必须严格使用以下 9 列，顺序不可改变：
标题 | 时间 | 来源层级 | 来源 | 原始链接 | 核心内容 | 本次新增事实 | 业务标签 | 为什么值得纳入

六、字段规则：
1. 原始链接：有可靠原始 URL 就填写，没有就留空，不要编造，不要写“待补”。
2. 本次新增事实：只写相对上一有效版本新增了什么事实，不要写解释性改写。
3. 业务标签：只能写 machine key，不要写中文展示词。
4. 同一事件持续跟踪时，标题尽量保持稳定，不要为了修辞而重写标题。

七、推荐使用的 business_tags machine key：
brand_release, product_innovation, exhibition_activity, channel_commercialization, qualification_patent, industrial_layout,
hainan_core_competitors, benchmark_institutions, authoritative_figures, competitor_background,
origin_hainan_danzhou, origin_maoming_dianbai, price_trade, traceability_standard, industry_extension,
guanxia, wenxian, other_premium_brands, fragrance_paint, space_home_fragrance, emotional_fragrance,
agarwood_space_daily, eastern_aesthetics, cultural_space, oriental_fragrance_consumer, premium_fragrance_consumer,
home_space_consumer, emotional_consumer, young_consumer_preference, retail_channel_shift,
national_policy, hainan_policy, danzhou_yangpu_policy, free_trade_port_policy,
europe_market, middle_east_market, japan_market, korea_market, global_fragrance_trends

八、空结果规则：
如果某个 x.1 / x.2 / x.3 没有有效内容，也必须保留合法表格，不要用自由段落替代。

九、本次资料范围：
{source_scope}

十、额外要求：
{extra_requirements}
```

## 九、上游自检清单

导出前请逐项确认：

1. 是否仍是 `docx` 主契约，而不是 Markdown 自由文本
2. 是否固定使用了 10 个一级标题
3. 是否固定使用了 4 个二级标题
4. 是否显式写出了窗口 metadata
5. 是否所有结构化区都使用了 v2 9 列
6. `business_tags` 是否全部为 machine key
7. `delta_text` 是否全部只写新增事实
8. 原始链接缺失时是否真的留空
9. 同一事件跨天跟踪时标题是否保持稳定
10. 是否删除了所有 AI 尾巴
