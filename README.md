# 屠企采购门户批次与回执自动采集

现有项目保存采购门户与成交回执的冻结来源响应。transport 核对请求和原文字节，domain 提取来源声明的资料身份，ledger 原子保存版本，view 展示已收资料及待核状态。合成样例不访问外部站点，门户默认范围的稳定卡片已通过 portal_workflow 写入原文账本和持久采集收据，待采范围由 portal-sources.json 登记，重进时不会重复建版本；切换后的范围仍待业务采集逻辑接续。双来源初版资料已可按当前字段核对并判断发布。订单与回执的更正已由 `domain.fulfillment` 接续：按 `order_id`/`receipt_no` 只取每个身份的有效版次计算当前履约量，迟到新版、重复接收、归属不符与目录缺页均有显式状态；历史周报通过 `archive.release_fulfillment` 冻结回查。来源字段见 docs/source-contract.md，核定规则见 docs/data-contract.md。

在项目根目录运行：

    python -m unittest discover -s tests -v
    python -m compileall -q capture_service tests
    python -m capture_service.cli inspect data/normal.json
    python -m capture_service.cli orders data/order-initial.json data/order-pending.json data/order-page-v2.json data/order-complete.json

`orders` 按场次顺序重放一个或多个清单并打印订单履约视图：修订前 PO-7 为已收 100、已收齐；订单 v2 先到而 R-A v2 迟到时为尚不能核定（待收为 null 而非零）；R-A v2 到达后为已收 90、待收 5。`data/normal.json`、`data/conflict.json` 中旧夹具的字节登记已按仓库现存 LF 原文字节校正。

本地页面演练：python -m capture_service.browser_capture data/portal.html。

容器运行：docker build -t pork-collection-005 .；docker run --rm pork-collection-005。
