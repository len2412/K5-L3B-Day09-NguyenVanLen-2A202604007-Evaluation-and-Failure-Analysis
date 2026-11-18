# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / eval set SHA:**
- **Phiên bản:** code (commit) … · eval set v1 (sha …) · metric_spec … · grader (commit) … · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed, nguồn lab8_public; nhãn: labels_v1.json
- **Metric & ngưỡng:** (trích metric_spec.yaml)
- **Kết quả baseline vs PR:** bảng + paired CI
- **Judge:** tone_ok κ=…, P=…, R=…; helpful bị loại vì …
- **Trace case:** link `docs/trace_case.md`, bước sai đầu tiên, regression test
- **Gate owner:** ai xử lý khi gate exit 1
- **Phạm vi pilot:** …
- **Giới hạn / bằng chứng còn thiếu:** MockLLM, 14 item, judge replay; không đo trên người dùng thật
- **Khi nào tăng eval-set version:** …

## Eval set v2 — slices và độ ổn định

- **Eval set / baseline:** v2, 28 item × 5 seed, gồm 14 claim adversarial; SHA `4357102e623d`. Baseline MockLLM `E-swarm-20261118-4357`: `pass_rate = 0.9786`, `pass_5 = 0.8929`.
- **Ngưỡng `pass_hat_5`:** blocking tại `0.80`. A/A trên MockLLM với seed thay thế `66,77,88,99,110` cho cùng `pass_hat_5 = 0.8929`, Δ = 0. Ngưỡng 0.80 nằm dưới kết quả A/A quan sát được và đạt sàn tối thiểu của checkpoint. MockLLM có tính xác định nên Δ = 0 không đại diện cho độ nhiễu của LLM thật; khi đổi model cần đo lại dải A/A và chọn sàn thấp hơn dải đó.
- **Slice phát hiện hồi quy:** Với `slice_regression`, `pass_rate` toàn cục là `0.9357`, trên sàn `0.85`; CI paired toàn cục `[-0.121, +0.029]` chạm/cắt 0 nên metric tổng không block. Slice `money_movement` đạt `0.85`, Δ `-0.150`, CI `[-0.300, 0.000]`; vì delta âm và cận trên CI chạm 0, slice blocking đã chặn. Slice `adversarial` cũng blocking và được báo cáo riêng.
- **Lỗi chập chờn:** Với `flaky_regression`, `pass_hat_5` giảm từ `0.8929` xuống `0.5714`, thấp hơn sàn 0.80. `pass_rate` là `0.9143`; trong lần chạy này CI paired `[-0.114, -0.014]` cũng block, nên không xem `pass_hat_5` là tín hiệu duy nhất của lần chạy này.
- **Giới hạn cỡ mẫu:** Chỉ có 5 seed cho mỗi item. Lỗi hiếm xuất hiện ở 1/3 seed có thể không được phát hiện ổn định; tăng số seed hoặc chạy lại độc lập khi cần đánh giá độ tin cậy cao hơn. Kết quả hiện tại dùng MockLLM, không chứng minh hiệu năng trên người dùng thật hoặc LLM production.
