# 来源字段

procurement_page 与 trade_receipt 的 lot 是来源声明的关联线索；字段相等不证明两份原文已经完整或同版。

PO-7 的计划量和 R-A、R-B 的回执量按 `order_id` 与 `receipt_no` 关联。文档 revision 表示该订单或回执的版本：订单 v2 替代 PO-7 v1，R-A v2 替代 R-A v1，不能把版本当成新的订单或回执。R-B 仍为有效 v1。
