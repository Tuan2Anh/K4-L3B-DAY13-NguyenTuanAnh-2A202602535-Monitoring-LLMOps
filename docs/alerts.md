# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Latency P95 của `response_sent.latency_ms` (ngưỡng SLO <= 3000ms)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` duy trì liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng bị phản hồi chậm, trải nghiệm hội thoại gián đoạn
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel Latency để xác nhận P95/P99 và khoảng thời gian bắt đầu tăng.
  2. Lọc `data/logs.jsonl` trong khung giờ đó, tìm các log `response_sent` có `latency_ms > 3000`, ghi nhận `correlation_id`.
  3. Mở trace có cùng `correlation_id` trên Langfuse, so sánh waterfall giữa child observation `retrieval` và `generation` để xác định bước gây nghẽn (ví dụ do vector store timeout/slow hay LLM latency).
- Mitigation tạm thời: Nếu do retrieval chậm (vector store quá tải), bật caching tạm thời hoặc fallback corpus; nếu do prompt/LLM quá tải, rollback prompt hoặc cân nhắc scale out; nếu đang trong bài lab kiểm tra, kiểm tra incident script (`inject_incident.py --disable`).
- Owner: `student-2A202602535`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `3m`
- Kênh thông báo: Slack `#k4-l3b-critical`
- SLI/SLO liên quan: Error rate `count(request_failed) / count(request_received) * 100` (ngưỡng guardrail <= 2%)
- Điều kiện và thời gian duy trì: `error_rate_pct > 2.0%` duy trì trong 3 phút
- Ảnh hưởng tới người dùng: Người dùng nhận mã lỗi HTTP 500, không nhận được câu trả lời từ hệ thống
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel Errors để xem tỉ lệ lỗi và breakdown theo `error_type` (e.g. `RuntimeError`, `TimeoutError`).
  2. Lọc log `data/logs.jsonl` với `event == "request_failed"`, trích xuất `correlation_id` và trường `error_type`, `detail`.
  3. Tra cứu trace ID trên Langfuse tương ứng với `correlation_id` lỗi để xem stack trace và vị trí exception trong cây quan sát.
- Mitigation tạm thời: Kích hoạt circuit breaker cho tool/retrieval bị lỗi; nếu là lỗi deploy mới, rollback bản build hoặc rollback prompt về bản stable; thông báo incident channel và điều phối khắc phục upstream service.
- Owner: `student-2A202602535`

## Alert 3

- Tên: `LowRetrievalSuccessRate`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Tỉ lệ thành công của retrieval `tool_success_rate_pct` (ngưỡng guardrail >= 90%)
- Điều kiện và thời gian duy trì: `retrieval_success_rate_pct < 90.0%` duy trì trong 5 phút
- Ảnh hưởng tới người dùng: Chatbot trả lời bằng fallback chung chung không có context tài liệu, làm giảm mạnh `quality_score`
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors & Retrieval để đối chiếu `tool_success` rate và panel Quality để kiểm tra mức sụt giảm `quality_score`.
  2. Lọc các bản ghi `response_sent` có `tool_success == false` hoặc `quality_score < 0.7` trong `data/logs.jsonl`.
  3. Mở trace trên Langfuse, kiểm tra observation `retrieval` xem tài liệu trả về có rỗng (empty docs) hoặc exception bị swallow hay không.
- Mitigation tạm thời: Kiểm tra trạng thái kết nối Vector Database/RAG service, khởi động lại cache hoặc chuyển hướng truy vấn sang index phụ (backup index).
- Owner: `student-2A202602535`
