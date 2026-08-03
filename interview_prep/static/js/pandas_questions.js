// pandas 练习题库 —— 数据分析/BI 方向
// 每题要求把最终结果赋值给变量 result
// orderMatters: 行顺序是否重要(false 时判分会按全部列排序后再比较)

const PANDAS_QUESTIONS = [
  {
    id: 'pd-1',
    title: '按条件筛选',
    difficulty: '简单',
    prompt: '从 sales_df 中筛选出 category 为 "电子产品" 的所有行,赋值给 result。',
    dataHint: 'sales_df 列: order_id, date, customer, city, category, product, quantity, unit_price, rating',
    starter: `result = sales_df[...]`,
    solution: `result = sales_df[sales_df['category'] == '电子产品']`,
    orderMatters: true,
  },
  {
    id: 'pd-2',
    title: 'groupby 统计分类销售额',
    difficulty: '简单',
    prompt:
      '计算每个 category 的总销售额(quantity * unit_price 之和),按销售额从高到低排序。result 是两列的 DataFrame:category, revenue。',
    dataHint: '',
    starter: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
result = tmp.groupby(...)...`,
    solution: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
result = tmp.groupby('category', as_index=False)['revenue'].sum().sort_values('revenue', ascending=False).reset_index(drop=True)`,
    orderMatters: true,
  },
  {
    id: 'pd-3',
    title: '缺失值填充',
    difficulty: '简单偏中',
    prompt: '把 sales_df 的 rating 列缺失值用该列的平均值填充,其余列不变,把结果(完整 DataFrame)赋值给 result。',
    dataHint: '提示: fillna()',
    starter: `result = sales_df.copy()
result['rating'] = ...`,
    solution: `result = sales_df.copy()
result['rating'] = result['rating'].fillna(result['rating'].mean())`,
    orderMatters: true,
  },
  {
    id: 'pd-4',
    title: '热门城市 Top3',
    difficulty: '中等',
    prompt: '用 value_counts 统计各城市出现的订单条数,取出现次数最多的前 3 个城市,赋值给 result(一个 Series)。',
    dataHint: '',
    starter: `result = sales_df['city'].value_counts()...`,
    solution: `result = sales_df['city'].value_counts().head(3)`,
    orderMatters: true,
  },
  {
    id: 'pd-5',
    title: '透视表:城市 x 分类销售额',
    difficulty: '中等',
    prompt:
      '用 pivot_table,行是 city,列是 category,值是销售额(quantity*unit_price)总和,缺失填 0,赋值给 result。',
    dataHint: '',
    starter: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
result = tmp.pivot_table(...)`,
    solution: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
result = tmp.pivot_table(index='city', columns='category', values='revenue', aggfunc='sum', fill_value=0)`,
    orderMatters: true,
  },
  {
    id: 'pd-6',
    title: 'merge 关联客户等级',
    difficulty: '中等',
    prompt:
      '把 sales_df 和 customers_df 按 customer 字段关联,只保留 segment 为 "VIP" 的客户的销售记录,结果包含 sales_df 原有全部列 + segment 列,赋值给 result(重置索引)。',
    dataHint: 'customers_df 列: customer, segment, signup_date',
    starter: `merged = sales_df.merge(customers_df, on='customer', how='inner')
result = merged[...].reset_index(drop=True)`,
    solution: `merged = sales_df.merge(customers_df, on='customer', how='inner')
result = merged[merged['segment'] == 'VIP'].reset_index(drop=True)`,
    orderMatters: true,
  },
  {
    id: 'pd-7',
    title: 'apply 自定义分级',
    difficulty: '中等',
    prompt:
      '新增列 order_amount = quantity*unit_price;再新增列 amount_level:order_amount>=500 为 "高",100<=order_amount<500 为 "中",否则 "低"。把完整 DataFrame 赋值给 result。',
    dataHint: '提示: apply + 自定义函数或 lambda',
    starter: `result = sales_df.copy()
result['order_amount'] = result['quantity'] * result['unit_price']
result['amount_level'] = result['order_amount'].apply(...)`,
    solution: `def _level(x):
    if x >= 500:
        return '高'
    elif x >= 100:
        return '中'
    else:
        return '低'

result = sales_df.copy()
result['order_amount'] = result['quantity'] * result['unit_price']
result['amount_level'] = result['order_amount'].apply(_level)`,
    orderMatters: true,
  },
  {
    id: 'pd-8',
    title: '按月统计收入',
    difficulty: '中等',
    prompt:
      '把 date 列转成 datetime,按月份(格式 "YYYY-MM")分组统计总销售额,按月份排序。result 是两列: month, revenue。',
    dataHint: '提示: pd.to_datetime, dt.to_period("M")',
    starter: `tmp = sales_df.copy()
tmp['date'] = pd.to_datetime(tmp['date'])
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
tmp['month'] = ...
result = tmp.groupby(...)...`,
    solution: `tmp = sales_df.copy()
tmp['date'] = pd.to_datetime(tmp['date'])
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
tmp['month'] = tmp['date'].dt.to_period('M').astype(str)
result = tmp.groupby('month', as_index=False)['revenue'].sum().sort_values('month').reset_index(drop=True)`,
    orderMatters: true,
  },
  {
    id: 'pd-9',
    title: '客户内订单金额排名',
    difficulty: '中等偏难',
    prompt:
      '计算 order_amount = quantity*unit_price,在每个 customer 内部按 order_amount 从高到低排名(1 为最高,并列取最小名次),新增列 amount_rank(整数)。result 包含 customer, order_id, order_amount, amount_rank 四列,按 customer、amount_rank 排序,重置索引。',
    dataHint: '提示: groupby(...)[col].rank(ascending=False, method="min")',
    starter: `tmp = sales_df.copy()
tmp['order_amount'] = tmp['quantity'] * tmp['unit_price']
tmp['amount_rank'] = tmp.groupby('customer')['order_amount'].rank(...).astype(int)
result = tmp[[...]].sort_values([...]).reset_index(drop=True)`,
    solution: `tmp = sales_df.copy()
tmp['order_amount'] = tmp['quantity'] * tmp['unit_price']
tmp['amount_rank'] = tmp.groupby('customer')['order_amount'].rank(ascending=False, method='min').astype(int)
result = tmp[['customer', 'order_id', 'order_amount', 'amount_rank']].sort_values(['customer', 'amount_rank']).reset_index(drop=True)`,
    orderMatters: true,
  },
  {
    id: 'pd-10',
    title: '找出重复下单记录',
    difficulty: '中等',
    prompt:
      '找出同一 customer 在同一 date 下了多次单的重复记录(按 customer+date 判断,保留第一条之外的重复行),赋值给 result。',
    dataHint: '提示: duplicated(subset=[...], keep="first")',
    starter: `result = sales_df[sales_df.duplicated(subset=[...], keep='first')].reset_index(drop=True)`,
    solution: `result = sales_df[sales_df.duplicated(subset=['customer', 'date'], keep='first')].reset_index(drop=True)`,
    orderMatters: true,
  },
  {
    id: 'pd-11',
    title: '多重聚合',
    difficulty: '中等',
    prompt:
      '按 category 分组,同时计算总销量(quantity 之和)、平均单价(unit_price 均值)、订单数(order_id 计数)。result 列名为 category, total_quantity, avg_price, order_count。',
    dataHint: '提示: groupby(...).agg(new_col=(source_col, func))',
    starter: `result = sales_df.groupby('category', as_index=False).agg(
    total_quantity=(...),
    avg_price=(...),
    order_count=(...),
)`,
    solution: `result = sales_df.groupby('category', as_index=False).agg(
    total_quantity=('quantity', 'sum'),
    avg_price=('unit_price', 'mean'),
    order_count=('order_id', 'count'),
)`,
    orderMatters: false,
  },
  {
    id: 'pd-12',
    title: '宽表转长表(melt)',
    difficulty: '较难',
    prompt:
      '先做一个 city x category 的销售额透视表(同第 5 题,fill_value=0),再用 melt 把它转成长表,列名为 city, category, revenue,赋值给 result。',
    dataHint: '提示: pivot_table 后 reset_index(),再 melt(id_vars="city", ...)',
    starter: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
pivot = tmp.pivot_table(index='city', columns='category', values='revenue', aggfunc='sum', fill_value=0).reset_index()
result = pivot.melt(...)`,
    solution: `tmp = sales_df.copy()
tmp['revenue'] = tmp['quantity'] * tmp['unit_price']
pivot = tmp.pivot_table(index='city', columns='category', values='revenue', aggfunc='sum', fill_value=0).reset_index()
result = pivot.melt(id_vars='city', var_name='category', value_name='revenue')`,
    orderMatters: false,
  },
];
