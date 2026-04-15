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
