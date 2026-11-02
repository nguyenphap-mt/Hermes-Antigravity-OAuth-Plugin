# Hướng Dẫn Sử Dụng & Cấu Hình: Bảo Toàn Trí Nhớ Đa Lượt (Memory Persistence) Trên Gemini Web App Bridge

## 1. Giới Thiệu
Tài liệu này hướng dẫn cơ chế hoạt động, cách cấu hình và kiểm chứng tính năng **Bảo Toàn Ngữ Cảnh Đa Lượt & Chuỗi Gọi Công Cụ (Multi-Turn Memory & Tool-Calling Persistence)** trên `GeminiWebClient`, `GeminiWebToolAdapter` và `GeminiWebPoolManager`.

Tính năng này giải quyết triệt để hiện tượng "Mất trí nhớ" (Context Amnesia) khi trò chuyện nhiều lượt hoặc khi Hermes Agent gọi chuỗi công cụ (`read_file`, `terminal`, `search_files`, `web_search`) qua cả hai kênh:
1. **Stateful Cookie Session (`gemini.google.com/app`)**: Lưu và đồng bộ bộ ba `[cid, rid, rcid]` kèm mã băm lịch sử `history_hash` (SHA-256).
2. **Stateless OAuth-Bridge (`oauth_bridge:<email>`)**: Tự động biên dịch **Full Transcript** (bao gồm `[SYSTEM_INSTRUCTION]`, `<antigravity_tool_protocol>`, toàn bộ lịch sử `[USER]` / `[ASSISTANT]` / `[TOOL_RESPONSE]`) ở mọi lượt gọi.

---

## 2. Cơ Chế Tự Động Chống Mất Ngữ Cảnh

### 2.1. Phân Tách Kênh Stateful (`[cid, rid, rcid]`) và Stateless (`oauth_bridge:`)
- Khi Node có cookie `__Secure-1PSID` thực từ trình duyệt, `GeminiWebClient` sử dụng `[cid, rid, rcid]` của Google để gửi phần chênh lệch (`incremental_only=True`) nhằm tiết kiệm băng thông.
- Khi Node chạy ở chế độ `oauth_bridge:<email>` hoặc khi phiên Web fallback sang tài khoản OAuth liên kết (`cloudcode-pa.googleapis.com/v1internal:generateContent`), hệ thống đánh dấu `is_stateful = False`, không lưu `cid` giả và luôn truyền `full_prompt_text` đầy đủ.

### 2.2. Kiểm Chứng Băm Lịch Sử (`compute_history_hash`) Chống Lệch Pha Khi Failover
- Sau mỗi lượt phản hồi thành công trên kênh Web Stateful, `GeminiWebPoolManager` tính mã băm SHA-256 của toàn bộ lịch sử `messages` tính đến lượt `assistant` vừa hoàn thành và lưu vào `history_hash`.
- Ở lượt kế tiếp:
  - Nếu người dùng bắt đầu cuộc hội thoại mới (`/new` — chưa có lượt `assistant` nào trong `messages`), hệ thống tự động hủy `cid` cũ.
  - Nếu lượt trung gian vừa failover sang một Web Node khác hoặc sang Code Assist OAuth rồi quay lại Node cũ, hệ thống phát hiện `stored_hash != expected_history_hash` (`Turn Desync`), lập tức hủy `cid` cũ bị thiếu lượt và gửi lại **Full Transcript** để đồng bộ 100% ngữ cảnh.

### 2.3. Tương Quan `tool_call_id` ↔ `tool_name` & Bảo Toàn `<thinking>`
- `GeminiWebToolAdapter` tự động ánh xạ `tool_call_id` từ `assistant.tool_calls` sang tên hàm thực tế (`read_file`, `terminal`, v.v.) ngay cả khi thông điệp `role: "tool"` của OpenAI không chứa trường `"name"`.
- Hỗ trợ giải mã `<tool_call>` đặt trong cả khối ```` ```tool_call ````, ```` ```xml ```` và ```` ```json ````.

---

## 3. Cấu Hình (`gemini_web_pool.json` & Dashboard)

Bạn có thể bật/tắt chế độ lưu ngữ cảnh phía máy chủ (`preserve_server_context`) qua Dashboard hoặc API:

```bash
curl -X POST http://127.0.0.1:8642/api/plugins/antigravity/gemini-web/config \
  -H "Content-Type: application/json" \
  -d '{
    "routing_mode": "hybrid_failover",
    "proactive_switch_remaining_pct": 10.0,
    "preserve_server_context": true
  }'
```

- `preserve_server_context: true` *(Mặc định — Khuyên dùng)*: Sử dụng `[cid, rid, rcid]` có kiểm chứng `history_hash` cho các phiên Cookie thực, và tự động dùng Full Transcript khi chạy qua `oauth_bridge:` hoặc khi phát hiện lệch pha lượt.
- `preserve_server_context: false`: Luôn gửi Full Transcript ở mọi lượt trên mọi Node.

---

## 4. Chạy Vòng Lặp Kiểm Chứng 7-Stage Audit Loop

Để kiểm tra toàn diện 7 giai đoạn (bao gồm kiểm thử trí nhớ 3 lượt trên OAuth-Bridge, khôi phục lệch pha Multi-Node Failover, và tương quan Tool Call ID), chạy lệnh:

```bash
python scripts/audit_hermes_gemini_web_loop.py
```

Khi toàn bộ 7 giai đoạn đạt chuẩn, script sẽ xuất JSON với `"all_passed": true` và mã thoát `0`.
