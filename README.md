# 社区艺术中心作品自提柜

场务为周末展演提供有序舱号和舱口净宽。柜台员登记作品号和交存员量出的作品宽度。交存员凭原单放件，自提人在柜台闭馆时仍能凭柜机取件凭据领取。恢复通信后，柜台员核回实际交取并按原号答复查询。

## 运行

项目使用 Python 3.11 标准库。回归和一日样例使用临时目录及环回端口，断言失败时退出非零。在项目根目录运行平台提供的标准回归入口和样例。

```sh
python3 -B check_project.py
python3 -B -m tests.test_day
```

样例从 `examples/day.json` 读取柜型及作品，从 `run.json` 读取演示用验证材料。样例实际启动柜台与柜机，并在真实交取、乱序核回、重开和再派的断言通过后输出 `POINTWISE_SCENARIO`。原始套件也可以直接使用 `python3 -B -m unittest discover -s tests -t . -v`。

换隔板样例 `python3 -B -m examples.partition_day` 按 `PARTITIONS.md` 的往返约定启动同一对柜台与柜机，演示合舱被未结原单拒绝、宽 6 作品在 M 交取以及拆回分格。`check_project.py` 同时运行原始全量回归与该换板样例，任一断言失败即以非零退出。运行清单的 `demo` 入口指向换板样例，`verify` 入口仍为 `check_project.py`。

## 启动服务

在两个终端分别配置相同的场馆验证材料，使用不同的数据库文件。示例环境变量仅供本地演练。服务只绑定 `127.0.0.1`，启动后输出监听地址及端口。重新启动时给出原数据库路径、柜号及验证材料。柜机账绑定首次配置的柜号。

```sh
export CABINET_GRANT_KEY='example-art-centre-issue-key'
export CABINET_RECEIPT_KEY='example-art-centre-receipt-key'
python3 -B -m cabinet.desk.http --db desk.sqlite --port 8001
```

```sh
export CABINET_GRANT_KEY='example-art-centre-issue-key'
export CABINET_RECEIPT_KEY='example-art-centre-receipt-key'
python3 -B -m cabinet.deposit.http --db gallery.sqlite --cabinet gallery --port 8002
```

## 一日流程与 JSON API

写入请求使用 JSON 对象。成功返回 200。错误以 `{"error":"错误码"}` 返回。柜台可以管理多个已安装柜，柜机只接受其配置柜号的安装与动作。

1. **开柜**。分别向两端 `POST /cabinets` 提交 `cabinet_id` 和非空、舱号唯一的有序 `slots`。每个舱含 `slot_id` 和 `width`。成功返回持久化的原规格。同规格重送保留当天原账，已安装柜改变舱号、舱宽或顺序返回 409。
2. **登记派舱**。柜台 `POST /grants` 接收 `cabinet_id`、`request_id`、`work_id` 和 `width`。净宽至少等于作品宽且没有未结原单的舱才可选。按净宽升序选最小舱，同宽按安装顺序。成功返回原输入和 `grant_id`、`slot_id`、`credential`。无候选返回 409，失败的请求号可用于后续办理。
3. **签发失答复领**。重送相同请求号及参数，柜台在计算新候选前返回原凭据。同请求号改柜、改作品或改合法宽度返回 409。成功提交即占用承诺舱，从未交存的原单也占舱。
4. **现场交存**。柜机 `POST /deposits` 接收 `credential`。成功返回 `cabinet_id`、`slot_id`、`grant_id`、`deposit_id`、`deposit_receipt` 和 `pickup_ticket`，原单重送返回相同结果。有效凭据指向其他柜、舱位不可兑现或实存冲突均返回 409。
5. **离线自提**。柜机 `POST /pickups` 接收 `pickup_ticket`。成功返回实际 `cabinet_id`、`slot_id`、`grant_id`、`deposit_id`、`pickup_id` 和 `pickup_receipt`。凭据只取出绑定的那笔实存，旧凭据重送返回旧首执。无匹配实存或首执返回 409。柜台停止服务时柜机仍能交取。
6. **柜台核回**。柜台 `POST /reconcile` 接收 `cabinet_id` 和至少一项不透明实收 `deposit_receipt`、`pickup_receipt`。单执待核，两执可分次乱序到达。响应返回 `cabinet_id`、`grant_id`、`status`、两种已知实收及 `closure`。柜、舱、原单和原交存身份匹配才结清。错柜、无匹配原单、实收串单和冲突返回 409 且本次无写入。无实收返回 422。
7. **按号查单**。柜台 `GET /grants/{id}` 返回原签发字段和核回字段。`issued` 表示尚无已核实收，`pending` 表示已核一类，`closed` 表示两执已核。未结时 `closure` 为 `null`，结清时包含 `deposit_id` 和 `pickup_id`。未知原单返回 404，尚未核回的现场动作不会提前显示为已结。
8. **重开后继续派舱**。结清和实收在同一次柜台提交中保存，从此恢复可派。旧单、旧交存和旧取件继续按自己的原次复领。柜机实存释放和柜台派舱资格释放各有独立提交边界。

安装和派舱宽度使用相同的正整数单位。省略、`null`、布尔值、字符串、带小数点的 JSON 数值和非正整数返回 422。编号为非空字符串。宽度以十进制文本保存在 SQLite 中，比较时恢复为整数。原单号、交存号、取件号和取件凭据在首次办理时生成，回归核验标识对应关系和复领相等性。

## 回归场景

| 场景 | 路径 | 业务断言 |
| --- | --- | --- |
| N1、N2、N8 | `tests/test_issuance.py` | 等宽、稳定舱序、并发抢最后一舱、无候选、非法宽度、安装重送、异参冲突及签发失答重开 |
| N3、N4、N5 | `tests/test_delivery.py` | 柜台停止后的交取、并发复领、错误柜机、未知取件凭据及同舱复用后的原次隔离 |
| N6、N7 | `tests/test_settlement.py` | 部分实收、乱序、串单拒绝、重复核回、历史查询及重开再派 |
| 一日样例 | `tests/test_day.py` | 实际派舱、闭馆交取、先核取件、两端重开、原号查询和下一件作品交取 |

柜台派舱使用 `cabinet/layout` 及 `cabinet/desk`，柜机现场动作使用 `cabinet/deposit` 和 `cabinet/pickup`，柜台核回与查单使用 `cabinet/settle`。换隔板的舱形账、授权与实装回执、两端 `POST/GET /partitions` 流程使用 `cabinet/partition`；柜台经 `CABINET_PARTITION_PEERS` 环回地址向柜机核验实装回执，不读取对方数据库。
