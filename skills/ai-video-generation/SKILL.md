---
name: ai-video-generation
description: >
  Generate AI videos from text prompts (text-to-video) or animate images (image-to-video) using Google Flow (Google Veo 2 / Abra). Use whenever the user asks to generate, create, or make a video from a prompt or image (e.g. "tạo video về...", "tạo video...", "generate a video of...", "make a video...").
---

# AI Video Generation via Google Flow (Veo 2)

When the user asks to generate, produce, or create a video:
1. **Always call the `video_generate` model tool directly**.
   - `video_generate` is **ALREADY ACTIVE** in your primary tools.
   - **DO NOT** use `tool_search` to search for it (because `tool_search` only searches deferred non-core tools and will return empty).
   - **DO NOT** write custom Python scripts, `image_generate` + FFmpeg pipelines, or HTML animation scripts. Call `video_generate` directly.
2. **Google Flow Video Models & Intent-based Tiers**:
   Người dùng KHÔNG CẦN nhớ tên mô hình. Hãy tự động ánh xạ theo ý định của người dùng:
   - **Miễn phí (0 tín dụng)**: `veo-3.1-lite-free` — Khi người dùng nói "miễn phí", "free", "0 credits", "làm nháp", "thử nghiệm", "xem trước".
   - **Tiết kiệm (5 tín dụng)**: `veo-3.1-lite` — Khi người dùng nói "tiết kiệm", "rẻ nhất", "nhanh nhất", "5 credits".
   - **Tiêu chuẩn (6 tín dụng)**: `omni-1.1-flash` — **Mặc định** khi người dùng không chỉ định, hoặc khi muốn có âm thanh tự nhiên.
   - **Cao cấp (10 tín dụng)**: `veo-3.1-fast` — Khi người dùng nói "chất lượng cao", "đẹp", "sắc nét", "10 credits".
   - **Cực phẩm (100 tín dụng)**: `veo-3.1-quality` — Khi người dùng nói "cực phẩm", "điện ảnh đỉnh cao", "siêu nét", "phim chiếu rạp", "100 credits".
3. Parameters for `video_generate`:
   - `prompt`: Detailed prompt describing the motion, visual style, atmosphere, and camera motion.
   - `model`: Model ID tương ứng với ý định ở trên (ví dụ: `omni-1.1-flash`, `veo-3.1-lite-free`, `veo-3.1-quality`).
   - `duration`: 10 (default), 8, 6, or 4.
   - `aspect_ratio`: "16:9" (default landscape) or "9:16" (portrait / shorts / tiktok).
   - `image_url`: If animating an existing image (Image-to-Video).
4. Khi người dùng hỏi về các chế độ tạo video hoặc cách chọn, hãy tóm tắt ngắn gọn bảng 5 mức chất lượng (từ Miễn phí 0 credit đến Cực phẩm 100 credit) để người dùng dễ dàng chọn số 1, 2, 3, 4, 5.
5. The tool connects to Google Flow (Veo / Omni), automatically renders the video, downloads the `.mp4` locally, and returns the path in `video`.
6. Telegram Gateway will automatically upload and send the `.mp4` video directly to the chat.
