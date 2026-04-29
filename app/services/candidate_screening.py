from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.common import CandidateTagHit, SentenceSegment
from app.services.fuzzy_matching import find_fuzzy_match


@dataclass(frozen=True, slots=True)
class TagPattern:
    keywords: tuple[str, ...]
    regex_patterns: tuple[str, ...]


DEFAULT_TAG_PATTERNS: dict[str, TagPattern] = {
    "absolute_guarantee": TagPattern(
        keywords=("保证", "确保", "绝对", "100%", "唯一", "顶级"),
        regex_patterns=(r"百分之百", r"包过", r"包成功"),
    ),
    "medical_claim": TagPattern(
        keywords=("根治", "治愈", "药到病除", "逆转病情", "消炎止痛", "疗效", "功效", "降糖", "降压"),
        regex_patterns=(r"\d+天治好", r"包治", r"瘦\d+斤", r"永不复发"),
    ),
    "financial_promise": TagPattern(
        keywords=("稳赚", "暴富", "保本", "翻倍收益", "回本", "高收益", "短期收益", "保证收益", "带单"),
        regex_patterns=(r"\d+天回本", r"零风险", r"收益翻倍", r"稳赚不赔", r"保本保息"),
    ),
    "traffic_inducement": TagPattern(
        keywords=(
            "私信",
            "加微信",
            "微信号",
            "vx",
            "v信",
            "QQ",
            "扫码",
            "二维码",
            "领取",
            "进群",
            "小窗联系",
            "站外",
            "外链",
            "私域",
            "留联系方式",
            "私下交易",
        ),
        regex_patterns=(r"评论区.*领取", r"私信.*资料", r"(微信|vx|v信|二维码).*下单", r"私下交易|站外交易"),
    ),
    "scarcity_urgency": TagPattern(
        keywords=("限时", "最后一天", "仅剩", "马上抢", "错过不再"),
        regex_patterns=(r"最后\d+个名额", r"\d+分钟内"),
    ),
    "sexual_content": TagPattern(
        keywords=("色情", "淫秽", "招嫖", "性服务", "走光", "抖胸", "两性技巧", "低俗擦边", "裸体"),
        regex_patterns=(r"乳头|乳晕|生殖器", r"性暗示", r"敏感部位", r"私密部位|隐私部位"),
    ),
    "illegal_activity": TagPattern(
        keywords=("高收入兼职", "征信修复", "赌博", "博彩", "传销", "诈骗", "假证", "管制刀具", "枪支", "外挂", "跑分"),
        regex_patterns=(r"兼职.*日结", r"征信修复|洗白征信", r"赌博|博彩|彩票群", r"棋牌.*房卡", r"洗钱|跑分"),
    ),
    "disturbing_content": TagPattern(
        keywords=("血腥", "遗体", "自杀", "排泄物", "鬼脸", "蜈蚣", "暴力", "恐怖", "手术特写"),
        regex_patterns=(r"断肢|器官|巨人观", r"自残|轻生|不想活了", r"密集.*蜘蛛|密集.*蜈蚣", r"虐杀|恐怖吓人"),
    ),
    "marketing_violation": TagPattern(
        keywords=("合作推广", "全网最低", "0元抢", "地板价", "第三方交易", "热点营销", "拉踩", "恶意举报"),
        regex_patterns=(
            r"全网第?一|全网最低",
            r"0元抢|免费领",
            r"原价\d+现价\d+",
            r"拉踩.*竞品|诋毁.*品牌",
            r"恶意举报|虚假投诉",
        ),
    ),
    "minor_protection": TagPattern(
        keywords=("未成年人", "校园霸凌", "童工", "抽烟", "喝酒", "辍学"),
        regex_patterns=(r"未成年.*(抽烟|喝酒|性行为)", r"校园霸凌|欺凌同学", r"童工|童模"),
    ),
    "public_ethics": TagPattern(
        keywords=("炫富", "卖惨", "婚闹", "地域歧视", "辱骂", "一夜情", "出轨", "婚外恋", "封建迷信"),
        regex_patterns=(r"种族歧视|地域歧视|性别歧视", r"恶俗婚闹|拜金", r"乱伦|一夜情|情感操控", r"童养媳|封建迷信"),
    ),
    "unsafe_behavior": TagPattern(
        keywords=("飙车", "闯红灯", "烧胎", "跳楼", "割腕", "玩火"),
        regex_patterns=(r"双手离把|超速|闯红灯", r"割腕|服毒|自残", r"高空.*摆拍|冰面.*游泳"),
    ),
    "interaction_manipulation": TagPattern(
        keywords=("扣1", "评论666", "互粉互赞", "点赞关注", "许愿", "不转"),
        regex_patterns=(r"评论区.*扣1", r"不转.*(倒霉|不是中国人)", r"互粉|互赞|有求必应"),
    ),
    "originality_violation": TagPattern(
        keywords=("搬运", "抄袭", "转载", "洗稿", "站外素材", "去水印"),
        regex_patterns=(r"未经授权.*(搬运|转载)", r"多账号.*重复发布", r"去水印|二次剪辑"),
    ),
    "rights_infringement": TagPattern(
        keywords=("身份证", "手机号", "家庭住址", "聊天记录", "AI换脸", "冒充企业", "网暴", "肖像权", "姓名权", "隐私权"),
        regex_patterns=(r"身份证号|手机号|家庭住址", r"AI合成|换脸|肖像", r"冒充.*(企业|员工|公章)", r"人肉|泄露.*隐私"),
    ),
    "persona_fabrication": TagPattern(
        keywords=("虚假人设", "逆袭故事", "编造经历", "名校毕业", "年入百万", "宝妈创业"),
        regex_patterns=(r"(月入|年入)\d+(万|w|百万)", r"前(大厂|投行|名企).*创业", r"编造.*(学历|职业|经历)"),
    ),
    "ai_generated_content": TagPattern(
        keywords=("AI生成", "AIGC", "深度合成", "AI换脸", "数字人", "AI配音"),
        regex_patterns=(r"AI(生成|合成|换脸)", r"深度合成", r"数字人.*口播"),
    ),
    "clickbait_content": TagPattern(
        keywords=("震惊", "一定要看完", "最后一条", "99%的人不知道", "封面即真相", "看完沉默"),
        regex_patterns=(r"\d+%的人都不知道", r"一定要看完", r"最后一条.*颠覆认知"),
    ),
    "commercial_disclosure": TagPattern(
        keywords=("合作", "商单", "广告", "赞助", "品牌合作", "报备"),
        regex_patterns=(r"(品牌|店铺).*合作", r"商务合作|商单", r"广告.*未标识"),
    ),
    "false_review": TagPattern(
        keywords=("无广", "亲测有效", "自用推荐", "真实测评", "回购十次", "素人种草"),
        regex_patterns=(r"(无广|自用).*推荐", r"亲测.*有效", r"素人.*种草|真实测评"),
    ),
    "medical_content": TagPattern(
        keywords=("诊疗建议", "推荐药物", "针灸", "刮痧", "胃炎", "痛风", "高血压"),
        regex_patterns=(r"永不复发|一定有效", r"推荐.*(药物|手术)", r"养生|食疗.*治"),
    ),
    "duplicate_content": TagPattern(
        keywords=("在线等", "属鸡的人有福了", "雷同文案", "模板文案", "集体发布"),
        regex_patterns=(r"怎么办.*在线等", r"属(鸡|狗|猴|马)的人有福了", r"同款文案|批量发布"),
    ),
    "content_quality_issue": TagPattern(
        keywords=("黑边", "花屏", "卡顿", "口型", "字幕遮挡", "画质模糊", "音画不同步", "低质"),
        regex_patterns=(r"花屏|卡顿|黑边", r"口型.*不(同步|一致)|音画不同步", r"字幕.*(遮挡|错误)"),
    ),
    "mid_long_video_marketing": TagPattern(
        keywords=("营销素材", "打断剧情", "生硬口播", "超过40秒", "植入次数"),
        regex_patterns=(r"连续超过10秒", r"超过20秒|超过40秒", r"植入次数.*大于3次"),
    ),
    "copyright_violation": TagPattern(
        keywords=("版权", "盗录", "拍屏", "拆条", "未授权", "合作片单"),
        regex_patterns=(r"拍屏|盗摄|盗录", r"未经授权.*(音乐|影视|字体|图片)", r"拆条|搬运"),
    ),
    "short_drama_promotion": TagPattern(
        keywords=("短剧锚点", "免费看全集", "第三方平台", "盗版短剧", "虚假续集", "迷信"),
        regex_patterns=(r"免费看.*全集", r"引导.*第三方.*观看", r"未挂载.*短剧锚点"),
    ),
    "live_stream_related": TagPattern(
        keywords=("PK惩罚", "黑暗料理", "刷礼物", "返利", "陪聊", "低俗擦边"),
        regex_patterns=(r"刷礼物|打赏", r"PK.*惩罚", r"私下交易|返现"),
    ),
}


class CandidateScreeningService:
    def __init__(self, tag_patterns: dict[str, TagPattern] | None = None) -> None:
        self.tag_patterns = tag_patterns or DEFAULT_TAG_PATTERNS

    def screen(self, sentences: list[SentenceSegment]) -> list[CandidateTagHit]:
        hits: list[CandidateTagHit] = []
        seen: set[tuple[str, str, int]] = set()

        for sentence in sentences:
            text_lower = sentence.text.lower()
            for tag, pattern in self.tag_patterns.items():
                for keyword in pattern.keywords:
                    keyword_match = re.search(re.escape(keyword), sentence.text, flags=re.IGNORECASE)
                    if keyword_match and keyword.lower() in text_lower:
                        key = (tag, keyword, sentence.sentence_id)
                        if key not in seen:
                            hits.append(
                                CandidateTagHit(
                                    tag=tag,
                                    trigger_type="keyword",
                                    trigger_value=keyword,
                                    sentence_id=sentence.sentence_id,
                                    sentence=sentence.text,
                                    matched_text=keyword_match.group(0),
                                    match_start=keyword_match.start(),
                                    match_end=keyword_match.end(),
                                )
                            )
                            seen.add(key)
                        continue

                    fuzzy_match = find_fuzzy_match(sentence.text, keyword)
                    if fuzzy_match:
                        key = (tag, keyword, sentence.sentence_id)
                        if key not in seen:
                            hits.append(
                                CandidateTagHit(
                                    tag=tag,
                                    trigger_type="fuzzy_keyword",
                                    trigger_value=keyword,
                                    sentence_id=sentence.sentence_id,
                                    sentence=sentence.text,
                                    matched_text=fuzzy_match.matched_text,
                                    match_start=fuzzy_match.start,
                                    match_end=fuzzy_match.end,
                                )
                            )
                            seen.add(key)
                for regex in pattern.regex_patterns:
                    regex_match = re.search(regex, sentence.text, flags=re.IGNORECASE)
                    if regex_match:
                        key = (tag, regex, sentence.sentence_id)
                        if key not in seen:
                            hits.append(
                                CandidateTagHit(
                                    tag=tag,
                                    trigger_type="regex",
                                    trigger_value=regex,
                                    sentence_id=sentence.sentence_id,
                                    sentence=sentence.text,
                                    matched_text=regex_match.group(0),
                                    match_start=regex_match.start(),
                                    match_end=regex_match.end(),
                                )
                            )
                            seen.add(key)
        return hits
