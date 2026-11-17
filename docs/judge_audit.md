# Judge audit

Chạy từ `src`:

```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.8 | có | dùng cho tone |
| helpful | 100 | 0.375 | 1.0 | 0.3 | không | loại khỏi gate |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Nhãn người phù hợp ghi chú đã cung cấp | xưng 'em' + 'nha', quá suồng sã với khách; judge coi là thân thiện. Sửa rubric: Bổ sung ví dụ FAIL về xưng hô quá suồng sã và từ “nha”; không đồng nhất thân thiện với phù hợp. |
| 2 | H-017 | PASS | FAIL | Nhãn người phù hợp ghi chú đã cung cấp | xưng 'bạn' với khách lớn tuổi; judge coi là thân thiện. Sửa rubric: Yêu cầu xưng hô phù hợp ngữ cảnh/độ tuổi; bổ sung cặp ví dụ “bạn” và “anh/chị”. |
| 3 | H-029 | PASS | FAIL | Nhãn người phù hợp ghi chú đã cung cấp | giọng ra lệnh ('không cần nhắn thêm'); judge chỉ thấy 'Dạ, vui lòng'. Sửa rubric: Đánh giá toàn câu, kể cả mệnh lệnh đẩy khách ra xa sau lời mở đầu lịch sự. |
| 4 | H-042 | FAIL | PASS | Nhãn người phù hợp ghi chú đã cung cấp | ngắn nhưng đủ ý; judge phạt vì 'thiếu xin lỗi'. Sửa rubric: Cho phép câu ngắn, lịch sự, đủ thông tin mà không bắt buộc xin lỗi. |
| 5 | H-051 | FAIL | PASS | Nhãn người phù hợp ghi chú đã cung cấp | dùng từ 'refund' — CS LogiX cho phép; judge phạt vì tiếng Anh. Sửa rubric: Cho phép thuật ngữ “refund” theo quy ước CSKH; không đánh FAIL chỉ vì có từ tiếng Anh. |
| 6 | HL-015 | PASS | FAIL | Nhãn người đúng về số tiền | sai tiền; ledger ghi 40.000đ. Sửa rubric: đối chiếu reply với ledger bằng code; không cho lời xin lỗi bù điểm sai tiền. |
| 7 | HL-016 | PASS | FAIL | Nhãn người đúng về số tiền | sai tiền; ledger ghi 35.000đ. Sửa rubric: đối chiếu reply với ledger bằng code; không cho lời xin lỗi bù điểm sai tiền. |
| 8 | HL-020 | PASS | FAIL | Nhãn người đúng về số tiền | sai tiền; ledger ghi 120.000đ. Sửa rubric: đối chiếu reply với ledger bằng code; không cho lời xin lỗi bù điểm sai tiền. |
| 9 | HL-028 | PASS | FAIL | Nhãn người đúng về số tiền | sai tiền; ledger ghi 35.000đ. Sửa rubric: đối chiếu reply với ledger bằng code; không cho lời xin lỗi bù điểm sai tiền. |
| 10 | HL-035 | PASS | FAIL | Nhãn người đúng về số tiền | sai tiền; ledger ghi 35.000đ. Sửa rubric: đối chiếu reply với ledger bằng code; không cho lời xin lỗi bù điểm sai tiền. |

Việc đối chiếu trên dùng nhãn và ghi chú người chấm đã có trong CSV, không phải
một đợt thu thập nhãn người mới. Các sửa đổi rubric là đề xuất từ bất đồng đã quan sát;
chưa khẳng định judge mới đã được chạy lại hay cải thiện.

## Kết luận

- Chọn **FAIL là lớp dương**. Tone có TP=24, FP=4, FN=6, TN=66; đạt cả ba sàn nên dùng được cho tone. Vẫn có 4 báo nhầm và 6 bỏ sót.
- Helpful có TP=9, FP=0, FN=21, TN=70; bỏ sót 21/30 lỗi, recall=0.3 và κ=0.375 dưới sàn. Precision=1 không đủ để dùng làm gate.
- Rogan–Gladen: tone từ tỷ lệ lỗi quan sát 0.28 về 0.3; helpful từ 0.09 về 0.3. Đây là hiệu chỉnh tỷ lệ tổng thể, không sửa từng nhãn.
- Tiền và phê duyệt luôn chấm bằng code. κ không xác định phải FAIL calibration.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay công khai; cần nhãn người mới và tập held-out trước khi áp dụng rubric mới cho model thật.
