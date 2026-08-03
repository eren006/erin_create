// 知识点学习内容 —— 结构化讲义,配合 basics 自测题和编程题一起用
// html 字段是可信的静态内容(自己写的,不是用户输入),直接 innerHTML 渲染

const LEARN_TOPICS = [
  // ---------------- SQL ----------------
  {
    id: 'l-sql-1',
    category: 'SQL',
    title: 'SELECT 基础与过滤',
    summary: 'WHERE vs HAVING、DISTINCT、NULL 的坑',
    html: `
      <h3>WHERE vs HAVING</h3>
      <p>WHERE 在分组(GROUP BY)之前执行,用来过滤原始行,不能直接用聚合函数;HAVING 在分组聚合之后执行,专门过滤聚合后的结果。</p>
      <pre class="code-block"><code>-- 找出订单数 &gt;= 3 的客户
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE status = 'completed'   -- 先过滤明细行
GROUP BY customer_id
HAVING COUNT(*) &gt;= 3;        -- 再过滤聚合结果</code></pre>
      <h3>DISTINCT 的作用范围</h3>
      <p>SELECT DISTINCT col1, col2 是对 (col1, col2) 这个组合去重,不是分别对每一列单独去重。</p>
      <h3>NULL 的坑</h3>
      <p>SQL 是三值逻辑(TRUE / FALSE / UNKNOWN)。任何值和 NULL 比较(包括 NULL = NULL)结果都是 UNKNOWN,不会被 WHERE 选中,必须用 IS NULL / IS NOT NULL。</p>
      <pre class="code-block"><code>-- 错误写法,永远查不到任何行
SELECT * FROM customers WHERE phone = NULL;

-- 正确写法
SELECT * FROM customers WHERE phone IS NULL;</code></pre>
    `,
  },
  {
    id: 'l-sql-2',
    category: 'SQL',
    title: 'JOIN 详解',
    summary: '四种 JOIN 的区别、反连接(anti-join)写法',
    html: `
      <h3>四种常见 JOIN</h3>
      <table class="ref-table">
        <tr><th>类型</th><th>返回内容</th></tr>
        <tr><td>INNER JOIN</td><td>只保留两表都能匹配上的行</td></tr>
        <tr><td>LEFT JOIN</td><td>保留左表全部行,右表没匹配到的列填 NULL</td></tr>
        <tr><td>RIGHT JOIN</td><td>保留右表全部行,左表没匹配到的列填 NULL(等价于把两表顺序换一下写 LEFT JOIN)</td></tr>
        <tr><td>FULL JOIN</td><td>两表都保留,谁没匹配到就补 NULL(SQLite 不直接支持,需要 UNION 两个 LEFT JOIN 模拟)</td></tr>
      </table>
      <h3>反连接(anti-join):找"没有"的数据</h3>
      <p>"从未下过单的客户"这类题,思路是 LEFT JOIN 之后,专挑右表主键是 NULL 的行:</p>
      <pre class="code-block"><code>SELECT c.name
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_id IS NULL;

-- 等价写法,用 NOT IN 子查询
SELECT name FROM customers
WHERE customer_id NOT IN (SELECT customer_id FROM orders);</code></pre>
      <p>注意:如果 NOT IN 的子查询结果里混入了 NULL,整个 NOT IN 会意外返回空结果——这是个经典陷阱,更安全的写法是用 NOT EXISTS 改写。</p>
    `,
  },
  {
    id: 'l-sql-3',
    category: 'SQL',
    title: '聚合与分组',
    summary: 'COUNT(*) vs COUNT(列)、常用聚合函数',
    html: `
      <h3>COUNT(*) vs COUNT(列)</h3>
      <p>COUNT(*) 统计行数,不管有没有 NULL;COUNT(列) 只统计该列非 NULL 的行数。这个区别在有缺失值的字段上经常被问到。</p>
      <h3>常用聚合函数</h3>
      <p>SUM / AVG / MAX / MIN / COUNT,只能配合 GROUP BY 使用,或者对整个结果集聚合(不加 GROUP BY 时相当于把整个表当一组)。</p>
      <pre class="code-block"><code>SELECT category, COUNT(*) AS cnt, AVG(price) AS avg_price
FROM products
GROUP BY category;</code></pre>
    `,
  },
  {
    id: 'l-sql-4',
    category: 'SQL',
    title: '窗口函数',
    summary: 'ROW_NUMBER/RANK/DENSE_RANK、累计求和、LAG/LEAD',
    html: `
      <h3>和 GROUP BY 的本质区别</h3>
      <p>GROUP BY 把每组压缩成一行;窗口函数在保留每一行明细的前提下,给每行附加"组内计算结果"。写法上多了 OVER (PARTITION BY ... ORDER BY ...)。</p>
      <h3>三个排名函数的区别</h3>
      <table class="ref-table">
        <tr><th>函数</th><th>并列(tie)时的行为</th></tr>
        <tr><td>ROW_NUMBER()</td><td>强制给唯一序号,不管并列</td></tr>
        <tr><td>RANK()</td><td>并列给相同名次,下一个名次跳号(1,2,2,4)</td></tr>
        <tr><td>DENSE_RANK()</td><td>并列给相同名次,下一个名次不跳号(1,2,2,3)</td></tr>
      </table>
      <h3>常见模式</h3>
      <pre class="code-block"><code>-- 每个客户的订单按日期排第几笔
ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date)

-- 累计求和(running total)
SUM(revenue) OVER (ORDER BY month)

-- 和上一行比较(环比、间隔天数)
LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date)</code></pre>
    `,
  },
  {
    id: 'l-sql-5',
    category: 'SQL',
    title: '子查询与 CTE',
    summary: 'EXISTS vs IN、WITH 的用法',
    html: `
      <h3>EXISTS vs IN</h3>
      <p>EXISTS 只判断"存在与否",一旦命中就停止;IN 需要把子查询结果整体物化再逐个比较。子查询结果集较大、只关心存在性时优先 EXISTS,而且 EXISTS 不受子查询里 NULL 值的坑影响,比 NOT IN 更安全。</p>
      <h3>CTE(WITH ... AS (...))</h3>
      <p>给一段查询命名,可以在同一条语句里被多次引用,把复杂查询拆成多个可读的步骤——主要价值是可读性和复用,不代表性能一定更快。</p>
      <pre class="code-block"><code>WITH monthly AS (
  SELECT strftime('%Y-%m', order_date) AS month, SUM(amount) AS revenue
  FROM orders GROUP BY month
)
SELECT month, revenue, SUM(revenue) OVER (ORDER BY month) AS running_total
FROM monthly;</code></pre>
    `,
  },
  {
    id: 'l-sql-6',
    category: 'SQL',
    title: 'UNION / UNION ALL',
    summary: '要不要去重、性能差异',
    html: `
      <p>UNION 会对合并结果去重(需要额外排序/哈希开销);UNION ALL 保留所有行、不去重,通常更快。确定不会有重复、或不在意重复时优先用 UNION ALL。两边 SELECT 的列数和类型需要对应。</p>
      <pre class="code-block"><code>SELECT city FROM customers
UNION ALL
SELECT city FROM suppliers;</code></pre>
    `,
  },
  {
    id: 'l-sql-7',
    category: 'SQL',
    title: '索引与性能',
    summary: '索引的代价、常见失效场景',
    html: `
      <p>索引本质是空间换时间:加速按索引列的查找/排序/JOIN,但会增加写入(INSERT/UPDATE/DELETE)的维护成本和存储空间,不是越多越好。</p>
      <h3>常见索引失效场景</h3>
      <ul>
        <li>对索引列做函数运算,如 WHERE YEAR(order_date) = 2023(应改写成范围比较 order_date &gt;= '2023-01-01' AND order_date &lt; '2024-01-01')</li>
        <li>用 LIKE '%关键词' 前导通配符(普通 B-Tree 索引无法做前缀匹配)</li>
        <li>索引列参与了隐式类型转换</li>
      </ul>
    `,
  },
  {
    id: 'l-sql-8',
    category: 'SQL',
    title: '事务与 ACID',
    summary: '原子性/一致性/隔离性/持久性',
    html: `
      <table class="ref-table">
        <tr><th>字母</th><th>含义</th></tr>
        <tr><td>A 原子性</td><td>事务里的操作要么全部成功,要么全部回滚</td></tr>
        <tr><td>C 一致性</td><td>事务前后数据都满足约束,不会出现"钱扣了但没到账"这种中间态被持久化</td></tr>
        <tr><td>I 隔离性</td><td>并发事务互不干扰,看不到彼此未提交的中间状态</td></tr>
        <tr><td>D 持久性</td><td>一旦提交,即使宕机数据也不会丢</td></tr>
      </table>
    `,
  },

  // ---------------- Pandas ----------------
  {
    id: 'l-pd-1',
    category: 'Pandas',
    title: '索引选取:loc / iloc / 布尔索引',
    summary: '标签 vs 位置、闭区间 vs 半开区间',
    html: `
      <p>loc 按标签(label)取,iloc 按整数位置(position)取,注意 loc 的切片是闭区间(包含末尾),iloc 是半开区间(不包含末尾)。</p>
      <pre class="code-block"><code>df.loc['a':'c']      # 包含 c
df.iloc[0:3]          # 不包含下标 3

# 布尔索引(最常用的筛选方式)
df[df['category'] == '电子产品']
df[(df['price'] > 100) & (df['city'] == '北京')]   # 多条件要用 & / | ,且每个条件要加括号</code></pre>
    `,
  },
  {
    id: 'l-pd-2',
    category: 'Pandas',
    title: '数据清洗:缺失值 / 去重 / 类型转换',
    summary: 'fillna vs dropna、duplicated、astype 的坑',
    html: `
      <h3>缺失值</h3>
      <p>fillna 填充(要结合业务含义选合适的填充值,比如均值/中位数/0/前值);缺失比例小、删掉不影响分析时用 dropna。</p>
      <h3>重复值</h3>
      <p>duplicated(keep='first'/'last'/False) 只标记不删除;drop_duplicates() 才是真正删除。</p>
      <h3>类型转换</h3>
      <p>astype('int') 遇到 NaN 或非数字字符串会直接报错,需要先清洗,或者改用支持缺失值的可空整型 'Int64'(注意大写 I)。</p>
    `,
  },
  {
    id: 'l-pd-3',
    category: 'Pandas',
    title: 'groupby 进阶:agg / transform / apply',
    summary: '返回形状的区别、as_index 参数',
    html: `
      <table class="ref-table">
        <tr><th>方法</th><th>返回形状</th><th>典型场景</th></tr>
        <tr><td>agg</td><td>行数 = 组数(汇总表)</td><td>每个分类的总销售额</td></tr>
        <tr><td>transform</td><td>行数 = 原表行数(可直接拼回原表)</td><td>给每一行加一列"该客户的平均订单额"</td></tr>
        <tr><td>apply</td><td>灵活,取决于函数返回什么</td><td>组内做复杂的自定义逻辑</td></tr>
      </table>
      <p>as_index=False:默认 groupby 会把分组列变成结果的索引;as_index=False 让分组列保留成普通列,方便后续链式操作(比如接 sort_values)。</p>
      <pre class="code-block"><code>sales_df.groupby('category', as_index=False)['revenue'].sum()

sales_df['customer_avg'] = sales_df.groupby('customer')['amount'].transform('mean')</code></pre>
    `,
  },
  {
    id: 'l-pd-4',
    category: 'Pandas',
    title: '合并与拼接:merge / concat',
    summary: '关联匹配 vs 简单堆叠,how 参数对应 SQL JOIN',
    html: `
      <p>concat 是简单堆叠(按索引/位置拼接多个结构相同的表);merge 是按某个字段的值做类似 SQL JOIN 的关联匹配,how 参数(left/right/inner/outer)含义和 SQL 的 JOIN 类型完全对应。</p>
      <pre class="code-block"><code>sales_df.merge(customers_df, on='customer', how='left')
pd.concat([df_jan, df_feb, df_mar])   # 按行摞起来</code></pre>
    `,
  },
  {
    id: 'l-pd-5',
    category: 'Pandas',
    title: '重塑数据:pivot_table / melt',
    summary: '长表转宽表、宽表转长表',
    html: `
      <p>pivot_table 把长表转成宽表(行列交叉的汇总矩阵),遇到重复的行列组合会自动用 aggfunc 聚合(普通 pivot 遇到重复组合会直接报错);melt 是反过来,把宽表转回长表。</p>
      <pre class="code-block"><code>tmp.pivot_table(index='city', columns='category', values='revenue', aggfunc='sum', fill_value=0)

pivot.melt(id_vars='city', var_name='category', value_name='revenue')</code></pre>
    `,
  },
  {
    id: 'l-pd-6',
    category: 'Pandas',
    title: 'apply / map / applymap',
    summary: '三者各自作用在什么对象上',
    html: `
      <table class="ref-table">
        <tr><th>方法</th><th>作用对象</th></tr>
        <tr><td>Series.map(func)</td><td>Series 逐元素映射</td></tr>
        <tr><td>DataFrame.apply(func, axis=)</td><td>按行(axis=1)或按列(axis=0)整体处理</td></tr>
        <tr><td>DataFrame.applymap(func)</td><td>DataFrame 每个格子逐一处理</td></tr>
      </table>
    `,
  },
  {
    id: 'l-pd-7',
    category: 'Pandas',
    title: '排序与排名:sort_values / rank',
    summary: 'rank 的 method 参数和 SQL 排名函数的对应关系',
    html: `
      <p>sort_values(by=[...], ascending=) 按值排序;rank() 计算名次,method 参数决定并列值怎么处理,和 SQL 的窗口排名函数概念完全对应:</p>
      <table class="ref-table">
        <tr><th>method</th><th>对应 SQL</th><th>并列时行为</th></tr>
        <tr><td>'min'</td><td>RANK()</td><td>并列取最小名次,后面跳号</td></tr>
        <tr><td>'dense'</td><td>DENSE_RANK()</td><td>并列取最小名次,后面不跳号</td></tr>
        <tr><td>'first'</td><td>ROW_NUMBER()</td><td>按出现顺序强制给唯一名次</td></tr>
      </table>
    `,
  },
  {
    id: 'l-pd-8',
    category: 'Pandas',
    title: '常用统计:value_counts / describe',
    summary: '频次统计、占比、数值列概况',
    html: `
      <p>value_counts() 统计每个取值出现的次数,默认按次数降序;normalize=True 把次数换算成占比。describe() 快速看数值列的统计概况(均值/标准差/分位数)。</p>
      <pre class="code-block"><code>sales_df['city'].value_counts(normalize=True)
sales_df['unit_price'].describe()</code></pre>
    `,
  },
];
