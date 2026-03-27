# model_training

爱尔兰房产价格预测模型训练目录（COMP47350 Data Analysis）

---

## 文件结构

```
model_training/
├── train_data.csv                        # 训练集原始数据（含 dublin_district 列）
├── train_data_clean.csv                  # 清洗后的训练数据（模型输入）
├── test_data.csv                         # 外部测试集（原始，未清洗）
├── linear_regression.ipynb               # 线性回归模型
├── random_forest_model.ipynb             # 随机森林模型
├── ridge_lasso_model.ipynb               # Ridge / Lasso 正则化模型
└── linear_regression_coefficients.csv   # 线性回归各特征系数导出表
```

---

## 数据说明

### train_data.csv → train_data_clean.csv

原始训练数据经过以下清洗步骤后生成 `train_data_clean.csv`：

| 步骤 | 说明 |
|------|------|
| 文本标准化 | 去除多余空格，统一格式 |
| 日期解析 | `Date of Sale` 转为 datetime |
| 价格解析 | 去除 `€` 和逗号，转为 float |
| 去重 | 删除 9 条完全重复行 |
| 核心字段过滤 | 删除价格为空/负数、日期无效、County 为空的行 |
| VAT 调整 | 新房（`New Dwelling house`）且 `VAT Exclusive=Yes` 的价格 × 1.135 |
| 价格截断 | 按训练集 5%–95% 分位数截断极端值（60,000€ ~ 721,138€） |

### 最终特征（train_data_clean.csv，9列）

| 特征 | 类型 | 说明 |
|------|------|------|
| `Sale Year` | 数值 | 销售年份 |
| `Sale Month` | 数值 | 销售月份（1–12） |
| `is_apartment` | 0/1 | 地址中是否含 apartment/apt/unit/flat |
| `location` | 类别 | 都柏林用区号（如 Dublin 4），其他用 County 名 |
| `Description of Property` | 类别 | 房产类型（新房/二手房/其他） |
| `Not Full Market Price` | 类别 | 是否非全市价交易 |
| `Price_Adjusted_VAT_Clamped` | 数值 | 目标变量（VAT调整 + 截断后的价格） |
| `vat_adjusted_flag` | 0/1 | 是否经过 VAT 调整 |

---

## 模型说明

### 特征工程

- `location`、`Description of Property`、`Not Full Market Price` 做 **One-Hot 编码**，共生成 56 列
- `Sale Year`、`Sale Month`、`is_apartment`、`vat_adjusted_flag` 直接作为数值特征
- 最终输入维度：**60 列**
- Ridge/Lasso 额外使用 `StandardScaler` 对所有特征标准化

### 外部测试集结果对比

| 模型 | R² | RMSE | MAE |
|------|----|------|-----|
| Linear Regression | 0.3976 | 136,947€ | 104,861€ |
| Ridge (alpha=10) | 0.3975 | 136,922€ | 104,848€ |
| Lasso (alpha=100) | 0.3972 | 136,959€ | 104,896€ |
| Random Forest | 0.2834 | 149,331€ | 113,972€ |

**最终选用模型：Ridge 回归（alpha=10）**
- 与线性回归效果相当，但具备正则化理论保障
- 随机森林在外部测试集上出现明显过拟合，泛化能力较差
- 正则化对本数据集提升有限，原因是原始线性回归本身未出现过拟合

---

## 运行顺序

1. 运行 `linear_regression.ipynb` — 数据清洗 + 线性回归训练与评估
2. 运行 `random_forest_model.ipynb` — 随机森林训练与评估
3. 运行 `ridge_lasso_model.ipynb` — Ridge/Lasso 正则化训练与评估

> 注意：`test_data.csv` 为原始未清洗数据，各 notebook 内部均包含对应的清洗流程。
