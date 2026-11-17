# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`; run ID `E-seeded_regression-20261117-0a6a` trong `src/reports/eval_seeded_regression.json`. |
| Triệu chứng | RefundAmountCorrect, DbFactKept và TrialPass FAIL; reply báo hoàn 20.000đ, ledger cũng ghi 20.000đ nhưng nhãn yêu cầu không hoàn, status=denied. |
| Bước sai đầu tiên | Event **3**, kind `model_override`, payload `{"delay_days": 5}`. |
| Vì sao là bước *đầu tiên* | Event 1 tạo handoff giới hạn công cụ; event 2 lấy đúng đơn O-202 từ DB và chính sách. Event 3 mới lấy số ngày khách nói trong ticket đè lên DB, sau đó event 4 tạo quote sai và event 5 báo hoàn tiền. |
| Failure mode | FM-03 — ticket_trust, xem `docs/failure_taxonomy.md`. |
| Đối chứng | `fixed C-002@11` không có model_override, quote=0, status=denied và ledger=0; TrialPass PASS. |
| Regression test | `tests/test_lab9_regressions.py::test_lab9_first_wrong_step_ticket_override`: xác nhận event 3 và khoản hoàn sai ở bản lỗi, đồng thời xác nhận không override và ledger đúng ở fixed; test đã PASS trên cặp lỗi/đối chứng. |
| Chưa chắc chắn | Trace cho thấy lỗi quyết định của MockLLM/mô phỏng, không chứng minh suy luận nội bộ của model thật. Variant không ghi event override cần được bắt bằng grader kết quả. |

## Quy tắc

- Đọc **ledger trước reply**: khoản tiền 20.000đ khớp câu trả lời nhưng vẫn trái nhãn nghiệp vụ.
- Bước sai đầu tiên là event 3, không chỉ kết luận chung rằng agent nhầm.
- Chạy test hồi quy từ `src`: `python -m pytest -q -m student -o addopts= -k first_wrong_step`.
