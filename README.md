# COSMIC HOPPER — game Game Boy Advance (file .gba)

Một game "nhảy platform" trong không gian cho **Game Boy Advance**, viết bằng
ARM assembly tự sinh mã máy, **không dùng devkitPro / SDK / toolchain nào**.

| | |
|---|---|
| File chơi | `cosmic-hopper.gba` (262.144 byte = 256 KB) |
| Nền tảng | Game Boy Advance (ARM7TDMI, ARMv4T) |
| Đồ hoạ | Video mode 3 — framebuffer 240×160, 16 bpp |
| Chạy trên | VBA-M, mGBA, gpSP, phần cứng thật |
| Kích thước code | ~3,4 KB code + dữ liệu (toàn bộ game nằm trong ~4,3 KB đầu của ROM) |

## Chuyện gì đã xảy ra với file cũ?

File `cosmic-hopper.gba` bạn gửi **không phải một ROM bị hỏng dữ liệu** mà là
một file rỗng: trong 262.144 byte chỉ có **56 byte khác 0**, gồm header (tên
game, game code `CHPR`) và một mẩu code Thumb 26 byte không hoàn chỉnh. Không có
Nintendo logo, không có code game, không có dữ liệu — nên không thể "vá" lại
được, vì không còn gì để khôi phục.

Vì vậy file đã được **dựng lại từ đầu** thành một game hoàn chỉnh cùng tên
`COSMIC HOPPER`, dùng đúng phong cách của project `snake-gba` (assembler ARMv4T
nhỏ, sinh ROM bằng Python, không cần toolchain).

Bản gốc được giữ lại tại `cosmic-hopper.broken.gba` (ở thư mục gốc project).

## Cách chơi

1. Màn hình tiêu đề: bấm **START** (Enter).
2. Phi hành gia tự nhún trên các bệ phát sáng. Bạn chỉ cần **lái sang trái /
   phải** để đáp xuống bệ cao hơn.
3. **D-pad / phím mũi tên** — di chuyển ngang.
4. **START (Enter)** — chơi lại sau khi thua.
5. Điểm = độ cao đã leo được (chia 8 pixel). Càng lên cao điểm càng tăng.
6. Rơi khỏi màn hình phía dưới → **GAME OVER**.

Mẹo: bệ tiếp theo luôn nằm trong tầm nhảy (cách 38–50 px, cao tối đa ~80 px) và
lệch ngang tối đa 56 px, nên chỉ cần nghiêng nhẹ là lên được.

Phím trong **VBA-M**: phím mũi tên = D-pad, `Enter` = START.
Trong **mGBA**: phím mũi tên = D-pad, `Enter` = START.

## Build lại ROM

Không cần cài gì ngoài Python 3 (dùng thư viện chuẩn):

```
cd cosmic-hopper
python build_rom.py
```

Kết quả: file `cosmic-hopper.gba` được ghi ra cùng thư mục. Script chứa luôn:

1. một **assembler ARMv4T** nhỏ (mã hoá lệnh ARM bằng tay),
2. toàn bộ source game (dưới dạng các lời gọi assembler),
3. phần ghép header GBA + literal pool + dữ liệu (font 3×5, bảng sao, bảng
   bán kính hành tinh cho màn tiêu đề, các chuỗi "COSMIC", "HOPPER",
   "PRESS START"...).

Header có **Nintendo logo chính thức**, complement checksum đúng, lệnh nhảy ARM
ở `0x08000000` trỏ tới `0x080000C0`, ROM pad 256 KB.

## Test tự động

```
cd cosmic-hopper
python test_rom.py
```

Cần thêm gói `unicorn` (ARM emulator). Bộ test giả lập phần cứng GBA (VCOUNT +
KEYINPUT), chạy đúng đoạn mã trong ROM và kiểm tra:

1. header ROM (logo, checksum, entry point, code có mặt),
2. màn hình tiêu đề,
3. START → vào game,
4. nhún tại chỗ 200 frame không chết, camera bám theo,
5. giới hạn màn hình + lái trái/phải,
6. leo lên: camera cuộn, sinh bệ mới, điểm tăng, khoảng cách bệ luôn nhảy tới được,
7. **không có trần độ cao**: leo qua mốc 108 điểm cũ, camera và bệ vẫn sinh
   tiếp ở toạ độ âm, HUD hiện được 4 chữ số,
8. một **autopilot** đơn giản leo được 500 frame và đạt điểm cao,
9. rơi → game over,
10. START → chơi lại từ đầu,
11. kiểm tra framebuffer có vẽ bệ, phi hành gia, HUD.

Khi chạy, test còn xuất ảnh chụp màn hình từ VRAM: `shot_title.png`,
`shot_play.png`, `shot_climb.png`, `shot_autopilot.png`, `shot_high.png`,
`shot_gameover.png`, `shot_restart.png`.

## Ghi chú kỹ thuật

- Không dùng BIOS call, không interrupt, không DMA: game tự poll `VCOUNT`
  (`0x04000006`) để đồng bộ 60 fps và đọc `KEYINPUT` (`0x04000130`).
- Bầu trời là 10 dải màu 16 pixel, vẽ bằng lệnh `str` 32-bit (2 pixel/lần) cho
  nhanh; các đối tượng nhỏ vẽ bằng `strh`.
- Game chơi **vẽ tăng dần** (incremental): mỗi frame chỉ xoá đối tượng cũ bằng
  đúng màu dải trời rồi vẽ đối tượng mới, không vẽ lại cả màn hình. HUD chỉ
  được vẽ lại khi điểm thay đổi. Nhờ vậy hình không nháy và giữ được 60 fps.
- Màn tiêu đề và màn game over chỉ vẽ một lần; hành tinh chỉ xuất hiện ở màn
  tiêu đề.
- Chống input rác lúc khởi động: game chỉ nhận START sau khi đã thấy ít nhất
  một frame không bấm phím, và phải giữ START **5 frame liên tiếp** (~0,08 s).
  Giá trị keypad `0xFF` (không thể có trên phần cứng thật) bị coi như không
  bấm. Vì vậy các phím rác của giả lập lúc bật máy không thể tự vào game.
- Vị trí người chơi và vận tốc dùng số thực dấu phẩy tĩnh Q8.8 (1 pixel = 256).
- Camera chỉ cuộn lên, giữ người chơi ở khoảng y = 56 khi leo cao.
- **Không có trần độ cao**: toạ độ y là số có dấu 32-bit, camera/người chơi/bệ
  được phép âm, nên cứ leo là bệ mới lại sinh ra mãi. HUD in 3–7 chữ số
  (`108` → `1108` → ...). Chỉ khi rơi khỏi màn hình mới hiện GAME OVER.
- Bệ được sinh bằng LCG (`state * 1103515245 + 12345`), lưu trong buffer vòng 14
  phần tử; mỗi bệ mới lệch ngang tối đa ±56 px và cách bệ trước 38–50 px.
- Toàn bộ đồ hoạ vẽ trực tiếp vào framebuffer, không dùng tile/sprite.
