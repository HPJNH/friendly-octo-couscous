from .utils import normalize_compare_text


SECTION_DEFINITIONS = [
    {
        "number": 1,
        "key": "report_note",
        "title": "报告说明",
        "aliases": ["报告说明", "本期说明", "监测说明", "概览说明"],
    },
    {
        "number": 2,
        "key": "brand_alert",
        "title": "自身品牌提醒",
        "aliases": ["自身品牌提醒", "品牌提醒", "自有品牌提醒", "我方品牌提醒"],
    },
    {
        "number": 3,
        "key": "focus_targets",
        "title": "重点对象动态",
        "aliases": ["重点对象动态", "重点监测对象动态", "重点品牌动态", "重点对象追踪"],
    },
    {
        "number": 4,
        "key": "own_track",
        "title": "自身主赛道情报",
        "aliases": ["自身主赛道情报", "主赛道情报", "核心赛道情报", "自身赛道情报", "主赛道观察"],
    },
    {
        "number": 5,
        "key": "reference_brands",
        "title": "邻近参考品牌观察",
        "aliases": ["邻近参考品牌观察", "参考品牌观察", "邻近品牌观察", "竞品观察"],
    },
    {
        "number": 6,
        "key": "themed_tracks",
        "title": "主题型赛道观察",
        "aliases": ["主题型赛道观察", "主题赛道观察", "专题赛道观察", "主题型观察"],
    },
    {
        "number": 7,
        "key": "consumption_trends",
        "title": "消费趋势与市场风向",
        "aliases": ["消费趋势与市场风向", "消费趋势", "市场风向", "趋势与风向", "消费与市场风向"],
    },
    {
        "number": 8,
        "key": "policy_env",
        "title": "政策与企业发展情报",
        "aliases": ["政策与企业发展情报", "政策与企业发展", "政策情报", "企业发展情报", "政策及企业发展"],
    },
    {
        "number": 9,
        "key": "international_market",
        "title": "国际区市场动态",
        "aliases": ["国际区市场动态", "国际市场动态", "海外市场动态", "国际区动态"],
    },
    {
        "number": 10,
        "key": "douyin_monitoring",
        "title": "抖音内容与博主监测",
        "aliases": ["抖音内容与博主监测", "抖音内容监测", "抖音博主监测"],
    },
]

SECTION_ORDER = [item["key"] for item in SECTION_DEFINITIONS]
SECTION_MAP = {item["key"]: item for item in SECTION_DEFINITIONS}
SECTION_KEY_ALIASES = {
    "core_track": "own_track",
    "theme_tracks": "themed_tracks",
    "consumer_trends": "consumption_trends",
    "policy_enterprise": "policy_env",
}
SOFT_HIDDEN_SECTION_KEYS = {"douyin_monitoring"}
VISIBLE_SECTION_DEFINITIONS = [
    item for item in SECTION_DEFINITIONS if item["key"] not in SOFT_HIDDEN_SECTION_KEYS
]
VISIBLE_SECTION_ORDER = [item["key"] for item in VISIBLE_SECTION_DEFINITIONS]
VISIBLE_SECTION_MAP = {item["key"]: item for item in VISIBLE_SECTION_DEFINITIONS}
SECTION_UI_GROUPS = [
    {
        "key": "core",
        "title": "核心情报",
        "description": "优先查看变化最快、判断价值最高的核心情报。",
        "section_keys": [
            "focus_targets",
            "own_track",
            "policy_env",
            "consumption_trends",
            "international_market",
        ],
    },
    {
        "key": "reference",
        "title": "参考观察",
        "description": "补充品牌、主题与参考样本的持续观察。",
        "section_keys": [
            "brand_alert",
            "reference_brands",
            "themed_tracks",
        ],
    },
    {
        "key": "method",
        "title": "说明与方法",
        "description": "查看本期口径、编制原则与阅读边界。",
        "section_keys": [
            "report_note",
        ],
    },
]
FEATURED_SECTION_KEYS = [
    "focus_targets",
    "own_track",
    "policy_env",
    "consumption_trends",
    "international_market",
]
BRIEF_UI_ENABLED = False
BRIEF_EXPORT_ENABLED = False
PARSER_VERSION = "7.3"

DRAFT_MAIN_TITLE = "沉香行业情报研究底稿"
DRAFT_REPORT_NOTE_SUBSECTIONS = [
    ("1.1", "数据与规则"),
    ("1.2", "编制原则"),
]
DRAFT_STANDARD_SUBSECTIONS = [
    ("1", "本期新增"),
    ("2", "近72小时重点"),
    ("3", "延伸背景"),
    ("4", "板块判断"),
]
DRAFT_STANDARD_SUBSECTION_ALIASES = {
    "1": ["补采窗口内新增信号"],
    "2": ["近72小时重点新信号"],
    "3": ["背景补充"],
    "4": ["当前状态说明"],
}
DRAFT_STRUCTURED_TABLE_COLUMNS = [
    "标题",
    "时间",
    "来源层级",
    "来源",
    "核心内容",
    "为什么值得纳入",
]
DRAFT_STRUCTURED_TABLE_COLUMNS_V2 = [
    "标题",
    "时间",
    "来源层级",
    "来源",
    "原始链接",
    "核心内容",
    "本次新增事实",
    "业务标签",
    "为什么值得纳入",
]
DRAFT_WINDOW_METADATA_LABELS = {
    "patch_window": ["本期新增窗口", "补采窗口", "本期窗口"],
    "focus_window": ["近72小时窗口", "近72小时重点窗口", "重点窗口"],
}
DRAFT_TAIL_PATTERNS = [
    "需要我把这份底稿压缩成",
    "需要我把这份底稿整理成",
    "需要我继续",
    "如果你需要",
    "要不要我继续",
    "是否需要我继续",
    "文档部分内容可能由 AI 生成",
    "内容可能由 AI 生成",
    "如需我继续",
]

LEGACY_V1_FUZZY_MATCH_ENABLED = False
LEGACY_V1_FUZZY_MATCH_THRESHOLD = 0.88
LEGACY_FUZZY_LINK_BACKFILL_ENABLED = False
LEGACY_FUZZY_LINK_BACKFILL_THRESHOLD = 0.9

STATUS_CLASS_MAP = {
    "新增": "tag-new",
    "更新": "tag-update",
    "背景补充": "tag-background",
    "历史保留": "tag-retained",
    "占位项": "tag-placeholder",
    "待人工复核": "tag-review",
    "删除": "tag-deleted-soft",
    "无内容": "tag-empty",
}

FILE_STATUS_LABELS = {
    "active": "启用",
    "archived": "已归档",
    "withdrawn": "已撤回",
    "deleted": "已删除",
}

FILE_STATUS_CLASS_MAP = {
    "active": "tag-active",
    "archived": "tag-archived",
    "withdrawn": "tag-withdrawn",
    "deleted": "tag-deleted",
}

DOCUMENT_TYPE_LABELS = {
    "brief": "每日分析简报",
    "draft": "沉香行业情报研究底稿",
    "export": "导出文件",
    "unknown": "未识别",
}

BRIEF_KEYWORDS = ["每日分析简报", "分析简报", "简报"]
DRAFT_KEYWORDS = ["沉香行业情报研究底稿", "研究底稿", "行业情报底稿", "底稿"]
SUPPORTED_EXTENSIONS = {".docx", ".md", ".txt", ".pdf"}

READING_TRACKS_V1 = [
    {
        "key": "brand_dynamic",
        "title": "品牌自身动态赛道",
        "description": "优先阅读品牌自身发布、产品、活动与资质动作。",
        "section_keys": ["brand_alert"],
    },
    {
        "key": "competitor_watch",
        "title": "竞品对标动态赛道",
        "description": "持续跟进核心竞品、权威机构与关键人物动态。",
        "section_keys": ["focus_targets"],
    },
    {
        "key": "core_origin_industry",
        "title": "核心产区产业赛道",
        "description": "查看核心产区、价格交易、标准与产业链延伸信号。",
        "section_keys": ["own_track"],
    },
    {
        "key": "premium_benchmark_brands",
        "title": "高端香氛对标品牌赛道",
        "description": "沉淀高端香氛品牌的参考样本与方法对标。",
        "section_keys": ["reference_brands"],
    },
    {
        "key": "fragrance_innovation",
        "title": "香氛细分创新赛道",
        "description": "追踪细分香氛场景与创新方向的持续变化。",
        "section_keys": ["themed_tracks"],
    },
    {
        "key": "consumer_trends",
        "title": "消费市场趋势赛道",
        "description": "观察消费偏好、零售渠道与市场风向的变化。",
        "section_keys": ["consumption_trends"],
    },
    {
        "key": "policy_environment",
        "title": "产业政策环境赛道",
        "description": "集中查看国家、省市及自贸港相关政策环境。",
        "section_keys": ["policy_env"],
    },
    {
        "key": "global_market",
        "title": "全球市场国际赛道",
        "description": "浏览海外重点区域与全球香氛行业共性趋势。",
        "section_keys": ["international_market"],
    },
]

TRACK_DISPLAY_MAP = {
    "report_note": {
        "track_key": "reading_note",
        "track_title": "阅读说明",
        "section_title": "报告说明",
        "nav_title": "阅读说明",
    },
    "brand_alert": {
        "track_key": "brand_dynamic",
        "track_title": "品牌自身动态赛道",
        "section_title": "自身品牌提醒",
        "nav_title": "品牌自身动态赛道",
    },
    "focus_targets": {
        "track_key": "competitor_watch",
        "track_title": "竞品对标动态赛道",
        "section_title": "重点对象动态",
        "nav_title": "竞品对标动态赛道",
    },
    "own_track": {
        "track_key": "core_origin_industry",
        "track_title": "核心产区产业赛道",
        "section_title": "自身主赛道情报",
        "nav_title": "核心产区产业赛道",
    },
    "reference_brands": {
        "track_key": "premium_benchmark_brands",
        "track_title": "高端香氛对标品牌赛道",
        "section_title": "邻近参考品牌观察",
        "nav_title": "高端香氛对标品牌赛道",
    },
    "themed_tracks": {
        "track_key": "fragrance_innovation",
        "track_title": "香氛细分创新赛道",
        "section_title": "主题型赛道观察",
        "nav_title": "香氛细分创新赛道",
    },
    "consumption_trends": {
        "track_key": "consumer_trends",
        "track_title": "消费市场趋势赛道",
        "section_title": "消费趋势与市场风向",
        "nav_title": "消费市场趋势赛道",
    },
    "policy_env": {
        "track_key": "policy_environment",
        "track_title": "产业政策环境赛道",
        "section_title": "政策与企业发展情报",
        "nav_title": "产业政策环境赛道",
    },
    "international_market": {
        "track_key": "global_market",
        "track_title": "全球市场国际赛道",
        "section_title": "国际区市场动态",
        "nav_title": "全球市场国际赛道",
    },
    "douyin_monitoring": {
        "track_key": "hidden",
        "track_title": "抖音内容与博主监测",
        "section_title": "抖音内容与博主监测",
        "nav_title": "抖音内容与博主监测",
    },
}

TRACK_SUBTRACK_RULES = {
    "brand_dynamic": [
        {
            "key": "brand_release",
            "display_label": "A. 品牌发布与文化升级",
            "tag_keys": ["brand_release", "品牌发布", "文化升级", "品牌升级"],
            "keywords": ["发布", "发布会", "品牌焕新", "文化升级", "升级", "品牌主张"],
        },
        {
            "key": "product_innovation",
            "display_label": "B. 产品创新与新品动作",
            "tag_keys": ["product_innovation", "新品动作", "产品创新", "新品"],
            "keywords": ["新品", "新系列", "上线", "发售", "发布新品", "产品"],
        },
        {
            "key": "exhibition_activity",
            "display_label": "C. 线下展陈与艺术活动",
            "tag_keys": ["exhibition_activity", "展陈动作", "艺术活动", "线下展陈"],
            "keywords": ["艺术展", "展陈", "展览", "快闪", "活动", "品鉴会"],
        },
        {
            "key": "channel_commercialization",
            "display_label": "D. 渠道合作与商业落地",
            "tag_keys": ["channel_commercialization", "渠道合作", "商业落地", "渠道"],
            "keywords": ["渠道", "合作", "旗舰店", "入驻", "展售", "开店", "商业"],
        },
        {
            "key": "qualification_patent",
            "display_label": "E. 企业资质与技术专利",
            "tag_keys": ["qualification_patent", "企业资质", "技术专利", "资质"],
            "keywords": ["资质", "专利", "认证", "地理标志", "证明商标", "授权"],
        },
        {
            "key": "industrial_layout",
            "display_label": "F. 产业布局与社会责任",
            "tag_keys": ["industrial_layout", "产业布局", "社会责任", "乡村振兴"],
            "keywords": ["布局", "乡村振兴", "社会责任", "产业园", "基地", "联农", "公益"],
        },
    ],
    "competitor_watch": [
        {
            "key": "hainan_core_competitors",
            "display_label": "A. 海南本土核心竞品动态",
            "tag_keys": ["hainan_core_competitors", "海南本土核心竞品动态"],
            "keywords": ["大观", "楠脂", "海南本土", "竞品"],
        },
        {
            "key": "benchmark_institutions",
            "display_label": "B. 行业标杆机构与馆藏动态",
            "tag_keys": ["benchmark_institutions", "行业标杆机构与馆藏动态"],
            "keywords": ["博物馆", "馆藏", "机构", "协会", "研究院"],
        },
        {
            "key": "authoritative_figures",
            "display_label": "C. 香文化领域权威人物动态",
            "tag_keys": ["authoritative_figures", "香文化领域权威人物动态"],
            "keywords": ["傅京亮", "权威人物", "专家", "大师", "人物"],
        },
        {
            "key": "competitor_background",
            "display_label": "D. 竞品背景与长期战略补充",
            "tag_keys": ["competitor_background", "竞品背景与长期战略补充"],
            "keywords": ["背景", "长期", "战略", "补充", "简介"],
        },
    ],
    "core_origin_industry": [
        {
            "key": "origin_hainan_danzhou",
            "display_label": "A. 海南 / 儋州本土主产区动态",
            "tag_keys": ["origin_hainan_danzhou", "海南 / 儋州本土主产区动态", "海南", "儋州"],
            "keywords": ["海南", "儋州", "洋浦", "南丰"],
        },
        {
            "key": "origin_maoming_dianbai",
            "display_label": "B. 茂名 / 电白全国核心主产区动态",
            "tag_keys": ["origin_maoming_dianbai", "茂名 / 电白全国核心主产区动态", "茂名", "电白", "观珠"],
            "keywords": ["茂名", "电白", "观珠"],
        },
        {
            "key": "price_trade",
            "display_label": "C. 沉香价格与交易市场信号",
            "tag_keys": ["price_trade", "沉香价格与交易市场信号", "价格与交易"],
            "keywords": ["价格", "交易", "成交", "报价", "拍卖", "市场价"],
        },
        {
            "key": "traceability_standard",
            "display_label": "D. 行业标准与溯源体系建设",
            "tag_keys": ["traceability_standard", "行业标准与溯源体系建设", "标准", "溯源"],
            "keywords": ["标准", "溯源", "协会", "认证", "规范"],
        },
        {
            "key": "industry_extension",
            "display_label": "E. 产业链延伸与融合发展动向",
            "tag_keys": ["industry_extension", "产业链延伸与融合发展动向", "产业链延伸"],
            "keywords": ["产业链", "延伸", "融合", "跨界", "文旅", "康养"],
        },
    ],
    "premium_benchmark_brands": [
        {
            "key": "guanxia",
            "display_label": "A. 观夏品牌全维度动态",
            "tag_keys": ["guanxia", "观夏品牌全维度动态", "观夏"],
            "keywords": ["观夏"],
        },
        {
            "key": "wenxian",
            "display_label": "B. 闻献品牌全维度动态",
            "tag_keys": ["wenxian", "闻献品牌全维度动态", "闻献"],
            "keywords": ["闻献"],
        },
        {
            "key": "other_premium_brands",
            "display_label": "C. 其他高端香氛品牌参考样本",
            "tag_keys": ["other_premium_brands", "其他高端香氛品牌参考样本"],
            "keywords": ["品牌", "香氛", "样本", "对标"],
        },
    ],
    "fragrance_innovation": [
        {
            "key": "fragrance_paint",
            "display_label": "A. 香氛涂料",
            "tag_keys": ["fragrance_paint", "香氛涂料"],
            "keywords": ["香氛涂料", "涂料"],
        },
        {
            "key": "space_home_fragrance",
            "display_label": "B. 空间香 / 家居香氛",
            "tag_keys": ["space_home_fragrance", "space_fragrance", "home_fragrance", "空间香", "家居香氛", "空间香氛"],
            "keywords": ["空间香", "家居香氛", "空间香氛", "家居", "扩香"],
        },
        {
            "key": "emotional_fragrance",
            "display_label": "C. 情绪香氛",
            "tag_keys": ["emotional_fragrance", "情绪香氛"],
            "keywords": ["情绪香氛", "情绪", "疗愈", "放松"],
        },
        {
            "key": "agarwood_space_daily",
            "display_label": "D. 沉香 + 空间 / 沉香 + 日用",
            "tag_keys": ["agarwood_space_daily", "agarwood_space", "agarwood_daily", "沉香+空间", "沉香 + 空间", "沉香+日用", "沉香 + 日用"],
            "keywords": ["沉香+空间", "沉香 + 空间", "沉香+日用", "沉香 + 日用", "日用"],
        },
        {
            "key": "eastern_aesthetics",
            "display_label": "E. 东方香氛美学 / 高端香氛市场",
            "tag_keys": ["eastern_aesthetics", "东方香氛美学", "高端香氛市场"],
            "keywords": ["东方香氛", "美学", "高端香氛", "东方美学"],
        },
        {
            "key": "cultural_space",
            "display_label": "F. 香文化空间体验",
            "tag_keys": ["cultural_space", "香文化空间体验"],
            "keywords": ["香文化空间", "空间体验", "沉浸式", "体验空间"],
        },
    ],
    "consumer_trends": [
        {
            "key": "oriental_fragrance_consumer",
            "display_label": "A. 东方香氛消费趋势",
            "tag_keys": ["oriental_fragrance_consumer", "东方香氛消费趋势"],
            "keywords": ["东方香氛", "东方香调", "国风香氛"],
        },
        {
            "key": "premium_fragrance_consumer",
            "display_label": "B. 高端香氛消费趋势",
            "tag_keys": ["premium_fragrance_consumer", "高端香氛消费趋势"],
            "keywords": ["高端香氛", "高端消费", "奢香"],
        },
        {
            "key": "home_space_consumer",
            "display_label": "C. 家居香氛 / 空间香消费趋势",
            "tag_keys": ["home_space_consumer", "家居香氛 / 空间香消费趋势", "家居香氛", "空间香"],
            "keywords": ["家居香氛", "空间香", "空间香氛", "家居"],
        },
        {
            "key": "emotional_consumer",
            "display_label": "D. 情绪香氛 / 放松消费趋势",
            "tag_keys": ["emotional_consumer", "情绪香氛 / 放松消费趋势", "放松消费趋势"],
            "keywords": ["情绪香氛", "放松", "助眠", "疗愈"],
        },
        {
            "key": "young_consumer_preference",
            "display_label": "E. 年轻消费者香氛偏好",
            "tag_keys": ["young_consumer_preference", "年轻消费者香氛偏好"],
            "keywords": ["年轻", "Z世代", "青年消费者", "年轻消费者"],
        },
        {
            "key": "retail_channel_shift",
            "display_label": "F. 渠道与零售模式变化趋势",
            "tag_keys": ["retail_channel_shift", "渠道与零售模式变化趋势"],
            "keywords": ["零售", "渠道", "电商", "门店", "零售模式"],
        },
    ],
    "policy_environment": [
        {
            "key": "national_policy",
            "display_label": "A. 国家层产业政策与扶持",
            "tag_keys": ["national_policy", "国家层产业政策与扶持"],
            "keywords": ["国家", "中央", "部委", "国家层"],
        },
        {
            "key": "hainan_policy",
            "display_label": "B. 海南省层产业政策与招商",
            "tag_keys": ["hainan_policy", "海南省层产业政策与招商"],
            "keywords": ["海南省", "海南", "省级", "招商"],
        },
        {
            "key": "danzhou_yangpu_policy",
            "display_label": "C. 儋州 / 洋浦层产业政策与落地",
            "tag_keys": ["danzhou_yangpu_policy", "儋州 / 洋浦层产业政策与落地", "儋州", "洋浦"],
            "keywords": ["儋州", "洋浦"],
        },
        {
            "key": "free_trade_port_policy",
            "display_label": "D. 自贸港专项政策与红利",
            "tag_keys": ["free_trade_port_policy", "自贸港专项政策与红利", "自贸港"],
            "keywords": ["自贸港", "封关", "海南自由贸易港"],
        },
    ],
    "global_market": [
        {
            "key": "europe_market",
            "display_label": "A. 欧洲市场动态",
            "tag_keys": ["europe_market", "欧洲市场动态", "欧洲"],
            "keywords": ["欧洲", "欧盟", "法国", "意大利", "英国", "德国"],
        },
        {
            "key": "middle_east_market",
            "display_label": "B. 中东市场动态",
            "tag_keys": ["middle_east_market", "中东市场动态", "中东"],
            "keywords": ["中东", "迪拜", "阿联酋", "沙特"],
        },
        {
            "key": "japan_market",
            "display_label": "C. 日本市场动态",
            "tag_keys": ["japan_market", "日本市场动态", "日本"],
            "keywords": ["日本", "东京"],
        },
        {
            "key": "korea_market",
            "display_label": "D. 韩国市场动态",
            "tag_keys": ["korea_market", "韩国市场动态", "韩国"],
            "keywords": ["韩国", "首尔"],
        },
        {
            "key": "global_fragrance_trends",
            "display_label": "E. 全球香氛行业共性趋势",
            "tag_keys": ["global_fragrance_trends", "全球香氛行业共性趋势"],
            "keywords": ["全球", "国际趋势", "行业共性", "全球香氛"],
        },
    ],
}


def _build_business_tag_canonical_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rules in TRACK_SUBTRACK_RULES.values():
        for rule in rules:
            canonical_key = rule["key"]
            alias_values = [canonical_key, rule.get("display_label", ""), *rule.get("tag_keys", [])]
            for alias in alias_values:
                normalized = normalize_compare_text(str(alias))
                if normalized and normalized not in mapping:
                    mapping[normalized] = canonical_key
    return mapping


BUSINESS_TAG_CANONICAL_MAP = _build_business_tag_canonical_map()
BUSINESS_TAG_DISPLAY_MAP = {
    rule["key"]: rule["display_label"]
    for rules in TRACK_SUBTRACK_RULES.values()
    for rule in rules
}
BUSINESS_TAG_MACHINE_KEYS = sorted(BUSINESS_TAG_DISPLAY_MAP)

FRONTEND_READING_CATEGORIES = [dict(item) for item in READING_TRACKS_V1]

FRONTEND_SECTION_DISPLAY = {
    section_key: {
        "category_key": meta["track_key"],
        "category_title": meta["track_title"],
        "section_title": meta["section_title"],
        "view_label": "",
        "nav_title": meta["nav_title"],
    }
    for section_key, meta in TRACK_DISPLAY_MAP.items()
}

WORKBENCH_SHORTCUT_DEFINITIONS = [
    {
        "key": "today_focus",
        "title": "今日重点",
        "description": "优先查看今天最值得先看的行业动向。",
        "anchor": "today-focus",
    },
    {
        "key": "today_new",
        "title": "今日新增",
        "description": "快速进入今天新增最集中的阅读入口。",
        "anchor": "today-new",
    },
    {
        "key": "recent_changes",
        "title": "近期变化",
        "description": "回看最近几个版本的连续变化。",
        "anchor": "recent-versions",
    },
    {
        "key": "history_archive",
        "title": "历史归档",
        "description": "进入历史时间线查看完整版本轨迹。",
        "anchor": "",
    },
]

FRONTEND_SECONDARY_LABELS = {
    "1": "本期新增",
    "2": "近72小时重点",
    "3": "延伸背景",
    "4": "板块判断",
}

REPORT_NOTE_DISPLAY_LABELS = {
    "1.1": "数据与规则",
    "1.2": "编制原则",
}

FRONTEND_STATUS_LABELS = {
    "新增": "新增",
    "更新": "更新",
    "背景补充": "背景延伸",
    "历史保留": "历史延续",
    "待人工复核": "待复核",
    "占位项": "本期无新增",
    "无内容": "本期无新增",
}

FRONTEND_STATUS_CLASS_MAP = {
    "新增": "tag-new",
    "更新": "tag-update",
    "背景延伸": "tag-background",
    "历史延续": "tag-retained",
    "待复核": "tag-review",
    "本期无新增": "tag-empty",
}

FRONTEND_STATUS_ORDER = [
    "新增",
    "更新",
    "背景延伸",
    "历史延续",
    "待复核",
    "本期无新增",
]

SECTION_SUBCATEGORY_RULES = {
    section_key: [
        {
            "key": rule["key"],
            "title": rule["display_label"],
            "tag_keys": rule.get("tag_keys", []),
            "keywords": rule["keywords"],
        }
        for rule in TRACK_SUBTRACK_RULES.get(meta["track_key"], [])
    ]
    for section_key, meta in TRACK_DISPLAY_MAP.items()
    if meta["track_key"] not in {"reading_note", "hidden"}
}
