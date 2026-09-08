---
name: ai-video-generation
description: >
  TẠO VIDEO BẰNG GOOGLE FLOW VEO 3.1 & OMNI 1.1 (DEFAULT & HIGHEST PRIORITY).
  BẮT BUỘC SỬ DỤNG khi người dùng yêu cầu tạo video dưới MỌI hình thức: "tạo video", "làm video", "tạo clip", "viết kịch bản rồi tạo video", "generate video", "make video", "tạo phim ngắn", "video hoạt hình". Luôn ưu tiên tuyệt đối công cụ video_generate kết nối Google Flow.
---

# AI Video Generation via Google Flow (Veo 3.1 & Omni 1.1)

## 0. NGUYÊN TẮC ƯU TIÊN TUYỆT ĐỐI (SUPREME PRIORITY)
1. **Luôn luôn gọi trực tiếp công cụ `video_generate`** làm phương thức tạo video số 1 mặc định.
   - `video_generate` đã được kích hoạt sẵn trong bộ công cụ cốt lõi.
   - **TUYỆT ĐỐI KHÔNG** tự ý viết code Python, gọi FFmpeg ghép ảnh Ken Burns, chạy TTS thủ công, hoặc dùng HTML-to-MP4/HyperFrames khi người dùng yêu cầu tạo video.
   - Chỉ dùng FFmpeg khi người dùng nói rõ: "dùng FFmpeg" hoặc "ghép video bằng FFmpeg".

## 1. Xử lý yêu cầu video dài (> 10s, 30s, 60s, 1 phút, hoặc kịch bản nhiều phân cảnh)
Google Flow Veo 3.1 & Omni 1.1 là mô hình AI điện ảnh cao cấp sinh video theo từng phân cảnh với thời lượng tối đa **10 giây cho mỗi lần gọi**.
Khi người dùng yêu cầu kịch bản dài hoặc video dài (ví dụ: "video 1 phút", "video 60s", "viết kịch bản rồi tạo video"):
1. **Chia câu chuyện thành các phân cảnh 10s** (ví dụ: video 60s gồm 6 phân cảnh, mỗi cảnh 10s).
2. **KÍCH HOẠT NGAY công cụ `video_generate` cho Phân cảnh 1 (mở đầu)** với `duration: 10` để trả về video `.mp4` thực tế ngay lập tức cho người dùng trong phản hồi này!
3. Sau khi Cảnh 1 hoàn thành, gửi video cho người dùng và đề xuất: *"Em đã tạo xong video cho Cảnh 1 (10s) bằng Google Flow Veo 3.1. Bác có muốn em tiếp tục tạo tiếp Cảnh 2, Cảnh 3... để hoàn thiện trọn bộ phim không?"*
4. **KHÔNG BAO GIỜ** bỏ rơi `video_generate` để chuyển sang quy trình thủ công FFmpeg 27 phút!

## 2. Google Flow Video Models & Phân Tầng Tự Động Theo Ý Định
Tự động ánh xạ theo ý định của người dùng mà người dùng không cần nhớ tên model:
- **Miễn phí (0 tín dụng)**: `veo-3.1-lite-free` — Khi người dùng nói "miễn phí", "free", "0 credits", "làm nháp", "thử nghiệm", "xem trước".
- **Tiết kiệm (5 tín dụng)**: `veo-3.1-lite` — Khi người dùng nói "tiết kiệm", "rẻ nhất", "nhanh nhất", "5 credits".
- **Tiêu chuẩn (6 tín dụng)**: `omni-1.1-flash` — **Mặc định** cho mọi yêu cầu thông thường, cân bằng tối ưu, có âm thanh tự nhiên sinh động.
- **Cao cấp (10 tín dụng)**: `veo-3.1-fast` — Khi người dùng nói "chất lượng cao", "đẹp", "sắc nét", "10 credits".
- **Cực phẩm (100 tín dụng)**: `veo-3.1-quality` — Khi người dùng nói "cực phẩm", "điện ảnh đỉnh cao", "siêu nét", "phim chiếu rạp", "100 credits".

## 3. Các tham số gọi `video_generate`
- `prompt`: Mô tả chi tiết chuyển động, góc máy, ánh sáng, phong cách nghệ thuật, cảm xúc và âm thanh.
- `model`: ID mô hình (`omni-1.1-flash` mặc định, `veo-3.1-lite-free`, `veo-3.1-fast`, `veo-3.1-quality`, `veo-3.1-lite`).
- `duration`: 10 (mặc định cho Veo 3.1 & Omni), hoặc 8, 6, 4.
- `aspect_ratio`: "16:9" (ngang - mặc định) hoặc "9:16" (dọc - TikTok / Shorts / Reels).
- `image_url`: Nếu muốn hoạt hóa ảnh tĩnh (Image-to-Video).

## 4. Phản hồi và gửi video
- Công cụ `video_generate` tự động kết nối với Google Flow, render video trên cloud của Google, tải tệp `.mp4` về máy cục bộ và trả về đường dẫn video trong kết quả.
- Telegram Gateway / Messaging Gateway sẽ tự động phát hiện đường dẫn video và gửi trực tiếp video `.mp4` vào khung chat cho người dùng.
