# 1-品牌球馆冠名合作协议：TP/FP/TN/FN 逐条对照（third_party + policy_a）

## 对照口径

- 数据来源：metrics/outputs/eval_runs/20260316_single_brand_global_shot/evaluation_result.json
- 合同：1-品牌球馆冠名合作协议
- Participant：third_party
- Policy：policy_a（accept + partial 为正例）
- 判定规则：
  - label=1 且 pred=1 => TP
  - label=1 且 pred=0 => FN
  - label=0 且 pred=1 => FP
  - label=0 且 pred=0 => TN

## 汇总

- TP: 11
- FP: 6
- TN: 31
- FN: 0
- 总条款数: 48

- Accuracy = (TP+TN)/Total = 0.8750
- MissRate = FN/(TP+FN) = 0.0000
- FalsePositiveRate = FP/(FP+TN) = 0.1622

## 逐条明细（含实际条款文本）

### 01. 1-品牌球馆冠名合作协议_c001 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> 乙方（合作方/球馆方）：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_（以下简称“乙方”）

### 02. 1-品牌球馆冠名合作协议_c002 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 统一社会信用代码/身份证号：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 03. 1-品牌球馆冠名合作协议_c003 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 球馆地址：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 04. 1-品牌球馆冠名合作协议_c004 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 联系方式：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 05. 1-品牌球馆冠名合作协议_c005 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 鉴于甲方拥有“”品牌及相关产品资源，乙方拥有专业球馆运营资源，双方本着平等互利、友好协商的原则，就甲方对乙方球馆进行独家冠名及物资赞助事宜，达成如下协议，以资共同遵守。

### 06. 1-品牌球馆冠名合作协议_c006 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **一、合作核心内容**

### 07. 1-品牌球馆冠名合作协议_c007 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 双方确立球馆独家冠名合作关系，乙方球馆官方正式名称冠名为“XX球馆”（“XX”为乙方原有球馆核心标识，可保留）。

### 08. 1-品牌球馆冠名合作协议_c008 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 甲方按本协议约定向乙方提供指定物资赞助，乙方按本协议约定向甲方提供品牌冠名及专属曝光权益。

### 09. 1-品牌球馆冠名合作协议_c009 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 3. 合作期限：自2026年1月20日起至2028年1月20日止，共计2年。合作期限届满前30日，双方可协商续约事宜，同等条件下甲方享有优先续约权。

### 10. 1-品牌球馆冠名合作协议_c010 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **二、甲方赞助物资清单（赛事级标准，全额无偿赞助）**

### 11. 1-品牌球馆冠名合作协议_c011 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 6. 交付要求：甲方需在本协议签订后15个工作日内，将上述所有赞助物资足额交付至乙方球馆指定地点，运输费用由甲方承担。

### 12. 1-品牌球馆冠名合作协议_c012 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **三、乙方核心权益保障（独家品牌曝光，无竞品冲突）**

### 13. 1-品牌球馆冠名合作协议_c013 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 合作期内，乙方球馆所有官方对外标识均需醒目展示“XX球馆”全称及甲方品牌logo，字体规格不小于球馆原有标识字号，logo尺寸不小于30cm×30cm（具体位置、规格双方签字确认后落地）。

### 14. 1-品牌球馆冠名合作协议_c014 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 乙方对外宣传推广（包括但不限于大众点评、美团、微信公众号、视频号、抖音、线下海报、宣传单页、客户沟通话术等）需统一使用“XX球馆”冠名名称，不得擅自变更、删减或遮挡甲方品牌信息。

### 15. 1-品牌球馆冠名合作协议_c015 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **（二）场地品牌曝光权益**

### 16. 1-品牌球馆冠名合作协议_c016 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 乙方需在球馆所有匹克球场地的非截击区地面，统一喷涂甲方“”品牌logo（具体位置、尺寸、颜色由甲方提供规范文件，双方确认后执行）。乙方负责保障logo清晰完整，无遮挡、无磨损，若因正常使用出现磨损，需重新喷涂。

### 17. 1-品牌球馆冠名合作协议_c017 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 乙方需在球馆核心位置（包括但不限于场地主入口、观众观赛区、客户休息区）为甲方提供3个专属广告位。

### 18. 1-品牌球馆冠名合作协议_c018 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 甲方负责提供广告画面设计稿，乙方负责免费完成广告画面的安装、更换。

### 19. 1-品牌球馆冠名合作协议_c019 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **（三）无竞品承诺**

### 20. 1-品牌球馆冠名合作协议_c020 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 合作期内，乙方球馆所有区域（尤其是匹克球场地、产品陈列区、广告展示区）不得出现甲方同品类（匹克球相关器材、装备）竞品的品牌logo、广告宣传、物资投放等信息，确保甲方品牌独家曝光权益。

### 21. 1-品牌球馆冠名合作协议_c021 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **四、双方责任与义务**

### 22. 1-品牌球馆冠名合作协议_c022 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **（一）甲方责任与义务**

### 23. 1-品牌球馆冠名合作协议_c023 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 按本协议约定的时间、规格、数量向乙方交付赞助物资，确保物资为全新、合格的正品，符合赛事级使用要求，并提供相关质量合格证明。

### 24. 1-品牌球馆冠名合作协议_c024 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 及时向乙方提供品牌logo、广告设计规范、冠名名称使用规范等相关文件，配合乙方完成冠名及品牌曝光的落地工作。

### 25. 1-品牌球馆冠名合作协议_c025 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 3. 合作期内，甲方可优先使用冠名球馆举办品牌赛事、产品试打、客户沙龙等活动，乙方需提供场地协调、基础配套（如灯光、座椅）等便利支持，活动具体事宜双方另行协商。

### 26. 1-品牌球馆冠名合作协议_c026 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 4. 甲方不得要求乙方从事违反法律法规、公序良俗的宣传推广活动。

### 27. 1-品牌球馆冠名合作协议_c027 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **（二）乙方责任与义务**

### 28. 1-品牌球馆冠名合作协议_c028 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> 1. 本协议签订后15个工作日内，完成球馆冠名更名、门头标识更换、logo地面喷涂、广告位安装、品牌展架摆放等所有品牌曝光权益的落地工作，并拍摄清晰的现场照片（不少于10张，含整体场景及细节特写）、视频（时长不少于1分钟）提交甲方验收，验收合格后方视为完成落地。

### 29. 1-品牌球馆冠名合作协议_c029 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 2. 合作期内，妥善保管甲方赞助的物资，除正常使用损耗外，因乙方人为原因导致物资损坏、丢失的，需及时通知甲方并负责维修或按原价赔偿。

### 30. 1-品牌球馆冠名合作协议_c030 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 3. 定期检查甲方品牌曝光资源（冠名标识、logo、广告位、展架等）的完整性，发现问题及时整改，确保品牌形象不受影响。

### 31. 1-品牌球馆冠名合作协议_c031 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> 4. 主动向球馆客户介绍、推荐品牌及产品，配合甲方的品牌推广需求，不得故意诋毁或误导客户。

### 32. 1-品牌球馆冠名合作协议_c032 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 5. 若球馆需进行装修、改造或调整布局，涉及甲方品牌曝光资源的，需提前7个工作日书面通知甲方，经甲方同意后方可实施，且需保障调整后甲方品牌曝光权益不降低。

### 33. 1-品牌球馆冠名合作协议_c033 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> 1. 若甲方未按本协议约定时间交付赞助物资，逾期超过30日的，乙方有权解除本协议。

### 34. 1-品牌球馆冠名合作协议_c034 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 若甲方交付的赞助物资存在质量问题，不符合赛事级标准，甲方需在7个工作日内更换合格物资，逾期未更换的，乙方有权要求甲方赔偿损失。

### 35. 1-品牌球馆冠名合作协议_c035 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 3. 若乙方未按本协议约定完成冠名、logo喷涂、广告位提供等品牌曝光权益落地，或未通过验收且逾期未整改，甲方有权要求乙方限期整改，整改无效的，甲方有权解除本协议，并赔偿甲方因此造成的全部损失（包括但不限于物资成本、品牌推广损失等）。

### 36. 1-品牌球馆冠名合作协议_c036 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 4. 若乙方违反无竞品承诺，在球馆内引入甲方同品类竞品品牌信息，甲方有权要求乙方立即拆除相关信息；情节严重的，甲方有权解除本协议，乙方需赔偿甲方全部损失。

### 37. 1-品牌球馆冠名合作协议_c037 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> 5. 若乙方擅自变更、删减冠名名称或遮挡、拆除甲方品牌曝光资源，甲方有权要求乙方限期恢复；逾期未恢复的，甲方有权解除本协议，乙方需赔偿甲方损失。

### 38. 1-品牌球馆冠名合作协议_c038 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **六、协议的解除与终止**

### 39. 1-品牌球馆冠名合作协议_c039 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 双方协商一致，可书面解除本协议。

### 40. 1-品牌球馆冠名合作协议_c040 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 2. 一方严重违反本协议约定，经另一方催告后仍未整改的，另一方有权解除本协议。

### 41. 1-品牌球馆冠名合作协议_c041 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 3. 合作期限届满，本协议自动终止；若双方协商续约，需另行签订书面协议。

### 42. 1-品牌球馆冠名合作协议_c042 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 4. 协议解除或终止后，乙方需停止使用“”冠名名称及品牌相关标识，若甲方同意乙方继续使用赞助物资，物资所有权归乙方所有；若甲方要求收回物资，乙方需配合返还（正常使用损耗除外）。

### 43. 1-品牌球馆冠名合作协议_c043 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 本协议履行过程中发生的任何争议，双方应首先友好协商解决；协商不成的，任何一方均有权向乙方球馆所在地人民法院提起诉讼。

### 44. 1-品牌球馆冠名合作协议_c044 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 1. 本协议未尽事宜，双方可另行签订补充协议，补充协议与本协议具有同等法律效力。

### 45. 1-品牌球馆冠名合作协议_c045 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> 2. 本协议所有附件（包括但不限于落地验收清单、品牌规范文件、物资清单等）均为本协议不可分割的组成部分，与本协议具有同等法律效力。

### 46. 1-品牌球馆冠名合作协议_c046 -> TP

- label_positive: 1
- predicted_positive: 1
- clause_text:

> 3. 本协议一式两份，甲乙双方各执一份，自双方签字盖章之日起生效，具有同等法律效力。

### 47. 1-品牌球馆冠名合作协议_c047 -> TN

- label_positive: 0
- predicted_positive: 0
- clause_text:

> **甲方（盖章/签字）：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_**

### 48. 1-品牌球馆冠名合作协议_c048 -> FP

- label_positive: 0
- predicted_positive: 1
- clause_text:

> **乙方（盖章/签字）：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_**

## 按分类快速索引

- TP (11): 1-品牌球馆冠名合作协议_c002、1-品牌球馆冠名合作协议_c009、1-品牌球馆冠名合作协议_c020、1-品牌球馆冠名合作协议_c025、1-品牌球馆冠名合作协议_c029、1-品牌球馆冠名合作协议_c035、1-品牌球馆冠名合作协议_c036、1-品牌球馆冠名合作协议_c040、1-品牌球馆冠名合作协议_c042、1-品牌球馆冠名合作协议_c043、1-品牌球馆冠名合作协议_c046
- FP (6): 1-品牌球馆冠名合作协议_c001、1-品牌球馆冠名合作协议_c028、1-品牌球馆冠名合作协议_c031、1-品牌球馆冠名合作协议_c033、1-品牌球馆冠名合作协议_c037、1-品牌球馆冠名合作协议_c048
- TN (31): 1-品牌球馆冠名合作协议_c003、1-品牌球馆冠名合作协议_c004、1-品牌球馆冠名合作协议_c005、1-品牌球馆冠名合作协议_c006、1-品牌球馆冠名合作协议_c007、1-品牌球馆冠名合作协议_c008、1-品牌球馆冠名合作协议_c010、1-品牌球馆冠名合作协议_c011、1-品牌球馆冠名合作协议_c012、1-品牌球馆冠名合作协议_c013、1-品牌球馆冠名合作协议_c014、1-品牌球馆冠名合作协议_c015、1-品牌球馆冠名合作协议_c016、1-品牌球馆冠名合作协议_c017、1-品牌球馆冠名合作协议_c018、1-品牌球馆冠名合作协议_c019、1-品牌球馆冠名合作协议_c021、1-品牌球馆冠名合作协议_c022、1-品牌球馆冠名合作协议_c023、1-品牌球馆冠名合作协议_c024、1-品牌球馆冠名合作协议_c026、1-品牌球馆冠名合作协议_c027、1-品牌球馆冠名合作协议_c030、1-品牌球馆冠名合作协议_c032、1-品牌球馆冠名合作协议_c034、1-品牌球馆冠名合作协议_c038、1-品牌球馆冠名合作协议_c039、1-品牌球馆冠名合作协议_c041、1-品牌球馆冠名合作协议_c044、1-品牌球馆冠名合作协议_c045、1-品牌球馆冠名合作协议_c047
- FN (0): 无