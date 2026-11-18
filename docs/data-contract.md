# 采购门户与成交回执来源约定

normal.json 按顺序接收两份原文。conflict.json 的第二份与第一份使用相同资料身份和版次，但内容不同，账本应拒绝冲突。kind、id 和 revision 是来源声明，不能单独证明跨来源业务归属。

`order_id` 是采购计划与正式回执的共同业务身份；`heads_requested` 和 `heads_received` 分别是计划量与回执确认量，回执按 `receipt_no` 修订。资料顺序为：PO-7 v1=100，R-A v1=60，R-B v1=40；之后订单 v2=95，R-A v2=50。`order-pending.json` 表示两个 v2 尚未取得，`order-page-v2.json` 只补订单，`order-complete.json` 最后补 R-A v2。旧发布应仍为100；新资料齐备后当前为已收90、待收5。

## 履约量核定规则（domain.fulfillment）

- 同一 `order_id` 的订单、同一 `receipt_no` 的回执只取版次最高的有效版本；被替代的旧版进入 `superseded_*_versions` 留痕，不重复计入成交。
- 回执必须同时满足 `order_id`、`lot`、`session` 与当前订单一致且 `state=accepted` 才归属；不一致的回执进入 `excluded_receipts` 或 `unmatched_receipts`，不能凑到订单上。
- 待采目录（清单 `sources` 的 `expected_revision`）登记的新版尚未取得时，旧版只能标 `provisional=true` 并在 `gaps` 中记缺页；此时订单 `verifiable=false`、`status=尚不能核定`，`heads_received` 与 `heads_pending` 为 `null`（临时参考量在 `heads_provisional`），待收量绝不用零冒充。
- 目录闭合后 `heads_pending=max(0, heads_requested-heads_received)`；已收达到计划量时 `status=已收齐`，否则为 `待接收`。
- 重复读取同版次原文由账本按 (collection,type,id,version) 去重，履约量不会膨胀；历史周报由 `archive.release_fulfillment` 冻结，回查仍复现发布当时的计划量、已收量与回执版次。
- `order-mismatch.json` 提供 lot/场次不符的 R-C、R-D；`order-catalog-gap.json` 登记订单 v3 但不提供正文，用于验证缺页时待收量为尚不能核定。
