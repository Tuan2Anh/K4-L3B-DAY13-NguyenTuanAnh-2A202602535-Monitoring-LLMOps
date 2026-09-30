# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Tuấn Anh
- **MSSV:** 2A202602535
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/Tuan2Anh/K4-L3B-DAY13-NguyenTuanAnh-2A202602535-Monitoring-LLMOps
- **Commit SHA cuối:** `3f4ad3a` (`3f4ad3abcfb87b7a63d91cf0eb2623a886477b78`)
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602535`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.txt` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đạt tuyệt đối, đủ required fields, correlation ID và enrichment context |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Hợp lệ toàn bộ 6 panel theo đúng contract |
| `pytest` | 22 passed | 26 passed | Bổ sung unit tests cho CCCD, credit card, observability và request context |
| Số traces hợp lệ | 0 | >30 traces | Tạo thành công trên project cá nhân với đầy đủ quan hệ root/child |
| Số PII leak | 0 | 0 | Scrubbed an toàn toàn bộ Email, Phone VN, CCCD, Credit Card |
| Latency P95 / TTFT P95 | 992ms / 50ms | 529ms / 50ms | Nằm trong ngưỡng an toàn, thấp hơn nhiều so với SLO 3000ms |
| Retrieval success rate | 100% | 100% | Đạt chỉ tiêu guardrail >= 90% |

## 4. Logging và PII

- **Mã correlation ID đại diện cho request (Ảnh 04 & 07):** `req-04c0ffee` (Trace ID tương ứng trên Langfuse: `43a74e5708144582dd3de44ca85c549c`)
- **Mã correlation ID cho kiểm thử PII (Ảnh 05):** `req-05d4e5f6`
- **Cách tạo/nhận và truyền correlation ID:**
  - Tại `CorrelationIdMiddleware` (`app/middleware.py`), trước mỗi request gọi `clear_contextvars()` để xóa context cũ, chống rò rỉ dữ liệu giữa các request.
  - Trích xuất header `x-request-id` hoặc `x-correlation-id`. Nếu client không truyền hoặc để trống, sinh ID mới theo đúng định dạng `req-<8-hex>` (`f"req-{uuid.uuid4().hex[:8]}"`).
  - Gán `request.state.correlation_id = correlation_id` và gọi `bind_contextvars(correlation_id=correlation_id)` vào structlog contextvars.
  - Trong response headers, trả về `x-request-id` và thời gian thực thi `x-response-time-ms`. Đồng thời `correlation_id` được trả về trong body JSON của `ChatResponse`.

- **Các metadata được ghi vào structured log:**
  - Đầu endpoint `/chat` (`app/main.py`), trước khi log `request_received`, thực hiện enrich context:
    - `user_id_hash`: Hash SHA-256 rút gọn 12 ký tự hex của `user_id` qua `hash_user_id()`.
    - `session_id`: Session ID của phiên hội thoại.
    - `feature`: Tên tính năng (`qa`, `summary`,...).
    - `model`: Tên model LLM (`agent.model`).
    - `env`: Môi trường ứng dụng (`dev`, `prod`).
  - Nhờ `merge_contextvars`, toàn bộ các log tiếp theo trong cùng request (`response_sent`, `request_failed`) đều kế thừa các metadata này.

- **Cách bảo đảm PII được scrub trước khi ghi:**
  - Processor `scrub_event` trong `app/logging_config.py` được đăng ký trong chuỗi structlog processors **trước** `JsonlFileProcessor` và `JSONRenderer`.
  - Hàm `_scrub_value` duyệt đệ quy qua tất cả các trường string, dict, list trong `event_dict` và áp dụng `scrub_text()` với các regex pattern cho Email, SĐT Việt Nam (đầu 03, 05, 07, 08, 09, +84), CCCD (12 số) và thẻ tín dụng (16 số có/không khoảng trắng/dấu gạch nối).
  - Nhờ đặt trước renderer và file processor, dữ liệu nhạy cảm được thay thế bằng token `[REDACTED_...]` trước khi JSON được serialize và ghi xuống file `data/logs.jsonl` hoặc stdout.

- **Cách kiểm chứng kết quả:**
  - Chạy `python scripts/validate_logs.py`: đạt 100/100, 0 PII leak detected, 30 unique correlation IDs.
  - Chạy `pytest tests/test_pii.py tests/test_chat_observability.py`: toàn bộ 26 unit tests pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
  - Cấu hình biến môi trường trong `.env`: `LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY` trỏ đến project riêng `day13-k4-l3b-2A202602535` trên host `https://jp.cloud.langfuse.com`.
  - Mọi trace đều có `environment=dev`, `tags=["lab", feature, model]` và metadata chứa `correlation_id` khớp với `data/logs.jsonl`.

- **Cấu trúc root/retrieval/generation observations:**
  - Cây trace thể hiện đầy đủ cấu trúc cha-con:
    ```text
    day13-agent-request (trace)
    └── lab-agent-run (agent / root observation)
        ├── retrieval (retriever / child observation): ghi nhận tài liệu tìm thấy, query_preview đã scrub, doc_count
        └── generation (generation / child observation): ghi nhận model, input prompt, output text đã scrub, usage_details (input_tokens, output_tokens), cost_details
    ```

- **Cách nối trace với log:**
  - Khi request đến API, `CorrelationIdMiddleware` tạo `correlation_id`.
  - Log structlog ghi nhận `correlation_id` này ở mọi event.
  - Agent truyền `correlation_id` vào trace metadata thông qua `propagate_attributes(metadata={"correlation_id": correlation_id, ...})`.
  - Khi gặp log bất thường, chỉ cần copy `correlation_id` và tìm kiếm trên Langfuse UI trong trường metadata.

- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 1 (`labels: ['baseline', 'production']`)
- **Version/label candidate:** Version 2 (`labels: ['candidate']`)
- **Trace ID của mỗi version:**
  - Trace ID Version 1: `bff188b639ad87f940060e26c539fa16`
  - Trace ID Version 2: `9ad66f6e4788180c8c48c24bd6342fa0`
- **Cách promote và rollback `production`:**
  - Quản lý tập trung trên Langfuse Prompt Management thông qua nhãn (label).
  - Khi promote: chuyển nhãn `production` sang Version 2 qua `client.update_prompt(name='day13-chat', version=2, new_labels=['production', 'candidate'])`.
  - Khi rollback: chuyển nhãn `production` quay lại Version 1 qua `client.update_prompt(name='day13-chat', version=1, new_labels=['production', 'baseline'])`.
  - Ứng dụng tự động cập nhật prompt theo nhãn `production` mà không cần sửa code hay rebuild server.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
  - Dashboard endpoint `/dashboard` tích hợp sẵn trên API FastAPI, hiển thị 6 panel trực quan theo hợp đồng `config/dashboard.yaml`:
    1. *Latency percentiles and TTFT*: P50, P95, P99 và TTFT P95 kèm đường ngưỡng SLO 3000ms.
    2. *Request traffic*: Biểu đồ tần suất request theo phút kèm ngưỡng tối thiểu 1 req/min.
    3. *Error rate and retrieval success*: Tỉ lệ lỗi tổng thể (%) và tỉ lệ retrieval thành công (%) kèm ngưỡng lỗi tối đa 2%.
    4. *Cost over time*: Chi phí tích lũy và theo thời gian (USD) kèm ngưỡng tối đa $2.50.
    5. *Input and output tokens*: Tổng lượng tokens in và out kèm ngưỡng 50,000 tokens.
    6. *Quality proxy*: Điểm đánh giá chất lượng câu trả lời trung bình kèm ngưỡng tối thiểu 0.75.

- **SLO và lý do chọn:**
  - Primary SLO: `99.5% requests thành công và có latency_ms <= 3000ms trong cửa sổ 28 ngày`.
  - Lý do chọn: Đáp ứng trải nghiệm người dùng tương tác thời gian thực với trợ lý AI (không phải chờ quá 3 giây) trong khi duy trì độ sẵn sàng cao của hệ thống.

- **Cách tính error budget:**
  - Với mục tiêu SLO 99.5%, error budget là `100% - 99.5% = 0.5%`.
  - Ví dụ trong chu kỳ 28 ngày hệ thống phục vụ 10,000 requests, error budget cho phép tối đa `10,000 * 0.5% = 50 requests` bị lỗi (5xx) hoặc có độ trễ vượt quá 3000ms. Nếu số lượng request vi phạm vượt quá 50, error budget bị cạn kiệt (exhausted), đòi hỏi đóng băng tính năng mới để tập trung cải thiện độ tin cậy.

- **Ba alert và runbook tương ứng:**
  1. `HighLatencyP95` (warning, 5m): Kích hoạt khi P95 latency vượt quá 3000ms trong 5 phút liên tục. Runbook tại `docs/alerts.md#alert-1`.
  2. `HighErrorRate` (critical, 3m): Kích hoạt khi tỉ lệ lỗi vượt quá 2% trong 3 phút. Runbook tại `docs/alerts.md#alert-2`.
  3. `LowRetrievalSuccessRate` (warning, 5m): Kích hoạt khi tỉ lệ thành công của retrieval giảm dưới 90% trong 5 phút. Runbook tại `docs/alerts.md#alert-3`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (Cohort K4, Seed 1312)
- **Khoảng thời gian điều tra:** `2026-09-30 05:06:28Z` – `2026-09-30 05:06:45Z` (12:06:28 – 12:06:45 giờ Việt Nam UTC+7)
- **Triệu chứng từ metrics:**
  - Panel 1 (*Latency percentiles and TTFT*) ghi nhận P95 latency tăng vọt từ baseline ~529ms lên > 2650ms, vi phạm ngưỡng cảnh báo 2000ms đối với feature `monitoring`.
  - Panel 2 (*Traffic*) ghi nhận 5 requests đến đồng thời từ load test challenge.
  - Panel 3 (*Errors*) không ghi nhận request fail (HTTP 200), cho thấy đây là sự cố suy giảm hiệu năng (degradation) chứ không phải sập hoàn toàn (outage).
- **Log line và correlation ID liên quan:**
  - Correlation ID đại diện: `req-ce3ff3af` (Session: `k4-l3b-challenge-s02`, User Hash: `2f2fc5ebba0b`, Feature: `monitoring`).
  - Log `response_sent`:
    ```json
    {
      "service": "api",
      "latency_ms": 2653,
      "ttft_ms": 50,
      "tokens_in": 34,
      "tokens_out": 124,
      "cost_usd": 0.001962,
      "quality_score": 0.9,
      "tool_name": "retrieval",
      "tool_success": true,
      "event": "response_sent",
      "correlation_id": "req-ce3ff3af",
      "ts": "2026-09-30T05:06:31.521833Z"
    }
    ```
- **Trace ID và span gây ảnh hưởng:**
  - Trace ID trên Langfuse: `3b2e6561a91588e1a802245259f0e31f`
  - Phân rã Waterfall cho thấy:
    - Root `lab-agent-run`: tổng thời gian `2.653s`
    - Child span `retrieval` (loại `retriever`): mất tới **`2.501s`** (chiếm hơn 94% tổng latency của request)
    - Child span `generation` (loại `generation`): chỉ mất `0.152s`
- **Root cause:**
  - Sự cố nghẽn cổ chai xuất phát từ tầng Retrieval (RAG component) bị chậm bất thường (`rag_slow` gây trễ 2.5 giây cho mỗi lần query document) khiến request bị kéo dài thời gian phản hồi, trong khi mô hình LLM vẫn sinh câu trả lời trong thời gian bình thường (~150ms).
- **Fix action:**
  - Khôi phục trạng thái hoạt động bình thường của hệ thống bằng lệnh: `python scripts/inject_incident.py --disable`.
  - Triển khai bộ nhớ đệm (caching) cho các tài liệu RAG phổ biến và kiểm tra tải tài nguyên của vector store service.
- **Preventive measure:**
  - Kích hoạt alert `HighLatencyP95` (SLO <= 3000ms, guardrail <= 2000ms) với runbook chi tiết tại `docs/alerts.md#alert-1`.
  - Cấu hình timeout chặt chẽ cho bước `retrieve()` (ví dụ timeout 1.5s) kết hợp fallback sang tài liệu mặc định (degraded mode) để bảo vệ trải nghiệm người dùng, không để sự cố vector store làm tê liệt toàn bộ thời gian phản hồi của agent.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  - Đặt `scrub_event` processor ở vị trí ngay trước JSON renderer và file writer trong structlog. Quyết định này đảm bảo nguyên tắc an toàn thông tin cốt lõi: dữ liệu PII không bao giờ được ghi xuống đĩa cứng hoặc stream ra bên ngoài dưới dạng raw text, đồng thời tránh việc mỗi endpoint phải tự nhớ gọi hàm scrub thủ công.
- **Một lỗi/blocker đã gặp:**
  - API legacy `/api/public/traces` của Langfuse bị trả về mã 410 đối với các organization mới (sau 16/09/2026), yêu cầu chuyển đổi sang OpenTelemetry và endpoint `/api/public/v2/observations`.
- **Cách tìm nguyên nhân và xử lý:**
  - Đọc thông điệp lỗi chi tiết từ Langfuse SDK, chuyển sang dùng OpenTelemetry attributes propagation (`@observe` kết hợp `client.update_current_generation` và `client.api.observations.get_many`) để quản lý và truy xuất chính xác các child spans.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - *Metrics* trả lời câu hỏi: *Có vấn đề gì đang xảy ra và khi nào?* (nhìn toàn cảnh, phát hiện triệu chứng nhanh).
  - *Logs* trả lời câu hỏi: *Những request cụ thể nào bị ảnh hưởng?* (lọc theo khoảng thời gian và mã trạng thái để lấy `correlation_id`).
  - *Traces* trả lời câu hỏi: *Tại sao request đó bị chậm hoặc lỗi ở bước nào?* (mở trace theo `correlation_id`, soi waterfall giữa retrieval và generation để cô lập root cause).
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - Prompt là một thành phần mã nguồn động của hệ thống LLM. Quản lý phiên bản và nhãn (prompt labels) cho phép rollback tức thì khi prompt mới gây hallucination, tăng vọt chi phí token hoặc vi phạm SLO mà không cần triển khai lại mã nguồn ứng dụng.
- **Điều quan trọng nhất đã học:**
  - Khả năng quan sát toàn diện (Observability) trong LLMOps không chỉ là gom log hay vẽ biểu đồ thông thường, mà là chuỗi liên kết mật thiết giữa Correlation ID, OpenTelemetry Spans, Quản trị chi phí token và Tuân thủ bảo vệ dữ liệu nhạy cảm (PII).
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Không có. Hệ thống đã vượt qua toàn bộ technical gates và sẵn sàng nộp bài.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
