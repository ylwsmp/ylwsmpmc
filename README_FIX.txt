Исправления:
- Добавлен requirements.txt (раньше Flask мог отсутствовать).
- Исправлена блокировка SQLite при выдаче шардов админом.
Запуск:
python -m pip install -r requirements.txt
python main.py


Discord reviews:
- .env is loaded from the project folder automatically.
- Test review webhook (while logged into admin): /test-review-discord
- Check console for [Discord review] HTTP ...
- 204 means Discord accepted the message; 401/403/404 indicate webhook credentials/channel issues; 429 indicates rate limiting.
