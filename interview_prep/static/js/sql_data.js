// 构造 SQL 练习用的种子数据库(电商/BI 场景:客户、商品、订单、订单明细)
// 用 JS 数组生成 INSERT,避免手写 SQL 时把单价和商品表对不上

const SQL_SCHEMA_DATA = (function () {
  const customers = [
    [1, '张伟', '北京', '2023-01-15', 'VIP'],
    [2, '王芳', '上海', '2023-02-20', 'Regular'],
    [3, '李娜', '广州', '2023-01-05', 'Regular'],
    [4, '刘洋', '深圳', '2023-03-10', 'New'],
    [5, '陈静', '北京', '2022-11-01', 'VIP'],
    [6, '杨磊', '成都', '2023-04-18', 'Regular'],
    [7, '赵敏', '上海', '2023-05-22', 'New'],
    [8, '孙涛', '杭州', '2023-02-14', 'Regular'],
    [9, '周琳', '北京', '2022-12-25', 'VIP'],
    [10, '吴昊', '深圳', '2023-06-01', 'New'],
    [11, '郑爽', '广州', '2023-03-15', 'Regular'],
    [12, '冯霞', '成都', '2023-01-28', 'Regular'],
    [13, '蒋勇', '杭州', '2023-07-01', 'New'],
    [14, '韩梅', '北京', '2023-05-05', 'New'],
    [15, '曹颖', '上海', '2023-06-15', 'New'],
  ];

  const products = [
    [1, '无线鼠标', '电子产品', 79.0],
    [2, '机械键盘', '电子产品', 299.0],
    [3, '蓝牙耳机', '电子产品', 199.0],
    [4, '笔记本电脑支架', '办公用品', 89.0],
    [5, '保温杯', '生活用品', 59.0],
    [6, '记事本', '办公用品', 15.0],
    [7, '台灯', '生活用品', 129.0],
    [8, '移动电源', '电子产品', 99.0],
    [9, '办公椅', '办公用品', 599.0],
    [10, '咖啡杯', '生活用品', 39.0],
  ];

  const orders = [
    [1, 1, '2023-01-20', 'completed'],
    [2, 2, '2023-02-25', 'completed'],
    [3, 3, '2023-01-10', 'completed'],
    [4, 1, '2023-03-05', 'completed'],
    [5, 4, '2023-03-15', 'completed'],
    [6, 5, '2022-11-05', 'completed'],
    [7, 6, '2023-04-20', 'completed'],
    [8, 7, '2023-05-25', 'completed'],
    [9, 8, '2023-02-18', 'completed'],
    [10, 9, '2022-12-28', 'completed'],
    [11, 1, '2023-05-10', 'completed'],
    [12, 10, '2023-06-05', 'completed'],
    [13, 11, '2023-03-20', 'completed'],
    [14, 12, '2023-02-02', 'completed'],
    [15, 13, '2023-07-05', 'completed'],
    [16, 5, '2023-01-15', 'completed'],
    [17, 5, '2023-04-02', 'cancelled'],
    [18, 2, '2023-06-10', 'completed'],
    [19, 3, '2023-06-15', 'pending'],
    [20, 9, '2023-03-08', 'completed'],
    [21, 6, '2023-06-22', 'completed'],
    [22, 1, '2023-07-01', 'completed'],
    [23, 8, '2023-05-30', 'completed'],
    [24, 11, '2023-06-28', 'cancelled'],
    [25, 9, '2023-05-12', 'completed'],
    [26, 7, '2023-07-10', 'completed'],
    [27, 12, '2023-04-25', 'completed'],
    [28, 4, '2023-05-19', 'completed'],
    [29, 2, '2023-01-08', 'completed'],
    [30, 13, '2023-07-20', 'pending'],
  ];

  // [order_id, product_id, quantity]
  const itemLines = [
    [1, 1, 2], [1, 2, 1],
    [2, 3, 1],
    [3, 5, 3], [3, 10, 2],
    [4, 2, 1], [4, 8, 1],
    [5, 4, 1],
    [6, 9, 1],
    [7, 1, 1], [7, 6, 4],
    [8, 3, 2],
    [9, 7, 1], [9, 10, 1],
    [10, 2, 1],
    [11, 8, 2],
    [12, 1, 1],
    [13, 5, 2],
    [14, 6, 10],
    [15, 9, 1],
    [16, 3, 1], [16, 1, 1],
    [17, 2, 1],
    [18, 7, 1],
    [19, 10, 4],
    [20, 4, 2],
    [21, 1, 3],
    [22, 2, 2], [22, 8, 1],
    [23, 5, 1],
    [24, 3, 1],
    [25, 9, 1],
    [26, 6, 5],
    [27, 1, 2],
    [28, 7, 1],
    [29, 10, 3],
    [30, 3, 1],
  ];

  const productPrice = Object.fromEntries(products.map((p) => [p[0], p[3]]));

  const esc = (v) => {
    if (v === null || v === undefined) return 'NULL';
    if (typeof v === 'number') return String(v);
    return `'${String(v).replace(/'/g, "''")}'`;
  };

  const lines = [];
  lines.push(`
    CREATE TABLE customers (
      customer_id INTEGER PRIMARY KEY,
      name TEXT,
      city TEXT,
      signup_date TEXT,
      segment TEXT
    );
    CREATE TABLE products (
      product_id INTEGER PRIMARY KEY,
      name TEXT,
      category TEXT,
      price REAL
    );
    CREATE TABLE orders (
      order_id INTEGER PRIMARY KEY,
      customer_id INTEGER,
      order_date TEXT,
      status TEXT
    );
    CREATE TABLE order_items (
      order_item_id INTEGER PRIMARY KEY,
      order_id INTEGER,
      product_id INTEGER,
      quantity INTEGER,
      unit_price REAL
    );
  `);

  for (const row of customers) {
    lines.push(`INSERT INTO customers VALUES (${row.map(esc).join(',')});`);
  }
  for (const row of products) {
    lines.push(`INSERT INTO products VALUES (${row.map(esc).join(',')});`);
  }
  for (const row of orders) {
    lines.push(`INSERT INTO orders VALUES (${row.map(esc).join(',')});`);
  }
  itemLines.forEach((row, idx) => {
    const [orderId, productId, qty] = row;
    const unitPrice = productPrice[productId];
    lines.push(
      `INSERT INTO order_items VALUES (${idx + 1},${orderId},${productId},${qty},${unitPrice});`
    );
  });

  return lines.join('\n');
})();
