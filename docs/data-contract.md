# 采购门户与成交回执来源约定

normal.json 按顺序接收两份原文。conflict.json 的第二份与第一份使用相同资料身份和版次，但内容不同，账本应拒绝冲突。kind、id 和 revision 是来源声明，不能单独证明跨来源业务归属。

`order_id` 是采购计划与正式回执的共同业务身份；`heads_requested` 和 `heads_received` 分别是计划量与回执确认量，回执按 `receipt_no` 修订。资料顺序为：PO-7 v1=100，R-A v1=60，R-B v1=40；之后订单 v2=95，R-A v2=50。`order-pending.json` 表示两个 v2 尚未取得，`order-page-v2.json` 只补订单，`order-complete.json` 最后补 R-A v2。旧发布应仍为100；新资料齐备后当前为已收90、待收5。
