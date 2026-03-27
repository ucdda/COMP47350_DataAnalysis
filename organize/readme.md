# COMP47350 小组项目 — 爱尔兰住宅房产价格预测

## 项目概述

本项目基于爱尔兰**住宅房产价格登记册（RPPR）**数据，构建一个完整的数据分析流水线，用于预测住宅房产价格。预测目标变量为 `Price (€)`——每笔住宅房产交易的申报成交价格。

---

## 文件结构
```
.
├── project.ipynb                        # 主项目 Notebook（包含 Part 1、2、5）
├── DQR.pdf                              # 数据质量报告（Part 1 总结文档）
├── DQP.pdf                              # 数据质量计划（Part 2 总结文档）
├── requirements.txt                     # Python 依赖包列表
├── Individual_Contribution.pdf          # 个人贡献声明（所有成员）
│
├── 数据文件
│   ├── ppr-group-25208508-train.csv     # 原始训练集
│   ├── ppr-group-25208508-test.csv      # 原始测试集
│   ├── geocoded_train.csv               # 经过地理编码流水线处理后的训练集
│   ├── train-cleaned.csv                # DQR 阶段类型转换 + 去重后的中间文件
│   └── train-clean-final.csv            # DQP 最终清洗输出，用于建模
│
├── 地理编码流水线脚本（离线运行，详见 DQP.pdf）
│   ├── step1_geocode.py                 # 正向地理编码（Nominatim + Mapbox）
│   ├── step2_districts.py               # 反向地理编码，提取都柏林行政区号
│   ├── step3_map_preview.py             # 可视化验证（重匹配前）
│   ├── step4_rematch.py                 # 未解析都柏林行的几何兜底规则
│   └── step5_map_preview.py             # 可视化验证（重匹配后）
│
└── DQR 导出表格
    ├── DQR-NumericFeatures.csv
    └── DQR-CategoricalFeatures.csv
```

---

## Notebook 内容说明（`project.ipynb`）

### Part 1 — 数据质量报告 DQR（Cell 0–48）
- 加载原始训练 CSV，检查基本结构
- 数据类型转换（日期、价格、类别字段）
- 检查重复行、常量列、重复列对
- 所有数值与类别特征的描述性统计表
- 可视化分析：缺失值图、类别分布、价格分布（原始 + log）、按地区价格分布、时间趋势
- VAT 一致性检查
- 导出 DQR 汇总表格至 CSV
- 关键发现总结

### Part 2 — 数据质量计划 DQP（Cell 49–85）
- 加载经地理编码处理的训练集（`geocoded_train.csv`）
- 基线检查
- 在删除 Address 列之前先去重
- 从 Address 提取 `is_apartment` 特征
- 删除地理编码辅助列和原始 Address 列
- 基础标准化（空格清理、日期解析、价格转换、时间特征派生）
- 构建 `location` 特征（都柏林区号 或 County）
- 核心字段有效性验证
- VAT 价格调整（新建房产 ×1.135）
- 价格截断（5%–95% 分位数）
- 价格 log 变换 → `Price_Log`（目标变量）
- 删除高缺失率列（Eircode、Property Size Description、Date of Sale）
- 填充剩余缺失值
- 清洗后验证，导出 `train-clean-final.csv`

### Part 5 — 建模与评估（Cell 86–105）
- 加载 `train-clean-final.csv`
- 定义特征（数值 + 类别）和目标变量（`Price_Log`）
- 对类别特征进行 One-Hot 编码
- 训练集/验证集划分（80/20）
- 训练线性回归基线模型
- 评估指标：R²、RMSE、MAE（训练集、验证集、交叉验证）
- 对外部测试集（`test_data.csv`）应用同等清洗流程并评估
- 模型解释：系数分析，识别价格驱动因素

---

## DQR.pdf 应包含的内容

DQR PDF 是 Part 1 的**精简总结报告**（正文最多 5 页 + 附录），**不包含任何 Python 代码**。建议结构如下：

1. **引言**：数据集来源、目标变量、规模（54,000 行 × 9 列）
2. **缺失值问题**：`Property Size Description`（94.75%）、`Eircode`（68.72%）——成因与影响
3. **数据类型问题**：所有列原始加载为字符串，需要类型转换
4. **重复记录**：发现并删除 9 条重复行
5. **价格分布**：严重右偏，最小值 €5,250，最大值 €2.25 亿（批量交易）；建议 log 变换
6. **类别特征分布**：County 分布不均衡（Dublin 占 30.7%）、房产类型分布、VAT 与市场价标记的不均衡性
7. **地区价格差异**：明显地理价格梯度——都柏林及通勤圈显著高于农村地区
8. **时间趋势**：2016–2024 年价格持续上涨；存在轻微季节性波动
9. **VAT 一致性问题**：151 条 `VAT Exclusive = No` 但 `New Dwelling` 的逻辑矛盾记录
10. **附录**：所有汇总表格和图表

---

## DQP.pdf 应包含的内容

DQP PDF 是 Part 2 的**逐特征清洗方案文档**（正文最多 5 页 + 附录）。建议结构如下：

1. **引言**：引用 DQR 发现，概述清洗决策整体思路
2. **Address → `location` 特征**：地理编码方法概述（Nominatim + Mapbox，五步流水线），详细实现见脚本
3. **逐特征清洗表格**：对每个特征记录：
   - 数据类型决策
   - 识别到的问题
   - 选定策略及理由
   - 考虑过的备选方案
4. **价格处理流水线**：VAT 调整 → 截断 → log 变换，每步的理由说明
5. **删除的列**：`Eircode`、`Property Size Description`、`Address`、`Date of Sale`——删除原因
6. **最终特征集**：`train-clean-final.csv` 中所有特征的名称、类型和用途
7. **防止数据泄露**：截断边界、编码器、VAT 税率均仅在训练集上拟合
8. **附录**：清洗日志表、清洗前后数据形状对比

---

## 各部分完成状态

| Part | 状态 | 待办事项 |
|---|---|---|
| Part 1 (DQR) | ✅ Notebook 已完成 | 整理分析结果，撰写并导出 DQR.pdf |
| Part 2 (DQP) | ✅ Notebook 已完成 | 整理清洗方案，撰写并导出 DQP.pdf |
| Part 3（特征对关系） | 🔶 分析已完成，待整理 | 将现有分析整理进 Notebook，补充文字讨论 |
| Part 4（特征工程） | 🔶 特征已创建，待整理 | 将已创建的特征（`location`、`is_apartment` 等）整理进独立的 Part 4 章节，补充至少 3 个新特征的有效性验证 |
| Part 5（建模） | 🔶 基线模型已完成，待补充 | 整理进 Notebook，补充改进模型、完整对比表、过拟合/欠拟合讨论 |
| 个人贡献声明 | 🔶 待整理汇总 | 汇总各成员贡献比例表 + 任务日志 + 签名声明，导出 PDF |
| requirements.txt | 🔶 待生成 | 根据项目实际使用的包生成依赖列表 |

### Part 5 具体待补充内容：
- 提出并实现至少一个改进模型（如 Ridge 回归、随机森林、梯度提升）
- 对比改进模型与基线模型在训练集、交叉验证、测试集上的表现
- 明确讨论过拟合/欠拟合现象
- 讨论时间分布偏移问题（训练集 2016–2024，测试集 2025）

---

## 环境安装
```bash
pip install -r requirements.txt
```

主要依赖包：`pandas`、`numpy`、`scikit-learn`、`matplotlib`、`seaborn`

---

## 提交截止日期

**2026 年 3 月 30 日（周一）**