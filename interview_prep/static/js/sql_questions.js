// SQL 练习题库 —— 数据分析/BI 方向
// orderMatters: 结果行顺序是否重要(false 时判分会先排序再比较)

const SQL_QUESTIONS = [
  {
    id: 'sql-1',
    title: '筛选 VIP 客户',
    difficulty: '简单',
    prompt: '查询所有 segment 为 "VIP" 的客户,返回 name 和 city 两列。',
    schemaHint: 'customers(customer_id, name, city, signup_date, segment)',
    starter: 'SELECT\n  --\nFROM customers\nWHERE ...;',
    solution: `SELECT name, city FROM customers WHERE segment = 'VIP';`,
    orderMatters: false,
  },
  {
    id: 'sql-2',
    title: '电子产品按价格排序',
    difficulty: '简单',
    prompt: '查询 category 为 "电子产品" 的商品,返回 name 和 price,按 price 从高到低排序。',
    schemaHint: 'products(product_id, name, category, price)',
    starter: 'SELECT\n  --\nFROM products\nWHERE ...\nORDER BY ...;',
    solution: `SELECT name, price FROM products WHERE category = '电子产品' ORDER BY price DESC;`,
    orderMatters: true,
  },
  {
    id: 'sql-3',
    title: '统计已完成订单数',
    difficulty: '简单',
    prompt: '统计 status 为 "completed" 的订单总数,返回一列,列名随意。',
    schemaHint: 'orders(order_id, customer_id, order_date, status)',
    starter: 'SELECT COUNT(*)\nFROM orders\nWHERE ...;',
    solution: `SELECT COUNT(*) FROM orders WHERE status = 'completed';`,
    orderMatters: false,
  },
  {
    id: 'sql-4',
    title: '高频下单客户',
    difficulty: '中等',
    prompt:
      '按客户统计其 "completed" 订单数量,只保留订单数 >= 3 的客户,返回客户姓名和订单数。',
    schemaHint: 'orders JOIN customers ON orders.customer_id = customers.customer_id',
    starter:
      'SELECT c.name, COUNT(*) AS order_count\nFROM orders o\nJOIN customers c ON o.customer_id = c.customer_id\nWHERE ...\nGROUP BY ...\nHAVING ...;',
    solution: `SELECT c.name, COUNT(*) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.status = 'completed'
GROUP BY c.customer_id
HAVING COUNT(*) >= 3;`,
    orderMatters: false,
  },
  {
    id: 'sql-5',
    title: '从未下单的客户',
    difficulty: '中等',
    prompt: '找出从未下过任何订单的客户姓名(不限订单状态)。',
    schemaHint: '提示:可以用 NOT IN 子查询或 LEFT JOIN + IS NULL',
    starter: 'SELECT name\nFROM customers\nWHERE customer_id NOT IN (...);',
    solution: `SELECT name FROM customers WHERE customer_id NOT IN (SELECT customer_id FROM orders);`,
    orderMatters: false,
  },
  {
    id: 'sql-6',
    title: '分类销售额排行',
    difficulty: '中等',
    prompt:
      '统计每个商品分类(category)在 "completed" 订单中的总销售额(quantity * unit_price 之和),按销售额从高到低排序,返回 category 和 revenue。',
    schemaHint: 'order_items JOIN orders JOIN products,三表关联',
    starter:
      'SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue\nFROM order_items oi\nJOIN orders o ON ...\nJOIN products p ON ...\nWHERE ...\nGROUP BY ...\nORDER BY ...;',
    solution: `SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY revenue DESC;`,
    orderMatters: true,
  },
  {
    id: 'sql-7',
    title: '客户第几笔订单(窗口函数)',
    difficulty: '中等',
    prompt:
      '对每个客户的 "completed" 订单按 order_date 排序,用窗口函数标出这是该客户第几笔订单(从 1 开始)。返回客户姓名、订单日期、序号。',
    schemaHint: '提示:ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)',
    starter:
      'SELECT c.name, o.order_date, ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) AS seq\nFROM orders o\nJOIN customers c ON ...\nWHERE ...;',
    solution: `SELECT c.name, o.order_date,
  ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.order_date) AS seq
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.status = 'completed';`,
    orderMatters: false,
  },
  {
    id: 'sql-8',
    title: '分类内价格排名(窗口函数)',
    difficulty: '中等',
    prompt: '对每个商品,按 category 分组,在组内按 price 从高到低排名,返回 category、name、price、排名。',
    schemaHint: '提示:RANK() OVER (PARTITION BY ... ORDER BY ...)',
    starter: 'SELECT category, name, price, RANK() OVER (...) AS rnk\nFROM products;',
    solution: `SELECT category, name, price,
  RANK() OVER (PARTITION BY category ORDER BY price DESC) AS rnk
FROM products;`,
    orderMatters: false,
  },
  {
    id: 'sql-9',
    title: '按月统计收入',
    difficulty: '中等偏难',
    prompt:
      '统计每个月(格式 "YYYY-MM")"completed" 订单的总收入,按月份排序。',
    schemaHint: '提示:strftime(\'%Y-%m\', order_date)',
    starter:
      "SELECT strftime('%Y-%m', o.order_date) AS month, SUM(oi.quantity * oi.unit_price) AS revenue\nFROM orders o\nJOIN order_items oi ON ...\nWHERE ...\nGROUP BY ...\nORDER BY ...;",
    solution: `SELECT strftime('%Y-%m', o.order_date) AS month,
  SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
GROUP BY month
ORDER BY month;`,
    orderMatters: true,
  },
  {
    id: 'sql-10',
    title: '月度收入累计(running total)',
    difficulty: '较难',
    prompt:
      '在按月统计 "completed" 订单收入的基础上,用窗口函数计算累计总收入(running total)。返回 month、revenue、running_total,按月份排序。',
    schemaHint: '提示:先用 CTE 算出月度收入,再 SUM(revenue) OVER (ORDER BY month)',
    starter:
      "WITH monthly AS (\n  SELECT strftime('%Y-%m', o.order_date) AS month, SUM(oi.quantity * oi.unit_price) AS revenue\n  FROM orders o\n  JOIN order_items oi ON ...\n  WHERE ...\n  GROUP BY month\n)\nSELECT month, revenue, SUM(revenue) OVER (ORDER BY month) AS running_total\nFROM monthly\nORDER BY month;",
    solution: `WITH monthly AS (
  SELECT strftime('%Y-%m', o.order_date) AS month,
    SUM(oi.quantity * oi.unit_price) AS revenue
  FROM orders o
  JOIN order_items oi ON o.order_id = oi.order_id
  WHERE o.status = 'completed'
  GROUP BY month
)
SELECT month, revenue, SUM(revenue) OVER (ORDER BY month) AS running_total
FROM monthly
ORDER BY month;`,
    orderMatters: true,
  },
  {
    id: 'sql-11',
    title: '高于平均订单金额的客户',
    difficulty: '较难',
    prompt:
      '每个订单的金额 = 该订单所有明细 quantity*unit_price 之和(只算 completed 订单)。找出"平均订单金额"高于"全体客户平均订单金额"的客户,返回客户姓名和其平均订单金额。',
    schemaHint: '提示:先用 CTE 算出每个订单的金额,再算每个客户的平均值,再和全局平均比较',
    starter:
      'WITH order_totals AS (\n  SELECT o.order_id, o.customer_id, SUM(oi.quantity * oi.unit_price) AS total\n  FROM orders o\n  JOIN order_items oi ON ...\n  WHERE ...\n  GROUP BY o.order_id\n),\ncustomer_avg AS (\n  SELECT customer_id, AVG(total) AS avg_total FROM order_totals GROUP BY customer_id\n)\nSELECT c.name, ca.avg_total\nFROM customer_avg ca\nJOIN customers c ON ...\nWHERE ca.avg_total > (SELECT AVG(total) FROM order_totals);',
    solution: `WITH order_totals AS (
  SELECT o.order_id, o.customer_id, SUM(oi.quantity * oi.unit_price) AS total
  FROM orders o
  JOIN order_items oi ON o.order_id = oi.order_id
  WHERE o.status = 'completed'
  GROUP BY o.order_id
),
customer_avg AS (
  SELECT customer_id, AVG(total) AS avg_total FROM order_totals GROUP BY customer_id
)
SELECT c.name, ca.avg_total
FROM customer_avg ca
JOIN customers c ON c.customer_id = ca.customer_id
WHERE ca.avg_total > (SELECT AVG(total) FROM order_totals);`,
    orderMatters: false,
  },
  {
    id: 'sql-12',
    title: 'CASE WHEN 分组统计',
    difficulty: '简单偏中',
    prompt:
      '用 CASE WHEN 把客户按 signup_date 分成 "2022年" (早于 2023-01-01) 和 "2023年" 两组,统计每组人数。',
    schemaHint: '返回两列:年份分组、人数',
    starter:
      "SELECT CASE WHEN signup_date < '2023-01-01' THEN '2022年' ELSE '2023年' END AS year_group,\n  COUNT(*) AS cnt\nFROM customers\nGROUP BY ...;",
    solution: `SELECT CASE WHEN signup_date < '2023-01-01' THEN '2022年' ELSE '2023年' END AS year_group,
  COUNT(*) AS cnt
FROM customers
GROUP BY year_group;`,
    orderMatters: false,
  },
  {
    id: 'sql-13',
    title: '复购客户首末订单',
    difficulty: '中等',
    prompt:
      '找出下过 2 次及以上 "completed" 订单的客户,返回客户姓名、首次下单日期(first_order)、最后一次下单日期(last_order)、订单数(cnt)。',
    schemaHint: '提示:GROUP BY + MIN/MAX + HAVING',
    starter:
      'SELECT c.name, MIN(o.order_date) AS first_order, MAX(o.order_date) AS last_order, COUNT(*) AS cnt\nFROM orders o\nJOIN customers c ON ...\nWHERE ...\nGROUP BY ...\nHAVING ...;',
    solution: `SELECT c.name, MIN(o.order_date) AS first_order, MAX(o.order_date) AS last_order, COUNT(*) AS cnt
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.status = 'completed'
GROUP BY c.customer_id
HAVING COUNT(*) >= 2;`,
    orderMatters: false,
  },
  {
    id: 'sql-14',
    title: '相邻订单间隔天数(LAG)',
    difficulty: '较难',
    prompt:
      '对每个客户的 "completed" 订单按日期排序,用 LAG() 计算与上一笔订单相隔的天数(第一笔为 NULL)。返回客户姓名、订单日期、间隔天数 gap_days。',
    schemaHint: '提示:julianday(date1) - julianday(date2) 可以算天数差;LAG(col) OVER (PARTITION BY ... ORDER BY ...)',
    starter:
      'SELECT c.name, o.order_date,\n  julianday(o.order_date) - julianday(LAG(o.order_date) OVER (PARTITION BY ... ORDER BY ...)) AS gap_days\nFROM orders o\nJOIN customers c ON ...\nWHERE ...;',
    solution: `SELECT c.name, o.order_date,
  julianday(o.order_date) - julianday(LAG(o.order_date) OVER (PARTITION BY o.customer_id ORDER BY o.order_date)) AS gap_days
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.status = 'completed';`,
    orderMatters: false,
  },
];
