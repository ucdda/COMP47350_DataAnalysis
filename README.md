# COMP47350 Group Project README

## 1. 项目目标

使用 RPPR（Residential Property Price Register）数据，构建一个用于**房价预测**的数据分析与建模流程。  
目标变量：`Price (€)`。

## 2. 提交要求（打包为一个 zip）

压缩包命名格式：
`Student1-Name_ID12345678-Student2-Name_ID-Student3-Name_Id-COMP47350_GroupProject.zip`

zip 中应包含：
1. 小组数据文件（`.csv`）
2. 分析 notebook（`.ipynb`）
3. `DQR.pdf`（Data Quality Report，正文最多 5 页，附录不限）
4. `DQP.pdf`（Data Quality Plan，正文最多 5 页，附录不限）
5. `requirements.txt`
6. `Individual Contribution Statement.pdf`（最多 2 页，含分工比例表、任务日志、签名声明）

截止日期：**Monday, 30 March, 2026**。

## 3. 作业结构与评分权重

1. **Data Quality Report (DQR)** - `25%`
2. **Data Quality Plan (DQP)** - `15%`
3. **Feature Pair Relationships** - `15%`
4. **New Feature Engineering** - `15%`
5. **Model Training & Evaluation** - `30%`

## 4. 五部分任务要求（整理版）

### Part 1: DQR（训练集数据质量报告）

1. 只使用训练集做数据理解与初步清洗（测试集先保留）
2. 基础检查：行列数、样例、数据类型
3. 检查并处理：重复行/列、常量列
4. 输出清洗后训练集 CSV（命名清晰）
5. 为所有特征生成统计表和可视化
6. 在 `DQR.pdf` 总结关键质量问题与可选处理策略

### Part 2: DQP（数据质量处理计划）

1. 列出每个特征的数据质量问题
2. 给出候选方案并说明最终方案选择理由
3. 应用方案得到“最终清洗版”训练集
4. 明确每个特征最终数据类型（连续/类别等）
5. 该步骤后不应再有 `NaN`
6. 输出 `DQP.pdf` 与最终清洗 CSV

### Part 3: 特征两两关系探索

1. 选择有潜力的特征子集做交互分析（如相关图、散点图、分类-连续图）
2. 解释为什么选择这些特征组合
3. 说明哪些特征（或组合）对目标预测有帮助
4. 用简短文字总结“目前发现的规律”

### Part 4: 新特征构造

1. 至少构造 **3 个**工程特征（转换、组合、外部数据等）
2. 避免数据泄漏，保证对测试数据可泛化
3. 说明设计动机与领域知识依据
4. 用代码验证新特征确实提升预测价值
5. 输出包含新特征的数据集 CSV

### Part 5: 模型训练与评估

1. 对测试集执行与训练集一致的清洗和特征工程
2. 使用清洗后的训练集训练预测模型（目标：`Price (€)`）
3. 讨论模型可解释性
4. 至少给出 **3 个评估指标**
5. 比较训练集、hold-out 测试集、交叉验证结果
6. 识别过拟合/欠拟合，并提出改进方案并用代码验证

## 5. 当前项目文件（本仓库）

### 数据文件
- `ppr-group-25208508-train-utf8.csv`（54,000 行，9 列）
- `ppr-group-25208508-test.csv`（10,000 行，9 列）
- `ppr-group-25208508-train-with-features.csv`（54,000 行，11 列）

### 主要字段（原始训练集）
- `Date of Sale (dd/mm/yyyy)`
- `Address`
- `County`
- `Eircode`
- `Price (€)`（目标变量）
- `Not Full Market Price`
- `VAT Exclusive`
- `Description of Property`
- `Property Size Description`

### 已有 notebook / 资料
- `2025-Spring-GroupProject-Notebook.ipynb`（课程项目要求）
- `Lab3-Notebook-DataUnderstanding-DataQualityReport-MotorInsuranceData.ipynb`
- `Lab4-Notebook-DataUnderstanding-DataQualityPlan-MotorInsuranceData.ipynb`
- `Price-Distribution-Analysis.png`

## 6. 推荐执行清单（可直接打勾）

- [ ] 完成训练集初步清洗并导出 cleaned CSV  
- [ ] 完成 DQR 表格、可视化和 `DQR.pdf`  
- [ ] 完成 DQP（逐特征问题 + 方案 + 理由）并导出 final clean CSV  
- [ ] 完成特征关系探索与结论  
- [ ] 构造至少 3 个工程特征并验证有效性  
- [ ] 完成模型训练、测试集评估、交叉验证和对比分析  
- [ ] 整理 `requirements.txt`  
- [ ] 完成个人贡献声明 PDF（分工比例 + 任务日志 + 签名）  
- [ ] 打包 zip 并按命名规范提交

## 7. 备注

1. notebook 需做到“代码 + 解释”清晰可读，变量命名自解释。  
2. 报告（DQR/DQP）建议正文写结论，图表放附录。  
3. 评分更关注分析质量与决策理由，不是篇幅长度。
