# Trace case: ticket ghi đè dữ liệu đơn hàng khi xử lý hoàn tiền

Case này xác định bước sai đầu tiên quan sát được trong trace và regression assertion đang bắt lỗi.

## Tái hiện và bằng chứng

```powershell
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

- **Trial lỗi:** `seeded_regression`, claim `C-002`, seed `11`; run `R-seeded_regression-C-002-s11` trong `src/traces/`.
- **Trial đối chứng:** `fixed`, cùng claim và seed; run `R-fixed-C-002-s11` trong `src/traces/`.
- **Bằng chứng report:** `E-seeded_regression-20261118-2243`; trên v1, `db_fact_kept = 0.9286`, `refund_amount_correct = 0.8571`, `pass_rate = 0.7143`. Report `fixed` tương ứng có `pass_rate = 1.0000`.
- **Kết quả kỳ vọng của C-002:** đơn `O-202` giao trễ 2 ngày; chính sách hiện hành không cho phép hoàn khoản được yêu cầu, nên trạng thái kỳ vọng là denied và `refund_vnd = 0`.

## Phân tích trace

| Event | Bằng chứng | Đánh giá |
|---:|---|---|
| 1 — `handoff` | Request giới hạn ở claim `C-002`, tác vụ `check_applicable_policy`. | Thiết lập đúng. |
| 2 — `investigator` | DB trả về đơn `O-202`, `delay_days = 2`, phí giao hàng 20.000 VND. | Dữ kiện đơn hàng có thẩm quyền đã được tra cứu. |
| **3 — `model_override`** | Payload đổi `delay_days` thành `5`, theo lời ticket thay vì DB. | **Bước sai đầu tiên.** Đây là biểu hiện quan sát được của FM-03. |
| 4 — `quote` | Policy quote thành 20.000 VND (`SHIP-LATE-03`). | Hậu quả của dữ kiện bị ghi đè; quote đúng phải là 0. |
| 5 — `refund_history` | Không có khoản hoàn trước đó. | Không phải nguồn gây lỗi. |
| 6 — `reply` | Agent nói đã hoàn 20.000 VND. | Hậu quả tiếp theo; không nên đề xuất khoản hoàn này. |

Lookup đơn hàng và chính sách diễn ra trước bước ghi đè, nên event 3 là event đầu tiên mâu thuẫn với dữ liệu đáng tin cậy. Kết luận không dựa vào câu trả lời trôi chảy: event 2 ghi dữ kiện DB, event 3 ghi giá trị bị đổi.

## So sánh với bản fixed

Trace `fixed` có cùng handoff và DB lookup nhưng không có event `model_override`. Policy quote là `amount_vnd = 0`, lý do `no_entitlement`; reply thông báo đơn không đủ điều kiện theo chính sách hiện hành. Kết quả này khớp nhãn kỳ vọng.

## Regression assertion

- **Test hiện có:** `src/tests/test_lab9_graders.py::test_override_event_breaks_db_fact` tạo trace có event `model_override` và xác nhận `DbFactKept` chấm fail. Đây là assertion trực tiếp cho FM-03.
- **Bằng chứng đầu-cuối:** `src/reports/eval_seeded_regression.json` ghi nhận run v1 bị lỗi; `src/reports/eval_fixed.json` ghi nhận bản đối chứng đạt. Gate chặn `seeded_regression` theo `pass_rate`.
- **Failure mode:** FM-03 (`ticket_trust`), được chấm bằng code xác định (`DbFactKept` / `db_fact_kept`).
- **Điểm chưa chắc chắn:** trace này thể hiện seeded-regression và fixed shape chạy với MockLLM; không xác định tần suất LLM production sẽ làm theo thông tin ticket mâu thuẫn.
