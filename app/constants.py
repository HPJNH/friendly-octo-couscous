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
PARSER_VERSION = "7.0"

DRAFT_MAIN_TITLE = "沉香行业情报研究底稿"
DRAFT_REPORT_NOTE_SUBSECTIONS = [
    ("1.1", "数据与规则"),
    ("1.2", "编制原则"),
]
DRAFT_STANDARD_SUBSECTIONS = [
    ("1", "补采窗口内新增信号"),
    ("2", "近72小时重点新信号"),
    ("3", "背景补充"),
    ("4", "当前状态说明"),
]
DRAFT_STRUCTURED_TABLE_COLUMNS = [
    "标题",
    "时间",
    "来源层级",
    "来源",
    "核心内容",
    "为什么值得纳入",
]
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

FRONTEND_READING_CATEGORIES = [
    {
        "key": "our_focus",
        "title": "我方与重点对象",
        "description": "集中阅读我方动作与重点对象的最新变化。",
        "section_keys": ["brand_alert", "focus_targets"],
    },
    {
        "key": "core_business",
        "title": "核心业务与产区",
        "description": "聚焦沉香核心业务、产区、交易与产业链延伸。",
        "section_keys": ["own_track"],
    },
    {
        "key": "theme_track",
        "title": "主题赛道",
        "description": "围绕重点主题赛道继续跟进新增与延伸背景。",
        "section_keys": ["themed_tracks"],
    },
    {
        "key": "reference_samples",
        "title": "参考品牌与方法样本",
        "description": "沉淀可参考的品牌动作、内容表达与方法样本。",
        "section_keys": ["reference_brands"],
    },
    {
        "key": "market_trends",
        "title": "市场与消费趋势",
        "description": "查看市场风向、消费趋势与需求变化。",
        "section_keys": ["consumption_trends"],
    },
    {
        "key": "policy_environment",
        "title": "政策与产业环境",
        "description": "跟踪政策、企业发展和产业环境的关键变化。",
        "section_keys": ["policy_env"],
    },
    {
        "key": "international_market_reading",
        "title": "国际市场",
        "description": "浏览国际市场与海外相关动态。",
        "section_keys": ["international_market"],
    },
    {
        "key": "reading_note",
        "title": "阅读说明",
        "description": "用于理解当前版本的阅读边界、口径与说明。",
        "section_keys": ["report_note"],
    },
]

FRONTEND_SECTION_DISPLAY = {
    "report_note": {
        "category_key": "reading_note",
        "category_title": "阅读说明",
        "section_title": "阅读说明",
        "view_label": "",
        "nav_title": "阅读说明",
    },
    "brand_alert": {
        "category_key": "our_focus",
        "category_title": "我方与重点对象",
        "section_title": "我方与重点对象",
        "view_label": "我方视角",
        "nav_title": "我方与重点对象",
    },
    "focus_targets": {
        "category_key": "our_focus",
        "category_title": "我方与重点对象",
        "section_title": "我方与重点对象",
        "view_label": "重点对象视角",
        "nav_title": "我方与重点对象",
    },
    "own_track": {
        "category_key": "core_business",
        "category_title": "核心业务与产区",
        "section_title": "核心业务与产区",
        "view_label": "",
        "nav_title": "核心业务与产区",
    },
    "themed_tracks": {
        "category_key": "theme_track",
        "category_title": "主题赛道",
        "section_title": "主题赛道",
        "view_label": "",
        "nav_title": "主题赛道",
    },
    "reference_brands": {
        "category_key": "reference_samples",
        "category_title": "参考品牌与方法样本",
        "section_title": "参考品牌与方法样本",
        "view_label": "",
        "nav_title": "参考品牌与方法样本",
    },
    "consumption_trends": {
        "category_key": "market_trends",
        "category_title": "市场与消费趋势",
        "section_title": "市场与消费趋势",
        "view_label": "",
        "nav_title": "市场与消费趋势",
    },
    "policy_env": {
        "category_key": "policy_environment",
        "category_title": "政策与产业环境",
        "section_title": "政策与产业环境",
        "view_label": "",
        "nav_title": "政策与产业环境",
    },
    "international_market": {
        "category_key": "international_market_reading",
        "category_title": "国际市场",
        "section_title": "国际市场",
        "view_label": "",
        "nav_title": "国际市场",
    },
    "douyin_monitoring": {
        "category_key": "hidden",
        "category_title": "抖音监测",
        "section_title": "抖音监测",
        "view_label": "",
        "nav_title": "抖音监测",
    },
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
    "own_track": [
        {"title": "A. 海南 / 儋州本地主赛道", "keywords": ["海南", "儋州", "洋浦"]},
        {"title": "B. 电白 / 茂名 / 观珠主产区", "keywords": ["电白", "茂名", "观珠"]},
        {"title": "C. 价格与交易", "keywords": ["价格", "交易", "成交", "报价"]},
        {"title": "D. 协会 / 展会 / 标准 / 溯源", "keywords": ["协会", "展会", "标准", "溯源"]},
        {"title": "E. 产业链延伸与融合赛道", "keywords": ["产业链", "延伸", "融合", "跨界"]},
    ],
    "themed_tracks": [
        {"title": "A. 香氛涂料", "keywords": ["香氛涂料", "涂料"]},
        {"title": "B. 空间香 / 家居香氛", "keywords": ["空间香", "家居香氛", "空间香氛", "家居"]},
        {"title": "C. 情绪香氛", "keywords": ["情绪香氛", "情绪"]},
        {"title": "D. 沉香 + 空间 / 沉香 + 日用", "keywords": ["沉香+空间", "沉香 + 空间", "沉香+日用", "沉香 + 日用", "日用"]},
    ],
    "reference_brands": [
        {"title": "A. 观夏", "keywords": ["观夏"]},
        {"title": "B. 闻献", "keywords": ["闻献"]},
        {"title": "C. 其他参考品牌", "keywords": ["品牌", "参考品牌", "竞品"]},
        {"title": "D. 空间 / 内容 / 文案 / 活动样本", "keywords": ["空间", "内容", "文案", "活动", "样本"]},
    ],
}
