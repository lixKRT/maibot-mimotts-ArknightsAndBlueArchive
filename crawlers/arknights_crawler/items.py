"""数据项定义。"""

from dataclasses import dataclass


@dataclass
class VoiceItem:
    """语音数据项。"""

    operator_name: str = ""
    operator_id: str = ""
    title: str = ""
    filename: str = ""
    number: str = ""
    index: str = ""
    cond: str = ""
    language: str = "cn"
    url: str = ""
    save_path: str = ""


@dataclass
class OperatorInfoItem:
    """干员信息数据项。"""

    operator_name: str = ""

    # 基础档案
    code_name: str = ""
    gender: str = ""
    combat_experience: str = ""
    birth_place: str = ""
    birthday: str = ""
    race: str = ""
    height: str = ""
    infection_status: str = ""

    # 六维属性
    physical_strength: str = ""
    battlefield_mobility: str = ""
    physiological_tolerance: str = ""
    tactical_planning: str = ""
    combat_technique: str = ""
    originium_arts_adaptability: str = ""

    # 医疗数据
    cell_originium_assimilation: str = ""
    blood_originium_crystal_density: str = ""

    # 档案资料
    objective_resume: str = ""
    clinical_analysis: str = ""
    profile_1: str = ""
    profile_2: str = ""
    profile_3: str = ""
    profile_4: str = ""

    save_path: str = ""

    def to_text(self) -> str:
        """将干员信息格式化为可读文本。"""
        sections = []

        # 基础档案
        basic_info = [
            ("代号", self.code_name),
            ("性别", self.gender),
            ("战斗经验", self.combat_experience),
            ("出身地", self.birth_place),
            ("生日", self.birthday),
            ("种族", self.race),
            ("身高", self.height),
            ("矿石病感染情况", self.infection_status),
        ]
        lines = [f"{k}：{v}" for k, v in basic_info if v]
        if lines:
            sections.append("【基础档案】\n" + "\n".join(lines))

        # 六维属性
        six_dim = [
            ("物理强度", self.physical_strength),
            ("战场机动", self.battlefield_mobility),
            ("生理耐受", self.physiological_tolerance),
            ("战术规划", self.tactical_planning),
            ("战斗技巧", self.combat_technique),
            ("源石技艺适应性", self.originium_arts_adaptability),
        ]
        lines = [f"{k}：{v}" for k, v in six_dim if v]
        if lines:
            sections.append("【六维属性】\n" + "\n".join(lines))

        # 医疗数据
        medical = [
            ("体细胞与源石融合率", self.cell_originium_assimilation),
            ("血液源石结晶密度", self.blood_originium_crystal_density),
        ]
        lines = [f"{k}：{v}" for k, v in medical if v]
        if lines:
            sections.append("【医疗数据】\n" + "\n".join(lines))

        # 档案资料
        profiles = [
            ("客观履历", self.objective_resume),
            ("临床诊断分析", self.clinical_analysis),
            ("档案资料一", self.profile_1),
            ("档案资料二", self.profile_2),
            ("档案资料三", self.profile_3),
            ("档案资料四", self.profile_4),
        ]
        for label, content in profiles:
            if content:
                sections.append(f"【{label}】\n{content}")

        return "\n\n".join(sections)


@dataclass
class IllustrationItem:
    """立绘数据项。"""

    operator_name: str = ""
    stage: str = ""
    filename: str = ""
    url: str = ""
    save_path: str = ""
