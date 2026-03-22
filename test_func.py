    def _extract_keywords_from_dubbing(self, dubbing):
        """从配音文本提取关键词 - 本地模式，不依赖大模型
        
        Returns a string of keywords extracted from the dubbing text
        """
        import re
        
        if not dubbing:
            return ""
        
        keywords = []
        
        # 定义关键词映射表
        keyword_map = {
            # 时间和日期
            '2026': '2026, calendar, date',
            '3月': 'March, spring, calendar',
            '下旬': 'late month, calendar date',
            
            # 地点
            '俄乌': 'Russia Ukraine war, Russian Ukrainian conflict, Eastern Europe battlefield',
            '俄罗斯': 'Russia, Russian, Moscow',
            '乌克兰': 'Ukraine, Ukrainian, Kiev',
            '中东': 'Middle East, MENA region',
            '伊朗': 'Iran, Iranian, Persian',
            '美国': 'United States, America, US',
            '以色列': 'Israel, Israeli',
            '苏丹': 'Sudan, African',
            '缅甸': 'Myanmar, Burma, Southeast Asia',
            
            # 战争和冲突
            '战场': 'battlefield, war zone, combat area',
            '战争': 'war, warfare, conflict',
            '战斗': 'battle, combat, fighting',
            '冲突': 'conflict, clash',
            '军事': 'military, armed forces',
            '士兵': 'soldiers, troops, military personnel',
            '进攻': 'offensive, attack, assault',
            '防御': 'defense, defensive',
            '轰炸': 'bombing, air strike',
            '导弹': 'missile, rocket',
            '武器': 'weapons, arms',
            
            # 描述性词汇
            '最凶': 'most intense, severe, extreme',
            '影响最广': 'widespread impact, global impact',
            '持续燃烧': 'ongoing fire, burning, flames',
            '内战区': 'civil war zone, internal conflict',
            '多线混战': 'multi-front war, multiple battlefields',
            '外溢': 'spillover, spreading, escalation',
            '低调': 'low-key, understated, quiet',
            '摩擦': 'friction, tensions, minor conflicts',
            '全面战场': 'full-scale war, major battlefield',
            '三个方向': 'three directions, three fronts, three areas',
            '特别': 'especially, particularly, notably',
            
            # 新闻相关
            '新闻': 'news, news broadcast, news report',
            '分析': 'analysis, expert analysis',
            '报道': 'report, coverage',
        }
        
        # 遍历映射表，查找匹配的关键词
        for cn, en in keyword_map.items():
            if cn in dubbing:
                keywords.append(en)
        
        # 如果没有匹配，返回配音文本的前几个词的描述
        if not keywords:
            # 提取前20个字符作为描述
            short_text = dubbing[:20]
            return f"scene about {short_text}, documentary style"
        
        return ", ".join(keywords)
