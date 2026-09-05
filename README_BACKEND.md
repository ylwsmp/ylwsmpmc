<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход в админ-панель — YLWSMP</title>
    <link rel="stylesheet" href="static/style.css">
    <style>
        .login-wrapper {
            max-width: 400px;
            margin: 80px auto;
            padding: 30px;
            background: white;
            border: 2px solid #201f1a;
            border-radius: 14px;
            box-shadow: 6px 6px 0 rgba(32,31,26,0.9);
            text-align: center;
        }
        .login-wrapper .logo {
            font-family: 'MinecraftRus', Arial, sans-serif;
            font-size: 32px;
            color: #222;
            margin-bottom: 10px;
        }
        .login-wrapper .sub {
            color: var(--muted);
            margin-bottom: 25px;
        }
        .login-wrapper input {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid #e4dece;
            border-radius: 13px;
            font-size: 16px;
            outline: none;
            transition: 0.2s;
            margin-bottom: 15px;
            font-family: Arial, sans-serif;
        }
        .login-wrapper input:focus {
            border-color: #f5c400;
            box-shadow: 0 0 0 4px rgba(245,196,0,0.13);
        }
        .login-wrapper button {
            width: 100%;
            padding: 14px;
            background: #f5c400;
            border: 2px solid #201f1a;
            border-radius: 10px;
            font-weight: 700;
            font-size: 16px;
            cursor: pointer;
            transition: 0.08s;
            font-family: 'MinecraftRus', Arial, sans-serif;
            box-shadow: 4px 4px 0 rgba(32,31,26,0.9);
        }
        .login-wrapper button:hover {
            background: #ffd21a;
        }
        .login-wrapper button:active {
            transform: translate(4px, 4px);
            box-shadow: none;
        }
        .login-wrapper .error {
            color: #d32f2f;
            margin-top: 12px;
            font-size: 14px;
        }
        .login-wrapper .back-link {
            display: block;
            margin-top: 20px;
            color: var(--yellow-dark);
            text-decoration: none;
            font-weight: 700;
        }
        .login-wrapper .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
<div class="login-wrapper">
    <div class="logo">🔐 Админ-панель</div>
    <div class="sub">Введите пароль для входа</div>
    <form method="GET">
        <input type="password" name="password" placeholder="Пароль" autocomplete="off" required>
        <button type="submit">Войти</button>
    </form>
    
        <div class="error"></div>
    
    <a href="index.html" class="back-link">← Вернуться в магазин</a>
</div>
</body>
</html>
<script>
// Static mode: no Flask backend
document.querySelectorAll('form').forEach(f=>{f.addEventListener('submit',e=>{e.preventDefault();alert('Сайт работает в статическом режиме. Для онлайн-функций подключите PocketBase/Firebase.');});});
</script>
