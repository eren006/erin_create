// 基础知识点选择题 —— 复习 + 自测,配合 SQL / pandas 编程题一起用
// options 4 个,correctIndex 是正确选项下标(从0开始)

const BASICS_QUESTIONS = [
  // ---------------- SQL ----------------
  {
    id: 'b-sql-1',
    category: 'SQL',
    title: 'WHERE 和 HAVING 的区别',
    question: 'SELECT 查询中,WHERE 和 HAVING 的核心区别是什么?',
    options: [
      'WHERE 用于过滤分组前的行,HAVING 用于过滤分组后的聚合结果',
      'WHERE 和 HAVING 完全可以互换,没有区别',
      'HAVING 只能用在没有 GROUP BY 的查询里',
      'WHERE 可以直接使用聚合函数(如 SUM),HAVING 不行',
    ],
    correctIndex: 0,
    explanation:
      'WHERE 在 GROUP BY 之前执行,不能直接用聚合函数;HAVING 在分组聚合之后执行,专门用来过滤聚合结果(比如"订单数 >= 3 的客户")。',
  },
  {
    id: 'b-sql-2',
    category: 'SQL',
    title: 'INNER JOIN 会漏掉哪些数据',
    question: '下面哪种情况会导致 INNER JOIN 漏掉数据,而 LEFT JOIN 不会?',
    options: [
      '两张表的 JOIN 字段类型不一致',
      '右表中没有能匹配左表某些行的记录',
      '左表数据量比右表大',
      'JOIN 条件写反了表的顺序',
    ],
    correctIndex: 1,
    explanation:
      'INNER JOIN 只保留两边都匹配的行,右表没有对应记录的左表行会被直接丢弃;LEFT JOIN 会保留左表全部行,右表缺失部分用 NULL 填充——这正是"查找从未下单的客户"这类题要用 LEFT JOIN/NOT IN 而不是 INNER JOIN 的原因。',
  },
  {
    id: 'b-sql-3',
    category: 'SQL',
    title: 'COUNT(*) 和 COUNT(列)',
    question: 'COUNT(*) 和 COUNT(某列) 的区别是什么?',
    options: [
      '没有区别,两者永远返回相同结果',
      'COUNT(*) 统计所有行(不管有没有 NULL),COUNT(某列) 只统计该列非 NULL 的行数',
      'COUNT(*) 比 COUNT(某列) 慢很多倍',
      'COUNT(某列) 会自动去重',
    ],
    correctIndex: 1,
    explanation:
      'COUNT(*) 统计行数,不关心列值是否为 NULL;COUNT(column) 只统计该列不为 NULL 的行数,这个区别在有缺失值的字段上经常被问到。',
  },
  {
    id: 'b-sql-4',
    category: 'SQL',
    title: 'DISTINCT 的作用范围',
    question: 'SELECT DISTINCT col1, col2 中,DISTINCT 的去重范围是什么?',
    options: [
      '只对 col1 去重',
      '对 (col1, col2) 整行组合去重',
      '只能配合 COUNT 使用',
      '会自动按 col1 排序',
    ],
    correctIndex: 1,
    explanation: 'DISTINCT 是对 SELECT 列出的所有列组合(整行)去重,不是分别对每一列单独去重。',
  },
  {
    id: 'b-sql-5',
    category: 'SQL',
    title: 'UNION 和 UNION ALL',
    question: 'UNION 和 UNION ALL 的区别?',
    options: [
      'UNION 会自动去重,UNION ALL 保留所有重复行(通常更快)',
      'UNION ALL 会去重,UNION 不会',
      '两者性能完全一样',
      'UNION 只能合并两张同名表',
    ],
    correctIndex: 0,
    explanation:
      'UNION 需要额外做去重,开销更大;明确知道结果不会重复、或不在意重复时,优先用 UNION ALL。',
  },
  {
    id: 'b-sql-6',
    category: 'SQL',
    title: '窗口函数 vs GROUP BY',
    question: '窗口函数(如 ROW_NUMBER() OVER(...))和 GROUP BY 最大的区别是什么?',
    options: [
      '窗口函数会把明细行压缩成一行',
      '窗口函数可以在保留每一行明细的同时,计算分组内的排名/累计值等',
      '窗口函数不能配合 PARTITION BY 使用',
      'GROUP BY 可以返回和窗口函数完全相同的明细结果',
    ],
    correctIndex: 1,
    explanation:
      'GROUP BY 会把每组压缩成一行;窗口函数在不合并行的前提下,对每一行附加"组内"计算结果(排名、累计和、上下行对比等)——这是"给每个客户的订单标第几笔"这类题必须用窗口函数的原因。',
  },
  {
    id: 'b-sql-7',
    category: 'SQL',
    title: 'ROW_NUMBER/RANK/DENSE_RANK',
    question: '遇到并列(tie)值时,ROW_NUMBER()、RANK()、DENSE_RANK() 的区别?',
    options: [
      '三者结果永远相同',
      'ROW_NUMBER 强制给唯一序号,RANK 并列同名次但跳号,DENSE_RANK 并列同名次但不跳号',
      'RANK 和 DENSE_RANK 都会跳号',
      'ROW_NUMBER 会根据并列值自动分组',
    ],
    correctIndex: 1,
    explanation:
      '比如两个并列第2名:ROW_NUMBER 给 2,3(强制区分);RANK 给 2,2,下一个是4(跳过3);DENSE_RANK 给 2,2,下一个是3(不跳号)。',
  },
  {
    id: 'b-sql-8',
    category: 'SQL',
    title: 'EXISTS 和 IN',
    question: '什么情况下用 EXISTS 通常比 IN 更合适?',
    options: [
      '子查询结果集较大、且只需要判断"是否存在匹配关系"时',
      '任何时候都完全等价,没有场景区别',
      'IN 不能配合子查询使用',
      'EXISTS 只能用在 UPDATE 语句里',
    ],
    correctIndex: 0,
    explanation:
      'EXISTS 一旦找到匹配就停止判断,常用于"关联子查询判断存在性"的场景;IN 需要先把子查询结果物化再逐个比较,数据量大时容易更慢(具体表现因数据库优化器而异)。',
  },
  {
    id: 'b-sql-9',
    category: 'SQL',
    title: 'NULL 值比较的坑',
    question: '为什么 WHERE col = NULL 永远查不出结果,即便 col 确实有 NULL 值?',
    options: [
      'NULL 表示"未知",任何值(包括 NULL 自己)和它比较结果都不是 TRUE,要用 IS NULL 判断',
      '这是数据库的 bug',
      'NULL 会被自动转换成空字符串参与比较',
      '只有字符串类型的列才有这个问题',
    ],
    correctIndex: 0,
    explanation:
      'SQL 的三值逻辑(TRUE/FALSE/UNKNOWN)决定了 NULL = NULL 结果是 UNKNOWN 而不是 TRUE,必须用 IS NULL / IS NOT NULL 显式判断。',
  },
  {
    id: 'b-sql-10',
    category: 'SQL',
    title: 'CTE 的价值',
    question: 'CTE(WITH ... AS (...))相比子查询的主要优势是什么?',
    options: [
      '执行速度必然更快',
      '可以把复杂查询拆成多个命名步骤,提高可读性,还能被同一查询多次引用',
      'CTE 可以永久保存结果供其他查询使用',
      'CTE 只能嵌套一层',
    ],
    correctIndex: 1,
    explanation:
      'CTE 本质是给一段查询命名,主要价值是可读性和复用(比如先算月度收入,再在同一语句里对它做累计求和),不代表性能一定更好。',
  },
  {
    id: 'b-sql-11',
    category: 'SQL',
    title: '索引的代价',
    question: '索引(Index)能加速查找/排序/JOIN,但滥用会带来什么代价?',
    options: [
      '只加速 INSERT,不影响查询',
      '会增加写入(INSERT/UPDATE/DELETE)的开销和额外存储空间',
      '索引对任何查询都百利而无一害',
      '索引只能建在主键上',
    ],
    correctIndex: 1,
    explanation:
      '索引本质是空间换时间——查询变快了,但每次写入都要同步维护索引结构,索引越多写入越慢,还要占额外存储。',
  },
  {
    id: 'b-sql-12',
    category: 'SQL',
    title: '索引失效',
    question: 'WHERE YEAR(order_date) = 2023 这种对索引列做函数运算的写法,通常会导致什么问题?',
    options: [
      '没有任何影响',
      '索引可能失效,退化成全表扫描',
      '会报语法错误',
      '数据库会自动帮你建一个新索引',
    ],
    correctIndex: 1,
    explanation:
      '对列做函数变换后,数据库通常无法直接用列上的索引匹配,只能逐行计算再比较。更好的写法是 WHERE order_date >= \'2023-01-01\' AND order_date < \'2024-01-01\',这样能利用索引做范围扫描。',
  },
  {
    id: 'b-sql-13',
    category: 'SQL',
    title: '事务的隔离性',
    question: '事务 ACID 中的 "I"(Isolation 隔离性)说的是什么?',
    options: [
      '事务要么全部成功要么全部失败',
      '并发执行的事务互不干扰,不会看到彼此未提交的中间状态',
      '数据一旦提交就永久保存',
      '事务里所有约束都必须满足',
    ],
    correctIndex: 1,
    explanation:
      'A=原子性(全成功/全回滚),C=一致性(数据始终满足约束),I=隔离性(并发事务互不干扰),D=持久性(提交后即使宕机也不丢)。',
  },
  {
    id: 'b-sql-14',
    category: 'SQL',
    title: '反连接(anti-join)写法',
    question: 'LEFT JOIN 之后,想找出"右表没有匹配到的行"(比如没下过单的客户),正确写法通常是?',
    options: [
      'WHERE 右表任意非主键列 = NULL',
      'WHERE 右表主键列 IS NULL(比如 WHERE o.order_id IS NULL)',
      '直接用 INNER JOIN 就能找到',
      '不需要额外条件,LEFT JOIN 自动只返回未匹配行',
    ],
    correctIndex: 1,
    explanation:
      'LEFT JOIN 保留左表所有行,未匹配的右表列会是 NULL;加上 WHERE 右表列 IS NULL,就能筛出"左表有、右表没有对应记录"的行,这是经典的反连接写法。',
  },

  // ---------------- Pandas ----------------
  {
    id: 'b-pd-1',
    category: 'Pandas',
    title: 'loc vs iloc',
    question: 'loc 和 iloc 最核心的区别是什么?',
    options: [
      'loc 按标签(label)索引,iloc 按整数位置(position)索引',
      'loc 只能选行,iloc 只能选列',
      '两者完全等价,可以互换',
      'loc 比 iloc 快很多',
    ],
    correctIndex: 0,
    explanation:
      "df.loc['a':'c'] 按索引标签取(闭区间,包含末尾);df.iloc[0:3] 按位置取(半开区间,不包含末尾),这个区间开闭的差别也是常见坑点。",
  },
  {
    id: 'b-pd-2',
    category: 'Pandas',
    title: 'apply / map / applymap',
    question: 'apply、map、applymap 三者的适用范围区别?',
    options: [
      'map 用于 Series 逐元素映射;apply 可用于 Series 或 DataFrame(逐行/逐列);applymap 用于 DataFrame 逐元素操作',
      '三者功能完全相同,随便用哪个都行',
      'applymap 只能用在 Series 上',
      'apply 不能接受自定义函数',
    ],
    correctIndex: 0,
    explanation:
      '简单记:Series 用 map 做元素级映射;DataFrame 整行/整列级操作用 apply(可指定 axis);DataFrame 每个格子都要处理用 applymap。',
  },
  {
    id: 'b-pd-3',
    category: 'Pandas',
    title: "merge 的 how 参数",
    question: "merge() 的 how 参数中,'left' 和 'inner' 的区别?",
    options: [
      "'left' 保留左表所有行(右表没匹配的填 NaN),'inner' 只保留两边都匹配的行",
      "'left' 只保留左表中存在于右表的行",
      "'inner' 会保留左表所有行",
      '两者结果行数必然相同',
    ],
    correctIndex: 0,
    explanation:
      "和 SQL 的 LEFT JOIN / INNER JOIN 完全对应,'left' 常用来\"给主表补充维度信息但不想丢数据\",'inner' 用来\"只要两边都有的交集\"。",
  },
  {
    id: 'b-pd-4',
    category: 'Pandas',
    title: '赋值 vs copy()',
    question: "df2 = df1 之后修改 df2 有时会连带修改 df1,是为什么?",
    options: [
      'pandas 有 bug',
      'df2 = df1 只是复制了引用,两个变量指向同一块数据;要独立副本必须显式 .copy()',
      '只有数值列会有这个问题',
      '这只在 Jupyter 里发生,脚本里不会',
    ],
    correctIndex: 1,
    explanation:
      '直接赋值(=)不会创建新数据,只是多了一个指向同一 DataFrame 的"标签";想要互不影响的独立副本要写 df2 = df1.copy()。',
  },
  {
    id: 'b-pd-5',
    category: 'Pandas',
    title: 'transform vs agg',
    question: "groupby(...).transform() 和 groupby(...).agg() 的结果形状有什么区别?",
    options: [
      'transform 返回和原 DataFrame 行数相同的结果(可直接拼回原表),agg 返回按组聚合后、行数等于组数的结果',
      '两者返回的行数永远相同',
      'agg 不能同时计算多个统计量',
      'transform 只能用来求和',
    ],
    correctIndex: 0,
    explanation:
      "比如想给原表新增一列\"该客户的平均订单额\",要用 transform('mean')(结果长度和原表一致,可直接赋值成新列);只想要每个客户一行的汇总表则用 agg('mean')。",
  },
  {
    id: 'b-pd-6',
    category: 'Pandas',
    title: 'fillna vs dropna',
    question: 'fillna() 和 dropna() 该怎么选?',
    options: [
      '永远优先用 dropna,更简单',
      '要结合业务含义:有明确合理填充值时用 fillna,缺失比例小且删除不影响分析时用 dropna',
      '两者对结果的影响完全一样',
      'fillna 只能填 0',
    ],
    correctIndex: 1,
    explanation:
      '核心是看缺失值背后的业务含义——比如评分缺失可能代表"没评价"而不是"评分是0",直接 fillna(0) 会扭曲分布,这时候可能保留 NaN 或用均值/中位数更合理。',
  },
  {
    id: 'b-pd-7',
    category: 'Pandas',
    title: 'concat vs merge',
    question: 'concat() 和 merge() 的本质区别?',
    options: [
      'concat 按索引/位置简单拼接(堆叠行或拼接列),merge 按某个字段的值做类似 SQL JOIN 的关联匹配',
      'concat 只能拼接列,merge 只能拼接行',
      '两者是同一个函数的不同名字',
      'merge 不能指定连接方式(how)',
    ],
    correctIndex: 0,
    explanation:
      '多个结构相同的表"摞起来"用 concat;两个表要按共同字段(比如 customer_id)关联起来用 merge。',
  },
  {
    id: 'b-pd-8',
    category: 'Pandas',
    title: 'pivot vs pivot_table',
    question: 'pivot_table 相比 pivot 多了什么能力?',
    options: [
      'pivot_table 支持对重复的行列组合做聚合(aggfunc),pivot 遇到重复组合会直接报错',
      'pivot 支持聚合,pivot_table 不支持',
      '两者功能完全相同',
      'pivot_table 只能用于数值列',
    ],
    correctIndex: 0,
    explanation:
      '如果同一个 (index, columns) 组合在原始数据里出现了多行,用 pivot 会报 "Index contains duplicate entries" 错误,这时需要 pivot_table 指定 aggfunc(如 \'sum\')先聚合再摊开。',
  },
  {
    id: 'b-pd-9',
    category: 'Pandas',
    title: 'astype 转换的坑',
    question: "对包含缺失值(NaN)的列用 astype('int') 会发生什么?",
    options: [
      '自动把 NaN 变成 0',
      "通常会直接报错,需要先处理缺失值,或改用可空整数类型 'Int64'",
      'pandas 会自动跳过有问题的行',
      '什么都不会发生,正常转换',
    ],
    correctIndex: 1,
    explanation:
      "int 类型不支持 NaN,常见做法是先 fillna/dropna,或者转换成 pandas 的可空整型 'Int64'(注意大写 I)。",
  },
  {
    id: 'b-pd-10',
    category: 'Pandas',
    title: 'duplicated 的 keep 参数',
    question: "duplicated() 的 keep 参数 'first'、'last'、False 分别是什么效果?",
    options: [
      "'first' 保留每组重复中的第一条不标记(其余标记为重复),'last' 保留最后一条,False 把所有重复行都标记为重复",
      '三个参数效果完全一样',
      "False 表示不检测重复",
      "'first' 会直接删除第一条",
    ],
    correctIndex: 0,
    explanation:
      'duplicated() 本身只是标记,不删除;keep 决定"哪一条不算重复"。要真正删除用 drop_duplicates(),参数含义一致。',
  },
  {
    id: 'b-pd-11',
    category: 'Pandas',
    title: 'value_counts normalize',
    question: 'value_counts(normalize=True) 相比默认的 value_counts() 多返回什么?',
    options: [
      '返回占比(比例,所有值加总为1)而不是绝对次数',
      '会自动画图',
      '会按字母顺序排序而不是按频次排序',
      '只统计前 5 个类别',
    ],
    correctIndex: 0,
    explanation:
      '默认返回每个取值出现的次数;normalize=True 把次数换算成占总数的比例,做"各城市订单占比"这类分析时很常用。',
  },
  {
    id: 'b-pd-12',
    category: 'Pandas',
    title: 'reset_index 的 drop 参数',
    question: 'reset_index(drop=True) 中 drop=True 和默认的 drop=False 的区别?',
    options: [
      'drop=True 直接丢弃旧索引;默认会把旧索引变成一个新列保留下来',
      'drop 参数只影响列名,不影响数据',
      'drop=True 会删除所有数据',
      '两者结果完全一样',
    ],
    correctIndex: 0,
    explanation:
      '比如 filter/groupby 之后索引变得不连续,只想要一个干净的 0,1,2... 索引、不需要保留旧索引值时用 drop=True;如果旧索引本身有意义(比如是日期)想留着当列,就用默认的 drop=False。',
  },
  {
    id: 'b-pd-13',
    category: 'Pandas',
    title: "rank 的 method 参数",
    question: "rank() 的 method 参数中 'min' 和 'dense' 遇到并列值时的区别?",
    options: [
      "'min' 并列取最小名次但后续跳号,'dense' 并列取最小名次但后续不跳号(对应 SQL 的 RANK / DENSE_RANK)",
      '两者结果永远相同',
      "'dense' 只能用于字符串列",
      "'min' 会自动去重",
    ],
    correctIndex: 0,
    explanation:
      '和 SQL 里 RANK() vs DENSE_RANK() 是同一个概念在 pandas 里的对应,"两个并列第1名的下一个名次该是几"就是在考这个区别。',
  },
  {
    id: 'b-pd-14',
    category: 'Pandas',
    title: 'groupby as_index 参数',
    question: "groupby('col', as_index=False) 里 as_index=False 的作用?",
    options: [
      '分组结果会把分组列还原成普通列,而不是设成结果的索引,方便后续继续当 DataFrame 处理',
      'as_index=False 会禁用分组,直接返回原表',
      '只影响排序方式',
      'as_index 只能设为 True',
    ],
    correctIndex: 0,
    explanation:
      '默认 groupby 会把分组列变成结果索引;as_index=False 让分组列保留为普通列,配合链式操作(比如接着 sort_values)更方便,不用额外 reset_index()。',
  },
];
